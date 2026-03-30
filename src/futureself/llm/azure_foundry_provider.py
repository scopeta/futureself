"""Azure AI Foundry concrete implementation of LLMProvider.

Uses the OpenAI-compatible Chat Completions API exposed by Azure AI Foundry.
When ``model`` is set to ``"model-router"`` Foundry automatically selects the
best underlying model for each prompt based on complexity, task type, and the
configured routing mode (Balanced / Cost / Quality).

Supports two authentication modes:

* **API key** — set ``AZURE_FOUNDRY_API_KEY`` or pass ``api_key=``.
* **Entra ID (default)** — when no API key is provided, uses
  ``azure.identity.DefaultAzureCredential`` to obtain a bearer token.  This
  works transparently with ``az login``, managed identity, workload identity,
  and other credential sources supported by the Azure Identity SDK.
"""
from __future__ import annotations

import asyncio
import os

import openai

from futureself.llm.provider import LLMProvider


def _get_entra_token_provider() -> object:
    """Build an async bearer-token provider using DefaultAzureCredential."""
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    credential = DefaultAzureCredential()
    return get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default",
    )


class AzureFoundryProvider(LLMProvider):
    """LLMProvider backed by an Azure AI Foundry inference endpoint.

    Environment variables (used when constructor args are *None*):

    * ``AZURE_FOUNDRY_ENDPOINT`` — project inference URL, e.g.
      ``https://<account>.services.ai.azure.com/api/projects/<project>``
    * ``AZURE_FOUNDRY_API_KEY``  — API key (optional; omit to use Entra ID).
    * ``AZURE_FOUNDRY_MAX_CONCURRENT`` — max parallel requests (default 10).

    When ``model="model-router"`` Foundry selects the best model per-prompt.
    The ``response.model`` field reveals which model was actually used.
    """

    provider_type: str = "azure_foundry"
    _API_VERSION = "2025-03-01-preview"

    def __init__(
        self,
        model: str = "model-router",
        endpoint: str | None = None,
        api_key: str | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        resolved_endpoint = endpoint or os.getenv("AZURE_FOUNDRY_ENDPOINT")
        if not resolved_endpoint:
            raise ValueError(
                "Azure AI Foundry endpoint is required.  Set AZURE_FOUNDRY_ENDPOINT "
                "or pass endpoint= to the constructor."
            )

        resolved_key = api_key or os.getenv("AZURE_FOUNDRY_API_KEY", "")

        if resolved_key:
            # API-key authentication.
            self.client = openai.AsyncAzureOpenAI(
                azure_endpoint=resolved_endpoint,
                api_key=resolved_key,
                api_version=self._API_VERSION,
            )
        else:
            # Entra ID / managed-identity authentication.
            self.client = openai.AsyncAzureOpenAI(
                azure_endpoint=resolved_endpoint,
                azure_ad_token_provider=_get_entra_token_provider(),
                api_version=self._API_VERSION,
            )
        self.model = model

        concurrency = max_concurrent or _read_positive_int(
            "AZURE_FOUNDRY_MAX_CONCURRENT", default=10,
        )
        self._semaphore = asyncio.Semaphore(concurrency)

    async def complete(
        self,
        system: str,
        user: str,
        response_format: dict | None = None,
    ) -> str:
        """Call the Azure AI Foundry Chat Completions API.

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
