"""FastAPI application for the FutureSelf web UI."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from futureself.web.routes.chat import router as chat_router
from futureself.web.routes.onboarding import router as onboarding_router

load_dotenv(override=True)

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    from futureself.telemetry import init_telemetry  # noqa: PLC0415

    init_telemetry()

    application = FastAPI(title="FutureSelf")

    application.state.sessions = {}
    application.state.conversations = {}

    application.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    application.include_router(onboarding_router)
    application.include_router(chat_router)

    return application


app = create_app()
