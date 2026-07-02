"""Tests for the hosted-agent client (BFF-side context assembly + synthesis).

The hosted agent (network + Azure auth) is mocked; these cover the pure
context helper and that ``synthesize`` calls the stateless Responses endpoint
correctly with a caller-supplied recent-turns window.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from futureself.schemas import ConversationTurn, UserBlueprint
from futureself.web import agent_client


def _turns(*pairs: tuple[str, str]) -> list[ConversationTurn]:
    return [ConversationTurn(role=r, content=c) for r, c in pairs]


# ---------------------------------------------------------------------------
# build_user_context
# ---------------------------------------------------------------------------


def test_build_user_context_includes_message():
    ctx = agent_client.build_user_context(UserBlueprint(), [], "Tell me about sleep.")
    assert "Tell me about sleep." in ctx
    assert "USER MESSAGE" in ctx


def test_build_user_context_includes_facts():
    bp = UserBlueprint(inferred_facts=["User is 40", "User lives in London"])
    ctx = agent_client.build_user_context(bp, [], "test")
    assert "User is 40" in ctx
    assert "User lives in London" in ctx


def test_build_user_context_includes_recent_messages():
    recent = _turns(("user", "earlier message"), ("assistant", "earlier reply"))
    ctx = agent_client.build_user_context(UserBlueprint(), recent, "now")
    assert "earlier message" in ctx
    assert "CONVERSATION HISTORY" in ctx


def test_build_user_context_no_transcript_in_profile():
    # The Blueprint carries no transcript, so the profile JSON must not contain
    # conversation history (no unbounded resend / duplication).
    recent = _turns(("user", "hello there"))
    ctx = agent_client.build_user_context(UserBlueprint(), recent, "now")
    profile = ctx.split("KNOWN FACTS")[0].split("CONVERSATION HISTORY")[0]
    assert "conversation_history" not in profile
    assert "hello there" not in profile  # only in the history section, not the profile


def test_build_user_context_empty_history_has_no_history_section():
    ctx = agent_client.build_user_context(UserBlueprint(), [], "hi")
    assert "CONVERSATION HISTORY" not in ctx


# ---------------------------------------------------------------------------
# synthesize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_returns_output_text(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(output_text="hello from the future"))
    fake_client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(agent_client, "_client", lambda: fake_client)

    out = await agent_client.synthesize(UserBlueprint(), _turns(("user", "hi")), "hi again")

    assert out == "hello from the future"
    create.assert_awaited_once()
    # Stateless endpoint: must not store server-side; input carries full context.
    assert create.await_args.kwargs["store"] is False
    assert "USER MESSAGE" in create.await_args.kwargs["input"]


@pytest.mark.asyncio
async def test_synthesize_handles_empty_output(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(output_text=None))
    fake_client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(agent_client, "_client", lambda: fake_client)

    assert await agent_client.synthesize(UserBlueprint(), [], "hi") == ""
