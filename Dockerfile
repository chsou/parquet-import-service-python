# --- Build ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-install-project --no-dev

COPY src/ ./src/

RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

# --- Runtime ---
FROM python:3.12-slim AS runtime

# Add the virtualenv to PATH (no 'source activate' needed)
ENV PATH="/app/.venv/bin:$PATH"

RUN groupadd -g 1001 app && \
    useradd -u 1001 -g app -m -d /app -s /bin/false app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 80

CMD ["uvicorn", "main", "--host", "0.0.0.0", "--port", "80"]
