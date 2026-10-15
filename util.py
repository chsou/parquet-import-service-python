# Copyright (c) 2026 Christoph Souris

import asyncio
import glob
import json
import os
import sys

from dotenv import load_dotenv
from pyc8y import CumulocityClient, get_client
from pyc8y.auth import BasicAuth
from pyc8y.model import Application

# Registers/deregisters this microservice as a Cumulocity application, using
# the admin credentials of the tenant it's registered against (read from the
# environment, falling back to a local .env file). See justfile: `register`,
# `deregister`.

load_dotenv()  # admin credentials: use env vars if already set, else fall back to .env

with open("src/cumulocity.json") as fp:
    REQUIRED_ROLES = json.load(fp)["requiredRoles"]

with open("ISOLATION") as fp:
    ISOLATION = fp.read().strip()

with open("MICROSERVICE_NAME") as fp:
    MICROSERVICE_NAME = fp.read().strip()


async def register() -> None:
    """(Re-)register the microservice application at Cumulocity, and write
    its runtime credentials to .env-ms for local testing."""
    async with await get_client() as c8y:
        apps = await c8y.applications.get_all(name=MICROSERVICE_NAME)
        if apps:
            app = apps[0]
            if set(app.required_roles or []) == set(REQUIRED_ROLES):
                print(f"Microservice '{MICROSERVICE_NAME}' (ID {app.id}) already up to date.")
            else:
                app.required_roles = REQUIRED_ROLES
                await app.update()
                print(f"Microservice '{MICROSERVICE_NAME}' (ID {app.id}) updated.")
        else:
            app = await Application(
                c8y,
                name=MICROSERVICE_NAME,
                key=f"{MICROSERVICE_NAME}-key",
                type=Application.MICROSERVICE_TYPE,
                availability=Application.PRIVATE_AVAILABILITY,
                required_roles=REQUIRED_ROLES,
            ).create()

            # subscribe the owning tenant so the microservice becomes usable there
            await c8y.post(
                f"/tenant/tenants/{c8y.tenant_id}/applications",
                json={"application": {"self": f"{c8y.base_url}application/applications/{app.id}"}},
            )
            print(f"Microservice '{MICROSERVICE_NAME}' (ID {app.id}) created and subscribed for tenant '{c8y.tenant_id}'.")

        await _write_env(c8y, app.id)


async def _write_env(c8y: CumulocityClient, application_id: str) -> None:
    """Fetch the microservice's bootstrap/service credentials and write .env-ms."""
    bootstrap = await c8y.get(f"/application/applications/{application_id}/bootstrapUser")

    if ISOLATION == "MULTI_TENANT":
        lines = [
            f"C8Y_BASEURL={c8y.base_url}",
            f"C8Y_BOOTSTRAP_TENANT={bootstrap['tenant']}",
            f"C8Y_BOOTSTRAP_USER={bootstrap['name']}",
            f"C8Y_BOOTSTRAP_PASSWORD={bootstrap['password']}",
        ]
    else:  # PER_TENANT
        async with CumulocityClient(
            base_url=c8y.base_url,
            tenant_id=bootstrap["tenant"],
            auth=BasicAuth(f"{bootstrap['tenant']}/{bootstrap['name']}", bootstrap["password"]),
        ) as bootstrap_client:
            subscriptions = await bootstrap_client.get("/application/currentApplication/subscriptions")
        service_user = subscriptions["users"][0]
        lines = [
            f"C8Y_BASEURL={c8y.base_url}",
            f"C8Y_TENANT={service_user['tenant']}",
            f"C8Y_USER={service_user['name']}",
            f"C8Y_PASSWORD={service_user['password']}",
        ]

    with open(".env-ms", "w") as fp:
        fp.write("\n".join(lines) + "\n")

    print(f"Wrote {ISOLATION.lower()} credentials to environment file (.env-ms).")


async def deregister() -> None:
    """Deregister (delete) the microservice application from Cumulocity."""
    async with await get_client() as c8y:
        apps = await c8y.applications.get_all(name=MICROSERVICE_NAME)
        if not apps:
            raise LookupError(f"No application named '{MICROSERVICE_NAME}' found.")
        app = apps[0]
        await app.delete()
        os.unlink(".env-ms")
        print(f"Microservice '{MICROSERVICE_NAME}' (ID {app.id}) deleted. Environment file (.env-ms) removed.")


async def deploy():
    """ Update a microservice at Cumulocity. """
    async with await get_client() as c8y:
        zip_files = glob.glob("dist/*.zip")
        if not zip_files:
            raise FileNotFoundError("No package (.zip) file found in 'dist/' directory. Please build the microservice first.")
        package_file = zip_files[0]
        print(f"Found previously build binary: {package_file}.")

        apps = await c8y.applications.get_all(name=MICROSERVICE_NAME)
        if not apps:
            raise LookupError(f"No application named '{MICROSERVICE_NAME}' found.")
        app = apps[0]
        print(f"Uploading binary for microservice '{app.name}' (ID {app.id}) ...")
        await c8y.applications.upload_attachment(app.id, package_file)
        print("Microservice binary uploaded successfully.")


def main() -> None:
    """CLI entry point: `util.py <register|deregister>`."""
    actions = {
        "register": register,
        "deregister": deregister,
        "deploy": deploy,
    }
    asyncio.run(actions[sys.argv[1]]())


if __name__ == "__main__":
    main()
