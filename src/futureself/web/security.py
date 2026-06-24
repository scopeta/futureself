"""Security middleware: per-IP rate limiting + standard security headers.

The API is anonymous and public, and ``/api/chat/send`` calls a paid LLM — so the
first hardening layer is throttling abuse. This rate limiter is in-memory and
**per-process**: limits reset on scale-to-zero and are not shared across replicas,
so it throttles a single abusive client hitting one replica but is not a global
guarantee. For hard global limits, front the app with Azure Front Door / APIM.

Tune via env:
  ``RATE_LIMIT_PER_MIN``  requests per client IP per minute (default 30; 0 disables)
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honouring the proxy's X-Forwarded-For (Container Apps)."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _over_limit(window: deque[float], now: float, limit: int) -> bool:
    """Evict entries older than 60s; return True if the window is already at `limit`.

    Pure helper (no I/O) so the sliding-window logic is unit-testable.
    """
    cutoff = now - 60.0
    while window and window[0] <= cutoff:
        window.popleft()
    return len(window) >= limit


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach conservative security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window-per-minute per-IP rate limit on ``/api/*`` routes."""

    def __init__(self, app: ASGIApp, limit_per_min: int) -> None:
        super().__init__(app)
        self.limit = limit_per_min
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        if self.limit <= 0 or not request.url.path.startswith("/api/"):
            return await call_next(request)
        ip = _client_ip(request)
        window = self._hits[ip]
        if _over_limit(window, time.monotonic(), self.limit):
            return JSONResponse(
                {"detail": "Too many requests — please slow down and try again shortly."},
                status_code=429,
            )
        window.append(time.monotonic())
        return await call_next(request)
