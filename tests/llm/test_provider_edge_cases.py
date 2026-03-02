"""Provider edge-case tests for env parsing and empty responses."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from futureself.llm import anthropic_provider, google_provider, openai_provider


def test_openai_read_positive_int_falls_back_on_invalid(monkeypatch):
    monkeypatch.setenv("OPENAI_MAX_CONCURRENT", "invalid")
    assert openai_provider._read_positive_int("OPENAI_MAX_CONCURRENT", 4) == 4

    monkeypatch.setenv("OPENAI_MAX_CONCURRENT", "0")
    assert openai_provider._read_positive_int("OPENAI_MAX_CONCURRENT", 4) == 4

    monkeypatch.setenv("OPENAI_MAX_CONCURRENT", "3")
    assert openai_provider._read_positive_int("OPENAI_MAX_CONCURRENT", 4) == 3


def test_google_read_positive_int_falls_back_on_invalid(monkeypatch):
    monkeypatch.setenv("GEMINI_RPM", "bad")
    assert google_provider._read_positive_int("GEMINI_RPM", 15) == 15

    monkeypatch.setenv("GEMINI_RPM", "-1")
    assert google_provider._read_positive_int("GEMINI_RPM", 15) == 15

    monkeypatch.setenv("GEMINI_RPM", "20")
    assert google_provider._read_positive_int("GEMINI_RPM", 15) == 20


@pytest.mark.asyncio
async def test_openai_provider_returns_empty_when_no_choices(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(choices=[]))
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(
        openai_provider.openai,
        "AsyncOpenAI",
        lambda **kwargs: fake_client,
    )

    provider = openai_provider.OpenAIProvider(model="test-model")
    result = await provider.complete(system="sys", user="usr")
    assert result == ""


@pytest.mark.asyncio
async def test_anthropic_provider_returns_empty_when_no_text_block(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(content=[]))
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(
        anthropic_provider.anthropic,
        "AsyncAnthropic",
        lambda **kwargs: fake_client,
    )

    provider = anthropic_provider.AnthropicProvider(model="test-model")
    result = await provider.complete(system="sys", user="usr")
    assert result == ""

