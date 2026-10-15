# Copyright (c) 2026 Christoph Souris

microservice_name := `cat MICROSERVICE_NAME`
isolation := `cat ISOLATION`
provider := `cat PROVIDER`

port := "8000"

_default:
    @echo "Microservice: {{microservice_name}} (isolation: {{isolation}}, provider: {{provider}})"
    @echo "Variables: port={{port}}"
    @just --list

# Turn this template into your own project (run once, right after creating it; see: just init --help)
[positional-arguments]
init *args:
    @test -d .template || { echo "Project is already initialized." >&2; exit 1; }
    @bash .template/init.sh "$@"

# Register microservice at Cumulocity (needs environment credentials)
register:
    uv run python util.py register

# Deregister microservice at Cumulocity (needs environment credentials)
deregister:
    uv run python util.py deregister

# Build deployable microservice package, use Git version by default
build version='':
    #!/usr/bin/env sh
    set -eu
    version="{{version}}"
    if [ -z "$version" ]; then
        if ! distance=$(git rev-list --count HEAD 2> /dev/null); then
            echo "No Git history to derive a version from. Please pass one, e.g.: just build 1.0.0" >&2
            exit 2
        fi
        version="0.0.0-c$(printf '%02d' "$distance")"
        if [ -n "$(git status --porcelain)" ]; then
            version="${version}-r$(date +%y%m%d%H%M)"
        fi
    fi
    ./build.sh -n {{microservice_name}} -v "$version" -i {{isolation}} -p "{{provider}}"

# Deploy previously built microservice package
deploy:
    uv run python util.py deploy

# Locally serve microservice (must be registered beforehand)
serve:
    echo "Running previously registered microservice (see: just register)..."
    uv run uvicorn main:app --app-dir src/main --port {{port}} --reload

# Perform a GET to locally running microservice (example: just get /health)
get path:
    #!/usr/bin/env sh
    set -eu
    . .env-ms
    tenant="${C8Y_BOOTSTRAP_TENANT:-$C8Y_TENANT}"
    user="${C8Y_BOOTSTRAP_USER:-$C8Y_USER}"
    password="${C8Y_BOOTSTRAP_PASSWORD:-$C8Y_PASSWORD}"
    curl -sS -u "${tenant}/${user}:${password}" "http://localhost:{{port}}{{path}}"
    echo

# Perform a POST to locally running microservice (example: just post /register '{"foo": "bar"}')
post path body:
    #!/usr/bin/env sh
    set -eu
    . .env-ms
    tenant="${C8Y_BOOTSTRAP_TENANT:-$C8Y_TENANT}"
    user="${C8Y_BOOTSTRAP_USER:-$C8Y_USER}"
    password="${C8Y_BOOTSTRAP_PASSWORD:-$C8Y_PASSWORD}"
    curl -sS -u "${tenant}/${user}:${password}" -H "Content-Type: application/json" -d '{{body}}' "http://localhost:{{port}}{{path}}"
    echo
