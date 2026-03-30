"""Live scenario tests — parametrised across all YAML scenario files.

These make real LLM API calls and are skipped by default.
Run with:  uv run pytest tests/scenarios/ -m live -v
Requires:  LLM provider env vars (see .env.example).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

load_dotenv()

from futureself.llm.router import reset_router  # noqa: E402
from futureself.orchestrator import run_turn  # noqa: E402
from futureself.schemas import UserBlueprint  # noqa: E402

SCENARIO_DIR = Path(__file__).parent.parent.parent / "scenarios"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.yaml"))


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario_path",
    SCENARIO_FILES,
    ids=[p.stem for p in SCENARIO_FILES],
)
async def test_scenario(scenario_path: Path) -> None:
    reset_router()  # ensure env-based config is picked up fresh
    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    blueprint = UserBlueprint.from_dict(scenario.get("user_blueprint", {}))

    for turn in scenario.get("turns", []):
        user_msg = turn["user_message"].strip()
        result = await run_turn(blueprint, user_msg)

        # Hard assertions — must always hold
        assert result.user_facing_reply, "Synthesis produced an empty reply"
        assert len(result.agents_consulted) >= 1, "No agents were consulted"

        # Soft assertions — log mismatches for human review, don't fail
        expected_agents = turn.get("expected_agents_consulted")
        if expected_agents:
            actual = set(result.agents_consulted)
            expected = set(expected_agents)
            if actual != expected:
                print(
                    f"  [DIVERGENCE] {scenario['name']}: "
                    f"expected agents {expected}, got {actual}"
                )

        expect_conflict = turn.get("expect_conflict")
        if expect_conflict is not None and result.conflict_detected != expect_conflict:
            print(
                f"  [DIVERGENCE] {scenario['name']}: "
                f"expected conflict={expect_conflict}, "
                f"got conflict={result.conflict_detected}"
            )

        # Carry forward
        blueprint = result.updated_blueprint
