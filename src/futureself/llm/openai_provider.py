"""OpenAI-compatible concrete implementation of LLMProvider."""
from __future__ import annotations

import asyncio
import os

import openai

from futureself.llm.provider import LLMProvider


class OpenAIProvider(LLMProvider):
    """LLMProvider backed by any OpenAI-compatible Chat Completions API.

    Reads ``OPENAI_API_KEY`` and optionally ``OPENAI_BASE_URL`` from the
    environment.  Setting ``OPENAI_BASE_URL`` lets you point at GitHub
    Models, Groq, OpenRouter, or any other compatible endpoint.

    ``OPENAI_MAX_CONCURRENT`` (default ``"4"``) caps the number of parallel
    requests — set to ``"1"`` for GitHub Models which only allows one
    concurrent request per user.

    The model defaults to ``gpt-5-nano`` but can be overridden via
    ``FUTURESELF_LLM_MODEL``.
    """

    def __init__(self, model: str = "gpt-5-nano") -> None:
        base_url = os.getenv("OPENAI_BASE_URL")
        self.client = openai.AsyncOpenAI(
            **(dict(base_url=base_url) if base_url else {}),
        )
        self.model = model
        max_concurrent = _read_positive_int("OPENAI_MAX_CONCURRENT", default=4)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def complete(
        self,
        system: str,
        user: str,
        response_format: dict | None = None,
    ) -> str:
        """Call the OpenAI Chat Completions API.

        Args:
            system: System prompt content.
            user: User turn content.
            response_format: Optional format hint, e.g. ``{"type": "json_object"}``.

        Returns:
            The text of the first completion choice.
        """
        kwargs: dict = {}
        if response_format:
            kwargs["response_format"] = response_format

        async with self._semaphore:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **kwargs,
            )
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        return (getattr(message, "content", "") or "").strip()


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
