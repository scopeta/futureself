"""Anthropic (Claude) concrete implementation of LLMProvider."""
from __future__ import annotations

import anthropic

from futureself.llm.provider import LLMProvider


class AnthropicProvider(LLMProvider):
    """LLMProvider backed by the Anthropic Messages API.

    Reads ``ANTHROPIC_API_KEY`` from the environment automatically (via the
    anthropic SDK).  The model defaults to ``claude-sonnet-4-20250514`` but can
    be overridden via ``FUTURESELF_LLM_MODEL``.
    """

    provider_type: str = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        self.client = anthropic.AsyncAnthropic()
        self.model = model

    async def complete(
        self,
        system: str,
        user: str,
        response_format: dict | None = None,
    ) -> str:
        """Call the Anthropic Messages API.

        Args:
            system: System prompt content (passed via the ``system`` parameter).
            user: User turn content.
            response_format: When ``{"type": "json_object"}``, a JSON
                instruction is appended to the user message so the model
                returns well-formed JSON.

        Returns:
            The text of the first content block.
        """
        user_content = user
        if response_format and response_format.get("type") == "json_object":
            user_content = (
                user + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
                "No markdown fences, no extra text."
            )

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[
                {"role": "user", "content": user_content},
            ],
        )
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                return text
        return ""
