"""Google Gemini concrete implementation of LLMProvider."""
from __future__ import annotations

import asyncio
import os
import time

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from futureself.llm.provider import LLMProvider


class _RateLimiter:
    """Token-bucket style rate limiter for async calls."""

    def __init__(self, max_per_minute: int) -> None:
        self._interval = 60.0 / max_per_minute
        self._lock = asyncio.Lock()
        self._last: float = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class GoogleProvider(LLMProvider):
    """LLMProvider backed by the Google Gemini API.

    Reads ``GOOGLE_API_KEY`` (or ``GEMINI_API_KEY``) from the environment
    automatically.  The model defaults to ``gemini-2.5-flash`` but can
    be overridden via ``FUTURESELF_LLM_MODEL``.

    A built-in rate limiter prevents exceeding the free-tier quota
    (default 15 RPM, configurable via ``GEMINI_RPM`` env var).
    """

    provider_type: str = "google"

    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        self.client = genai.Client()
        self.model = model
        rpm = _read_positive_int("GEMINI_RPM", default=15)
        self._limiter = _RateLimiter(rpm)

    async def complete(
        self,
        system: str,
        user: str,
        response_format: dict | None = None,
    ) -> str:
        """Call the Google Gemini API.

        Args:
            system: System prompt content (passed as system instruction).
            user: User turn content.
            response_format: When ``{"type": "json_object"}``, the response
                MIME type is set to ``application/json``.

        Returns:
            The text of the model response.
        """
        config = types.GenerateContentConfig(
            system_instruction=system,
        )

        if response_format and response_format.get("type") == "json_object":
            config.response_mime_type = "application/json"

        max_retries = 3
        for attempt in range(max_retries):
            await self._limiter.acquire()
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=user,
                    config=config,
                )
                return response.text or ""
            except ClientError as exc:
                if exc.status == 429 and attempt < max_retries - 1:
                    # Back off and retry on rate-limit errors
                    await asyncio.sleep(15 * (attempt + 1))
                    continue
                raise

        return ""  # unreachable, but satisfies type checker


def _read_positive_int(env_name: str, default: int) -> int:
    """Read a positive integer from env, falling back on invalid values."""
    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
