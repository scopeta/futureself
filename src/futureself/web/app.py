"""FastAPI application — JSON API backend for the FutureSelf React UI."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from futureself.web.routes.api import router as api_router

load_dotenv(override=True)

_appinsights_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
if _appinsights_conn:
    from azure.monitor.opentelemetry import configure_azure_monitor  # noqa: PLC0415
    configure_azure_monitor(connection_string=_appinsights_conn)
    # MAF OTel instrumentation is best-effort — some agent-framework releases
    # have a broken observability module that fails at import time. Without it
    # we still get HTTP/DB spans from azure-monitor-opentelemetry, just not
    # MAF-specific agent/skill spans.
    try:
        from agent_framework.observability import enable_instrumentation  # noqa: PLC0415
        enable_instrumentation(enable_sensitive_data=False)
    except (ImportError, AttributeError):
        pass

_FRONTEND_DIST = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Apply Alembic migrations up to head (sync; runs in a worker thread)."""
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ANN201, ARG001
    """On startup, bring the DB schema to head so a fresh database can't 500.

    Gated on ``DATABASE_URL`` so local dev / unit tests (which use a direct
    SQLite engine and never set it) skip migrations entirely. A migration
    failure fails startup fast rather than serving on a bad schema.
    """
    if os.getenv("DATABASE_URL"):
        print("[startup] applying database migrations (alembic upgrade head)...", flush=True)
        try:
            await asyncio.to_thread(_run_migrations)
        except Exception:
            import traceback  # noqa: PLC0415
            print("[startup] MIGRATION FAILED:", flush=True)
            traceback.print_exc()
            raise
        print("[startup] database migrations applied.", flush=True)
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(title="FutureSelf", lifespan=_lifespan)

    # Initialise database engine — DATABASE_URL is required in production.
    from futureself.db.engine import init_engine  # noqa: PLC0415
    init_engine()

    # ALLOWED_ORIGINS: comma-separated list of origins for CORS.
    # Defaults to empty (same-origin); set explicitly if frontend is on a separate origin.
    _origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Hardening: per-IP rate limit on /api/* (anonymous, paid-LLM endpoint) and
    # security headers on every response. Added after CORS so they sit outside it;
    # SecurityHeaders added last → outermost → applies even to 429 responses.
    from futureself.web.security import (  # noqa: PLC0415
        RateLimitMiddleware,
        SecurityHeadersMiddleware,
    )
    application.add_middleware(
        RateLimitMiddleware, limit_per_min=int(os.getenv("RATE_LIMIT_PER_MIN", "30"))
    )
    application.add_middleware(SecurityHeadersMiddleware)

    application.include_router(api_router, prefix="/api")

    # Capture incoming HTTP requests as App Insights "requests" telemetry.
    # configure_azure_monitor() (module import above) wires the exporter and the
    # agent/dependency spans, but server-side FastAPI requests need explicit
    # instrumentation — without it the request-driven portal blades (Performance,
    # Application Map, end-to-end transactions) stay empty. Guarded by the
    # connection string so local dev is untouched; the instrumentation package is
    # provided transitively by azure-monitor-opentelemetry.
    if _appinsights_conn:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: PLC0415
        FastAPIInstrumentor.instrument_app(application)

    # Serve the built React app in production (frontend/dist must exist)
    if _FRONTEND_DIST.exists():
        _assets = _FRONTEND_DIST / "assets"
        if _assets.exists():
            application.mount(
                "/assets",
                StaticFiles(directory=str(_assets)),
                name="assets",
            )

        @application.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            return FileResponse(str(_FRONTEND_DIST / "index.html"))

    return application


app = create_app()
