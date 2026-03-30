"""Tests for AzureFoundryProvider."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from futureself.llm.azure_foundry_provider import AzureFoundryProvider, _read_positive_int


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_constructor_requires_endpoint():
    """Raises if no endpoint is provided and env var is missing."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="endpoint is required"):
            AzureFoundryProvider(model="model-router")


def test_constructor_reads_env(monkeypatch):
    """Reads endpoint and API key from env."""
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://example.services.ai.azure.com")
    monkeypatch.setenv("AZURE_FOUNDRY_API_KEY", "test-key")
    provider = AzureFoundryProvider(model="model-router")
    assert provider.model == "model-router"


def test_constructor_explicit_params():
    """Constructor params take precedence over env."""
    provider = AzureFoundryProvider(
        model="gpt-5",
        endpoint="https://my-project.services.ai.azure.com",
        api_key="my-key",
    )
    assert provider.model == "gpt-5"


def test_constructor_entra_id_when_no_api_key(monkeypatch):
    """Uses Entra ID token provider when no API key is set."""
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://example.services.ai.azure.com")
    monkeypatch.delenv("AZURE_FOUNDRY_API_KEY", raising=False)

    mock_token_provider = MagicMock()
    with patch(
        "futureself.llm.azure_foundry_provider._get_entra_token_provider",
        return_value=mock_token_provider,
    ):
        provider = AzureFoundryProvider(model="model-router")
        assert provider.model == "model-router"
        # Client was created (Entra path, no api_key)
        assert provider.client is not None


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_calls_client():
    """Verify complete() calls the async OpenAI client correctly."""
    provider = AzureFoundryProvider(
        model="model-router",
        endpoint="https://test.services.ai.azure.com",
        api_key="test",
    )

    # Mock the client's chat.completions.create
    mock_message = MagicMock()
    mock_message.content = "Hello from model-router"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    provider.client = AsyncMock()
    provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await provider.complete(system="sys", user="hi")
    assert result == "Hello from model-router"

    provider.client.chat.completions.create.assert_called_once()
    call_kwargs = provider.client.chat.completions.create.call_args
    assert call_kwargs.kwargs["model"] == "model-router"


@pytest.mark.asyncio
async def test_complete_returns_empty_on_no_choices():
    """Returns empty string when response has no choices."""
    provider = AzureFoundryProvider(
        model="model-router",
        endpoint="https://test.services.ai.azure.com",
        api_key="test",
    )
    mock_response = MagicMock()
    mock_response.choices = []
    provider.client = AsyncMock()
    provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await provider.complete(system="sys", user="hi")
    assert result == ""


@pytest.mark.asyncio
async def test_complete_passes_response_format():
    """response_format is forwarded to the API call."""
    provider = AzureFoundryProvider(
        model="model-router",
        endpoint="https://test.services.ai.azure.com",
        api_key="test",
    )
    mock_message = MagicMock()
    mock_message.content = '{"key": "value"}'
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    provider.client = AsyncMock()
    provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

    await provider.complete(
        system="sys", user="hi",
        response_format={"type": "json_object"},
    )

    call_kwargs = provider.client.chat.completions.create.call_args
    assert call_kwargs.kwargs["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# _read_positive_int
# ---------------------------------------------------------------------------


def test_read_positive_int_valid(monkeypatch):
    monkeypatch.setenv("TEST_INT", "5")
    assert _read_positive_int("TEST_INT", default=10) == 5


def test_read_positive_int_missing():
    assert _read_positive_int("NONEXISTENT_VAR_12345", default=10) == 10


def test_read_positive_int_invalid(monkeypatch):
    monkeypatch.setenv("TEST_INT", "abc")
    assert _read_positive_int("TEST_INT", default=10) == 10


def test_read_positive_int_zero(monkeypatch):
    monkeypatch.setenv("TEST_INT", "0")
    assert _read_positive_int("TEST_INT", default=10) == 10
