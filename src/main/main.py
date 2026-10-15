# Per-tenant microservice example with user access and a periodic background task
# Copyright (c) 2026 Christoph Souris

import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pyc8y import AccessDeniedError, SimpleCumulocityApp

# A per-tenant (simple) Cumulocity application. It is subscribed to a single
# tenant and accesses Cumulocity in two ways:
# - as its own service user, read from the standard C8Y_* environment
#   variables, e.g. for the periodic background task below
# - on behalf of the calling user, using the user's own credentials from the
#   request, so that the user's permissions apply (see /user and /events)

# override=True: the MS service user must win over any admin credentials
# already present in the environment (e.g. from an active c8y-cli session).
load_dotenv(".env-ms", override=True)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s - %(name)s - %(message)s")
log = logging.getLogger("service")

PROCESSING_INTERVAL = 300  # seconds


async def process_devices(c8y: SimpleCumulocityApp) -> None:
    """Background task, processing all devices of the tenant periodically."""
    while True:
        try:
            devices = await c8y.device_inventory.get_all(limit=None)
            for device in devices:
                log.info("Processing device '%s' (%s) ...", device.name, device.id)
        except Exception:  # keep the task alive, try again next time
            log.exception("Processing devices failed.")
        await asyncio.sleep(PROCESSING_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):

    app.state.c8y = SimpleCumulocityApp()
    log.info("Running in tenant '%s' as user '%s'.", app.state.c8y.tenant_id, app.state.c8y.username)
    processing = asyncio.create_task(process_devices(app.state.c8y))

    yield

    processing.cancel()
    await app.state.c8y.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def get_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/user")
async def get_user(request: Request) -> dict:
    """Return the calling user's name and the devices they have access to."""
    user_c8y = await app.state.c8y.get_user_instance(headers=request.headers, cookies=request.cookies)
    devices = await user_c8y.device_inventory.get_all(limit=None)
    return {
        "username": user_c8y.username,
        "devices": [{"id": d.id, "name": d.name, "type": d.type} for d in devices],
    }


@app.get("/events/{device_id}")
async def get_events(device_id: str, request: Request) -> list[dict]:
    """List the 10 latest events of a device, if the calling user has access to it."""
    user_c8y = await app.state.c8y.get_user_instance(headers=request.headers, cookies=request.cookies)
    try:
        await user_c8y.device_inventory.get(device_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"No such device: {device_id}") from e
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=f"No access to device: {device_id}") from e
    events = await user_c8y.events.get_all(source=device_id, limit=10)
    return [{"id": e.id, "time": e.time, "type": e.type, "text": e.text} for e in events]
