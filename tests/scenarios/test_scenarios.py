"""Live scenario tests — the evaluator-as-reviewer gate.

These make real LLM API calls and are skipped by default. They run the agent
against each ``scenarios/*.yaml`` and apply two layers:

- **Deterministic assertions** (``expect`` block) — objective, repeatable;
  these are HARD failures.
- **LLM-as-judge** (``futureself.judge``) — rubric scoring; advisory, but a
  score below ``JUDGE_FLOOR`` (default 3/5) fails to catch egregious regressions.

Run with:  uv run pytest tests/scenarios/ -m live -v
Requires:  FOUNDRY_AGENT_ENDPOINT + Azure auth (az login / managed identity with
           the Foundry User role) to reach the deployed hosted agent, and
           ANTHROPIC_API_KEY for the LLM-as-judge.
Optional:  JUDGE_MODEL (default claude-opus-4-8), JUDGE_FLOOR (default 3).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

load_dotenv()

from futureself import judge  # noqa: E402
from futureself.eval import check_expectations  # noqa: E402
from futureself.schemas import ConversationTurn, UserBlueprint  # noqa: E402
from futureself.web.agent_client import synthesize  # noqa: E402

SCENARIO_DIR = Path(__file__).parent.parent.parent / "scenarios"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.yaml"))
_JUDGE_FLOOR = int(os.getenv("JUDGE_FLOOR", "3"))


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario_path",
    SCENARIO_FILES,
    ids=[p.stem for p in SCENARIO_FILES],
)
async def test_scenario(scenario_path: Path) -> None:
    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    blueprint = UserBlueprint.from_dict(scenario.get("user_blueprint", {}))
    rubric = judge.DEFAULT_RUBRIC + list(scenario.get("rubric", []))
    recent_messages: list[ConversationTurn] = []

    for i, turn in enumerate(scenario.get("turns", []), start=1):
        user_msg = turn["user_message"].strip()
        reply = await synthesize(blueprint, recent_messages, user_msg)

        # --- Hard gate: deterministic assertions ---
        assertions = check_expectations(reply, turn.get("expect"))
        failures = [f"{a.name} ({a.detail})" for a in assertions if not a.passed]
        assert not failures, (
            f"{scenario['name']} turn {i} failed assertions: {failures}\n"
            f"reply: {reply[:300]}"
        )

        # --- Advisory gate: LLM-as-judge ---
        verdict = judge.judge_reply(
            user_message=user_msg,
            reply=reply,
            scenario_description=scenario.get("description", ""),
            rubric=rubric,
        )
        print(
            f"  [JUDGE] {scenario['name']} turn {i}: "
            f"overall={verdict.overall_score}/5 passed={verdict.passed} "
            f"err={verdict.error}"
        )
        for c in verdict.criteria:
            print(f"          - {c.name}: {c.score}/5 — {c.comment}")
        if verdict.error is None:
            assert verdict.overall_score >= _JUDGE_FLOOR, (
                f"{scenario['name']} turn {i} judge score "
                f"{verdict.overall_score} < floor {_JUDGE_FLOOR}: {verdict.rationale}"
            )

        recent_messages = (
            recent_messages
            + [
                ConversationTurn(role="user", content=user_msg),
                ConversationTurn(role="assistant", content=reply),
            ]
        )[-20:]
