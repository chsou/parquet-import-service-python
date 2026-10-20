# Per-tenant microservice, bulk-uploading parquet files as measurements
# Copyright (c) 2026 Christoph Souris

import asyncio
import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager

import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pyc8y import CumulocityRestClient, SimpleCumulocityApp
from pyc8y.model import Measurement

# A per-tenant (simple) Cumulocity application. It is subscribed to a single
# tenant. Measurements are created on behalf of the calling user, using the
# user's own credentials from the request, so that the user's permissions apply
# (see /measurements).

# override=True: the MS service user must win over any admin credentials
# already present in the environment (e.g. from an active c8y-cli session).
load_dotenv(".env-ms", override=True)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s - %(name)s - %(message)s")
log = logging.getLogger("service")

REQUIRED_COLUMNS = {"timestamp", "source", "series", "value"}
CHUNK_ROWS = 50_000  # rows read from the parquet file at a time

# An uploaded file is kept in memory up to this size, beyond that it spills to a temporary
# file (in TMPDIR, so pointing that at a tmpfs gives you a RAM disk).
SPOOL_MAX_BYTES = int(os.environ.get("UPLOAD_SPOOL_BYTES", str(64 * 1024 * 1024)))
MAX_UPLOAD_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES", str(1024 * 1024 * 1024)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.c8y = SimpleCumulocityApp()
    log.info("Running in tenant '%s' as user '%s'.", app.state.c8y.tenant_id, app.state.c8y.username)

    yield

    await app.state.c8y.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def get_health() -> dict[str, str]:
    return {"status": "ok"}


async def receive_body(request: Request) -> tuple[tempfile.SpooledTemporaryFile, int]:
    """Stream the request body into a spooled file (a parquet footer is at the end, so it needs random access)."""
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_BYTES)  # noqa: SIM115 (closed by the caller)
    size = 0
    try:
        async for data in request.stream():
            size += len(data)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"Upload exceeds {MAX_UPLOAD_BYTES} bytes.")
            spool.write(data)
    except BaseException:
        spool.close()
        raise
    spool.seek(0)
    return spool, size


def read_chunks(file: pq.ParquetFile):
    """Yield lists of (timestamp, source, series, value) rows."""
    for chunk in file.iter_batches(batch_size=CHUNK_ROWS):
        data = chunk.to_pydict()
        yield list(zip(data["timestamp"], data["source"], data["series"], data["value"]))


@app.post("/measurements")
async def post_measurements(
    request: Request,
    type_: str = Query("c8y_Generated", alias="type"),
    batch_size: int = 500,
    workers: int = 20,
) -> JSONResponse:
    """Create measurements from an uploaded parquet file (raw request body).

    The file needs the columns timestamp, source (device ID), series (as 'a.b') and value.
    Measurements are created in bulk, `batch_size` per request, `workers` requests at a time.
    """
    if batch_size < 1 or workers < 1:
        raise HTTPException(status_code=400, detail="batch_size and workers must be positive.")
    user_c8y: CumulocityRestClient = await app.state.c8y.get_user_instance(
        headers=request.headers, cookies=request.cookies
    )

    started = time.monotonic()
    spool, size = await receive_body(request)
    log.info("Received %d bytes in %.2fs.", size, time.monotonic() - started)
    try:
        try:
            file = pq.ParquetFile(spool)
        except pa.ArrowException as e:
            raise HTTPException(status_code=400, detail=f"Not a valid parquet file: {e}") from e
        missing = REQUIRED_COLUMNS - set(file.schema_arrow.names)
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing columns: {', '.join(sorted(missing))}")

        slots = asyncio.Semaphore(workers)
        failures: list[dict] = []
        counts = {"ok": 0, "failed": 0, "requests": 0}

        async def send(first_row: int, measurements: list[Measurement]) -> None:
            async with slots:
                t0 = time.monotonic()
                try:
                    # batch_size == len() makes this exactly one bulk request
                    await user_c8y.measurements.create(*measurements, batch_size=len(measurements))
                    counts["ok"] += len(measurements)
                    outcome = "ok"
                except Exception as e:  # noqa: BLE001 - report and carry on with the remaining requests
                    counts["failed"] += len(measurements)
                    outcome = f"{type(e).__name__}: {e}"
                    failures.append({"rows": [first_row, first_row + len(measurements) - 1], "error": outcome})
                counts["requests"] += 1
                log.info(
                    "rows %d-%d: %.2fs %s",
                    first_row,
                    first_row + len(measurements) - 1,
                    time.monotonic() - t0,
                    outcome,
                )

        row = 0
        chunks = read_chunks(file)
        while (rows := await asyncio.to_thread(next, chunks, None)) is not None:
            measurements = await asyncio.to_thread(
                lambda rows=rows: [Measurement(type=type_, source=s, time=ts, series=(se, v)) for ts, s, se, v in rows]
            )
            await asyncio.gather(
                *(send(row + i, measurements[i : i + batch_size]) for i in range(0, len(measurements), batch_size))
            )
            row += len(measurements)
    finally:
        spool.close()

    result = {"rows": row, **counts, "seconds": round(time.monotonic() - started, 2), "failures": failures}
    return JSONResponse(result, status_code=207 if counts["failed"] else 200)
