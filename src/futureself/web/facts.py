"""Fact distillation — extract candidate facts from the conversation history.

Part of the memory lifecycle (spec §11.1): the transcript is short-term memory;
durable knowledge lives on the Blueprint as **user-confirmed** ``inferred_facts``.
This module runs an on-demand LLM pass over the recent transcript and proposes
candidate facts. Nothing is written to the Blueprint here — the user reviews the
candidates in the UI and explicitly confirms which to keep (the validated path),
after which the history can be pruned without losing what matters.

Like ``judge.py``, this is a data-processing utility, not a user-facing agent:
the single-agent rule (AGENTS.md) governs the chat turn; this is a separate,
user-triggered completion with forced tool use, and it never crashes — failures
degrade to an empty candidate list with ``error`` set.
"""
from __future__ import annotations

import dataclasses
import os
from typing import Any

from futureself.schemas import ConversationTurn, UserBlueprint

_TOOL = {
    "name": "submit_facts",
    "description": "Submit the candidate facts extracted from the conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "facts": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Durable facts the USER stated about themselves, each a short "
                    "third-person sentence starting with 'User'. Empty if none."
                ),
            },
        },
        "required": ["facts"],
    },
}


@dataclasses.dataclass
class FactCandidates:
    facts: list[str]
    error: str | None = None


def _build_prompt(blueprint: UserBlueprint, turns: list[ConversationTurn]) -> str:
    transcript = "\n".join(f"{t.role.upper()}: {t.content}" for t in turns)
    known = "\n".join(f"- {f}" for f in blueprint.inferred_facts) or "(none)"
    return (
        "Extract durable personal facts about the USER from this conversation "
        "transcript. Rules:\n"
        "- Only facts the USER stated about themselves (age, location, family, "
        "health conditions, habits, job, constraints, preferences). Never infer "
        "facts from the ASSISTANT's replies — the assistant role-plays a future "
        "self and its statements are not facts about the user.\n"
        "- Durable only: skip moods, one-off events, and anything already known.\n"
        "- Each fact: one short third-person sentence starting with 'User'.\n"
        "- If there is nothing new and durable, submit an empty list.\n\n"
        f"ALREADY-KNOWN FACTS (do not repeat):\n{known}\n\n"
        f"TRANSCRIPT:\n{transcript}\n\n"
        "Call submit_facts with the list."
    )


def extract_candidates(
    blueprint: UserBlueprint,
    turns: list[ConversationTurn],
    *,
    model: str | None = None,
    _client: Any | None = None,
) -> FactCandidates:
    """Propose candidate facts from ``turns``. Never raises.

    Args:
        blueprint: Current Blueprint (for already-known facts).
        turns: Conversation turns to distill (oldest→newest).
        model: Override model; defaults to ``FACTS_MODEL`` env or ``FUTURESELF_MODEL``.
        _client: Injected Anthropic-style client (testing).
    """
    if not turns:
        return FactCandidates(facts=[])
    model = model or os.getenv("FACTS_MODEL") or os.getenv("FUTURESELF_MODEL", "claude-opus-4-8")

    try:
        client = _client
        if client is None:
            import anthropic  # noqa: PLC0415

            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        response = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "submit_facts"},
            messages=[{"role": "user", "content": _build_prompt(blueprint, turns)}],
        )
        data = _extract_tool_input(response)
        raw = data.get("facts", [])
        known = set(blueprint.inferred_facts)
        facts = [str(f).strip() for f in raw if str(f).strip() and str(f).strip() not in known]
        return FactCandidates(facts=facts)
    except Exception as exc:  # noqa: BLE001 — distillation must never crash the request
        return FactCandidates(facts=[], error=f"{type(exc).__name__}: {exc}")


def _extract_tool_input(response: Any) -> dict[str, Any]:
    """Pull the forced tool-call input dict out of a Messages response."""
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use":
            return dict(getattr(block, "input", {}) or {})
    raise ValueError("no tool_use block in facts response")
