# ---- Frontend build stage ----
FROM oven/bun:1 AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile

COPY frontend/ ./
RUN bun run build

# ---- Python build stage ----
FROM python:3.13-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install production dependencies only (no dev extras).
RUN uv sync --frozen --no-dev

# Work around namespace collision: agent-framework-foundry (and friends) ship an
# empty agent_framework/__init__.py that can clobber the core package's __init__.py
# depending on install order. Force-reinstall the core so its __init__.py wins.
RUN uv pip install --force-reinstall --no-deps agent-framework-core==1.0.1

# ---- Runtime stage ----
FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /app/.venv .venv
COPY --from=frontend-builder /frontend/dist frontend/dist

COPY src/ src/
COPY prompts/ prompts/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "futureself.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
