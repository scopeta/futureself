"""Tests for the rate-limit + security-headers middleware (no DB needed)."""
from __future__ import annotations

from collections import deque

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from futureself.web.security import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    _over_limit,
)


def test_over_limit_sliding_window():
    w: deque[float] = deque()
    assert _over_limit(w, 100.0, 2) is False
    w.append(100.0)
    assert _over_limit(w, 100.0, 2) is False
    w.append(100.0)
    assert _over_limit(w, 100.0, 2) is True  # at limit
    # entries older than 60s are evicted, freeing the window
    assert _over_limit(w, 161.0, 2) is False


def _mini_app(limit: int) -> Starlette:
    async def ok(request):  # noqa: ANN001, ANN202
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/api/ping", ok), Route("/health", ok)])
    app.add_middleware(RateLimitMiddleware, limit_per_min=limit)
    app.add_middleware(SecurityHeadersMiddleware)
    return app


async def test_rate_limit_blocks_after_limit():
    transport = ASGITransport(app=_mini_app(2))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.get("/api/ping")).status_code == 200
        assert (await c.get("/api/ping")).status_code == 200
        assert (await c.get("/api/ping")).status_code == 429


async def test_rate_limit_ignores_non_api_paths():
    transport = ASGITransport(app=_mini_app(1))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        for _ in range(5):
            assert (await c.get("/health")).status_code == 200


async def test_rate_limit_disabled_when_zero():
    transport = ASGITransport(app=_mini_app(0))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        for _ in range(5):
            assert (await c.get("/api/ping")).status_code == 200


async def test_security_headers_present():
    transport = ASGITransport(app=_mini_app(0))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert "strict-transport-security" in r.headers
