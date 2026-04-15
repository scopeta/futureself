"""FastAPI application — JSON API backend for the FutureSelf React UI."""
from __future__ import annotations

import os
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
    from agent_framework.observability import enable_instrumentation  # noqa: PLC0415
    configure_azure_monitor(connection_string=_appinsights_conn)
    enable_instrumentation(enable_sensitive_data=False)

_FRONTEND_DIST = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(title="FutureSelf")

    # Initialise database engine if DATABASE_URL is configured
    if os.getenv("DATABASE_URL"):
        from futureself.db.engine import init_engine  # noqa: PLC0415
        init_engine()

    # Allow the Vite dev server to call the API during local development
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api")

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
