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
# --prerelease=allow is required because azure-ai-agentserver-responses is still in beta.
RUN uv sync --frozen --no-dev --prerelease=allow

# Work around namespace collision: agent-framework-foundry (and friends) ship an
# empty agent_framework/__init__.py that can clobber the core package's __init__.py
# depending on install order. Force-reinstall the core so its __init__.py wins.
# No version pin — use whatever the lockfile resolved (downgrading would break MAF API).
RUN uv pip install --force-reinstall --no-deps agent-framework-core

# ---- Runtime stage ----
FROM python:3.13-slim

WORKDIR /app

# Microsoft ODBC Driver 18 — required by the async Azure SQL driver (aioodbc).
# Tests run on SQLite and never need this; only the deployed BFF connects to Azure SQL.
# The MS package feed is selected by the base image's Debian version ($VERSION_ID),
# so this works whether python:3.13-slim is Debian 12 (bookworm) or 13 (trixie).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && . /etc/os-release \
    && curl -sSL -o /tmp/ms-prod.deb "https://packages.microsoft.com/config/debian/${VERSION_ID}/packages-microsoft-prod.deb" \
    && dpkg -i /tmp/ms-prod.deb && rm /tmp/ms-prod.deb \
    && apt-get update \
    # libgssapi-krb5-2 is a msodbcsql18 dependency (Kerberos/GSSAPI) that
    # --no-install-recommends skips; without it the driver fails to dlopen.
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc libgssapi-krb5-2 \
    && apt-get purge -y curl gnupg \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv .venv
COPY --from=frontend-builder /frontend/dist frontend/dist

COPY src/ src/
COPY prompts/ prompts/
COPY alembic.ini alembic.ini
COPY alembic/ alembic/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "futureself.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
