FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY main ./main

EXPOSE 80
CMD ["uv", "run", "--no-dev", "uvicorn", "main:app", "--app-dir", "main", "--host", "0.0.0.0", "--port", "80"]
