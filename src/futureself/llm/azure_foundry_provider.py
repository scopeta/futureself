"""Azure AI Foundry concrete implementation using the Anthropic SDK.

Provides a direct ``AnthropicFoundry`` client for cases where the raw
Anthropic Messages API is needed outside of the MAF agent loop (e.g., tests,
one-off calls). The main orchestrator uses MAF's ``AzureAIAgentClient`` instead.

Authentication:
* **Entra ID (default)** — ``DefaultAzureCredential`` via
  ``azure.identity``.  Works with ``az login``, managed identity, and
  workload identity.
* **API key** — set ``AZURE_FOUNDRY_API_KEY`` (not recommended for
  production).

Environment variables:
* ``AZURE_FOUNDRY_ENDPOINT`` — e.g.
  ``https://<account>.services.ai.azure.com/anthropic``
* ``AZURE_FOUNDRY_API_KEY`` — optional; omit to use Entra ID.
"""
from __future__ import annotations

import os


def build_anthropic_foundry_client() -> object:
    """Build an ``AnthropicFoundry`` client authenticated via Entra ID or API key.

    Returns:
        An ``anthropic.AnthropicFoundry`` instance ready to call
        ``client.messages.create()``.

    Raises:
        ImportError: If ``anthropic`` or ``azure-identity`` is not installed.
        ValueError: If ``AZURE_FOUNDRY_ENDPOINT`` is not set.
    """
    from anthropic import AnthropicFoundry

    endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "")
    if not endpoint:
        raise ValueError(
            "AZURE_FOUNDRY_ENDPOINT is required. "
            "Set it to your Azure AI Foundry project endpoint."
        )

    api_key = os.getenv("AZURE_FOUNDRY_API_KEY", "")
    if api_key:
        return AnthropicFoundry(api_key=api_key, base_url=endpoint)

    # Entra ID (keyless) — recommended for production
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://ai.azure.com/.default"
    )
    return AnthropicFoundry(
        azure_ad_token_provider=token_provider,
        base_url=endpoint,
    )
