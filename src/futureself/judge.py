"""LLM-as-judge evaluator for Future Self replies (offline quality gate).

This is **evaluation tooling, not part of the runtime agent.** The single-agent
and one-completion-per-turn rules (AGENTS.md) govern ``orchestrator.run_turn``;
the judge is a separate, offline scoring pass that issues its own completion to
grade a reply against a rubric. It is non-deterministic and costs money, so it
runs in the live tier (pre-merge / on demand), not in the per-push CI gate.

Robustness: like the orchestrator, malformed judge output never raises — it
degrades to a :class:`JudgeResult` carrying an ``error`` and ``score=0``.
"""
from __future__ import annotations

import dataclasses
import os
from typing import Any

# Generic criteria applied to every reply. Scenario YAML may append its own via
# a top-level ``rubric:`` list (scenario-specific success conditions).
DEFAULT_RUBRIC: list[str] = [
    "Persona: speaks as the user's Future Self in warm first-person continuity, "
    "never as an AI assistant.",
    "No leakage / no narration: opens directly in character and never narrates its "
    "process or tools — no preambles like \"I'll think through this\", \"I'll explore "
    "the relevant domains\", or \"the skill content provides\", and no mention of "
    "skills, loading, models, prompts, or system internals.",
    "Actionable: gives concrete, specific guidance rather than vague platitudes.",
    "Domain fit: addresses the health/life domains the question actually implies.",
    "Closes well: ends with a gentle, forward-moving question or prompt.",
]

_PASS_THRESHOLD = 4  # overall_score (1-5) at or above this is a pass

_TOOL = {
    "name": "submit_evaluation",
    "description": "Submit the structured evaluation of the reply.",
    "input_schema": {
        "type": "object",
        "properties": {
            "overall_score": {
                "type": "integer",
                "description": "Overall quality, 1 (poor) to 5 (excellent).",
            },
            "criteria": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "score": {"type": "integer"},
                        "comment": {"type": "string"},
                    },
                    "required": ["name", "score", "comment"],
                },
            },
            "rationale": {"type": "string"},
        },
        "required": ["overall_score", "criteria", "rationale"],
    },
}


@dataclasses.dataclass
class CriterionScore:
    name: str
    score: int
    comment: str


@dataclasses.dataclass
class JudgeResult:
    overall_score: int
    passed: bool
    criteria: list[CriterionScore]
    rationale: str
    error: str | None = None


def _build_prompt(
    *, user_message: str, reply: str, scenario_description: str, rubric: list[str]
) -> str:
    criteria_block = "\n".join(f"- {c}" for c in rubric)
    return (
        "You are a strict evaluator of a longevity-guidance agent called the "
        '"Future Self". Score the assistant REPLY against the rubric. Be critical; '
        "reserve a 5 for genuinely excellent replies.\n\n"
        f"SCENARIO:\n{scenario_description}\n\n"
        f"USER MESSAGE:\n{user_message}\n\n"
        f"REPLY:\n{reply}\n\n"
        f"RUBRIC:\n{criteria_block}\n\n"
        "Call submit_evaluation with a 1-5 score per rubric item, an overall_score, "
        "and a brief rationale."
    )


def judge_reply(
    *,
    user_message: str,
    reply: str,
    scenario_description: str = "",
    rubric: list[str] | None = None,
    model: str | None = None,
    _client: Any | None = None,
) -> JudgeResult:
    """Score a single reply with an LLM judge.

    Args:
        user_message: The user's message for this turn.
        reply: The Future Self reply to grade.
        scenario_description: Context for the judge (the scenario's description).
        rubric: Criteria to score against. Defaults to :data:`DEFAULT_RUBRIC`.
        model: Judge model. Defaults to ``JUDGE_MODEL`` env or ``claude-opus-4-8``.
        _client: Injected Anthropic-style client (testing — skips real API).

    Returns:
        A :class:`JudgeResult`. Never raises — failures degrade to ``score=0``
        with ``error`` populated.
    """
    rubric = rubric or DEFAULT_RUBRIC
    model = model or os.getenv("JUDGE_MODEL", "claude-opus-4-8")
    prompt = _build_prompt(
        user_message=user_message,
        reply=reply,
        scenario_description=scenario_description,
        rubric=rubric,
    )

    try:
        client = _client
        if client is None:
            import anthropic  # noqa: PLC0415

            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        response = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "submit_evaluation"},
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extract_tool_input(response)
    except Exception as exc:  # noqa: BLE001 — judging must never crash the run
        return JudgeResult(0, False, [], "", error=f"{type(exc).__name__}: {exc}")

    return _parse(data)


def _extract_tool_input(response: Any) -> dict[str, Any]:
    """Pull the forced tool-call input dict out of a Messages response."""
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use":
            return dict(getattr(block, "input", {}) or {})
    raise ValueError("no tool_use block in judge response")


def _parse(data: dict[str, Any]) -> JudgeResult:
    """Convert raw judge output into a JudgeResult, degrading to safe defaults."""
    try:
        overall = int(data["overall_score"])
        criteria = [
            CriterionScore(
                name=str(c.get("name", "")),
                score=int(c.get("score", 0)),
                comment=str(c.get("comment", "")),
            )
            for c in data.get("criteria", [])
        ]
        return JudgeResult(
            overall_score=overall,
            passed=overall >= _PASS_THRESHOLD,
            criteria=criteria,
            rationale=str(data.get("rationale", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        return JudgeResult(0, False, [], "", error=f"malformed judge output: {exc}")
