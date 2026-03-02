"""Abstract LLM provider interface.

All agent modules and the orchestrator call LLMs exclusively through this
interface. No agent ever imports a vendor SDK directly. Swapping providers
is an environment-variable change.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Vendor-agnostic interface for LLM completions."""

    @abstractmethod
    async def complete(
        self,
        system: str,
        user: str,
        response_format: dict | None = None,
    ) -> str:
        """Send a system + user prompt and return the raw text completion.

        Args:
            system: The system prompt (e.g. loaded from a prompts/*.md file).
            user: The user turn content.
            response_format: Optional vendor-specific format hint.
                Pass ``{"type": "json_object"}`` to request structured JSON.

        Returns:
            The raw string content of the model's first completion choice.
        """
        ...

    @classmethod
    def get_default(cls) -> "LLMProvider":
        """Return the configured provider instance.

        Reads ``FUTURESELF_LLM_PROVIDER`` from the environment (defaults to
        ``"openai"``). Instantiates the corresponding concrete class.
        """
        provider_name = os.getenv("FUTURESELF_LLM_PROVIDER", "openai").lower()

        if provider_name == "openai":
            from futureself.llm.openai_provider import OpenAIProvider  # noqa: PLC0415

            model = os.getenv("FUTURESELF_LLM_MODEL", "gpt-5-nano")
            return OpenAIProvider(model=model)

        if provider_name in ("anthropic", "claude"):
            from futureself.llm.anthropic_provider import AnthropicProvider  # noqa: PLC0415

            model = os.getenv("FUTURESELF_LLM_MODEL", "claude-haiku-4-5-20251001")
            return AnthropicProvider(model=model)

        if provider_name in ("google", "gemini"):
            from futureself.llm.google_provider import GoogleProvider  # noqa: PLC0415

            model = os.getenv("FUTURESELF_LLM_MODEL", "gemini-2.0-flash")
            return GoogleProvider(model=model)

        raise ValueError(
            f"Unknown LLM provider: {provider_name!r}. "
            "Set FUTURESELF_LLM_PROVIDER to a supported value "
            "('openai', 'anthropic', 'google')."
        )
