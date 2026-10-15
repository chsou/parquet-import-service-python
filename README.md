# python-ms

Test service.

A Cumulocity microservice written in Python, using [FastAPI](https://fastapi.tiangolo.com)
and [pyc8y](https://github.com/chisou/cumulocity-python-sdk).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python and dependencies
- [just](https://just.systems) for the project commands
- [Docker](https://www.docker.com) with `buildx` for building the microservice image.
  Cumulocity runs `linux/amd64` images, so on Apple Silicon (or any ARM machine) Docker
  needs amd64 emulation, e.g. Rosetta in Docker Desktop or Colima (`colima start --vz-rosetta`).
  Check with `docker run --rm --platform linux/amd64 python:3.11-slim uname -m`, which should
  print `x86_64`. If it fails with `exec format error`, `just build` will fail as well.
- A Cumulocity tenant and a user that can manage applications

## Setup

Install the dependencies:

```sh
uv sync
```

Put the credentials of your Cumulocity tenant into a `.env` file (or set them as environment variables):

```sh
C8Y_BASEURL=https://<your-tenant>.cumulocity.com
C8Y_TENANT=t12345
C8Y_USER=<user>
C8Y_PASSWORD=<password>
```

## Development

Register the microservice at Cumulocity. This creates the application, subscribes your
tenant to it, and writes the microservice's own credentials to `.env-ms`:

```sh
just register
```

Run the microservice locally (with auto-reload) and call it:

```sh
just serve
just get /health
```

To remove the microservice from Cumulocity again, use `just deregister`.

## Build and deploy

```sh
just build     # builds dist/<name>.zip, versioned from Git
just build 1.0.0   # ... or with an explicit version (needed without Git history)
just deploy    # uploads the package to Cumulocity
```

Run `just` to see all available commands.

## Project layout

| Path                  | Purpose                                                  |
|-----------------------|----------------------------------------------------------|
| `src/main/main.py`    | The microservice itself                                   |
| `src/cumulocity.json` | Microservice manifest (required roles, health probe, ...) |
| `src/Dockerfile`      | Image definition used by `just build`                     |
| `MICROSERVICE_NAME`, `PROVIDER`, `ISOLATION` | Microservice settings used by `just` |
| `util.py`, `build.sh` | Helpers behind the `just` commands                        |
