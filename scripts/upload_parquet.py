"""Upload a parquet file (timestamp, source, series, value) to Cumulocity as measurements.

Each row becomes one measurement: source = device ID, time = timestamp, and the
series "a.b" becomes the fragment {"a": {"b": {"value": <value>}}}.
Credentials are taken from the C8Y_* environment variables or a local .env file.

Example:
    uv run python scripts/upload_parquet.py data.parquet --batch-size 1000 --workers 4
"""

import argparse
import asyncio
import time

import pyarrow.parquet as pq
from dotenv import load_dotenv
from pyc8y import get_client
from pyc8y.model import Measurement

load_dotenv()


async def upload(args: argparse.Namespace) -> None:
    file = pq.ParquetFile(args.file)
    total = file.metadata.num_rows
    done = failed = requests = 0
    started = time.monotonic()
    slots = asyncio.Semaphore(args.workers)

    async def send(c8y, first_row: int, measurements: list[Measurement]) -> None:
        """Send one bulk request, timing it and reporting any failure."""
        nonlocal done, failed, requests
        async with slots:
            t0 = time.monotonic()
            try:
                # batch_size == len() makes this exactly one bulk request
                await c8y.measurements.create(*measurements, batch_size=len(measurements))
                outcome = "ok"
                done += len(measurements)
            except Exception as exc:  # noqa: BLE001 - report and carry on with the remaining requests
                outcome = f"FAILED: {type(exc).__name__}: {exc}"
                failed += len(measurements)
            requests += 1
            print(f"rows {first_row}-{first_row + len(measurements) - 1}: {time.monotonic() - t0:.2f}s {outcome}")

    async with await get_client() as c8y:
        row = 0
        # read in chunks to keep memory bounded, each chunk is split into bulk requests
        for chunk in file.iter_batches(batch_size=args.chunk_size):
            data = chunk.to_pydict()
            measurements = [
                Measurement(type=args.type, source=source, time=ts, series=(series, value))
                for ts, source, series, value in zip(data["timestamp"], data["source"], data["series"], data["value"])
            ]
            await asyncio.gather(
                *(
                    send(c8y, row + i, measurements[i : i + args.batch_size])
                    for i in range(0, len(measurements), args.batch_size)
                )
            )
            row += len(measurements)
    elapsed = time.monotonic() - started
    print(
        f"{total} rows in {requests} requests, {elapsed:.2f}s ({total / elapsed:.0f} rows/s): {done} ok, {failed} failed"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="parquet file to upload")
    p.add_argument("--type", default="c8y_Generated", help="measurement type (default: c8y_Generated)")
    p.add_argument("--batch-size", type=int, default=1000, help="measurements per request (default: 1000)")
    p.add_argument("--workers", type=int, default=4, help="concurrent requests (default: 4)")
    p.add_argument("--chunk-size", type=int, default=50_000, help="rows read from the file at a time (default: 50000)")
    asyncio.run(upload(p.parse_args()))


if __name__ == "__main__":
    main()
