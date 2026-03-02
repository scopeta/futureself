"""OpenAI concrete implementation of LLMProvider."""
from __future__ import annotations

import openai

from futureself.llm.provider import LLMProvider


class OpenAIProvider(LLMProvider):
    """LLMProvider backed by the OpenAI Chat Completions API.

    Reads ``OPENAI_API_KEY`` from the environment automatically (via the
    openai SDK). The model defaults to ``gpt-4o`` but can be overridden via
    ``FUTURESELF_LLM_MODEL``.
    """

    def __init__(self, model: str = "gpt-4o") -> None:
        self.client = openai.AsyncOpenAI()
        self.model = model

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

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        return response.choices[0].message.content or ""
