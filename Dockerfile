# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency metadata and source for package install.
COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install production + otel dependencies (no dev extras).
RUN uv sync --frozen --no-dev --extra otel

# ---- Runtime stage ----
FROM python:3.12-slim

WORKDIR /app

# Copy the virtual environment from the builder.
COPY --from=builder /app/.venv .venv

# Copy application source code.
COPY src/ src/
COPY prompts/ prompts/
COPY config/ config/

# Ensure the venv Python is on PATH.
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "futureself.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
