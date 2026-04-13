"""Live scenario tests — parametrised across all YAML scenario files.

These make real LLM API calls and are skipped by default.
Run with:  uv run pytest tests/scenarios/ -m live -v
Requires:  AZURE_FOUNDRY_ENDPOINT env var (and Azure credentials).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

load_dotenv()

from futureself.eval import evaluate_turn  # noqa: E402
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
    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    blueprint = UserBlueprint.from_dict(scenario.get("user_blueprint", {}))

    for i, turn in enumerate(scenario.get("turns", []), start=1):
        user_msg = turn["user_message"].strip()
        result = await run_turn(blueprint, user_msg)

        # Hard assertions — must always hold
        assert result.user_facing_reply, "Agent produced an empty reply"

        # Structured evaluation
        turn_eval = evaluate_turn(scenario["name"], i, turn, result)

        print(
            f"  [EVAL] {scenario['name']} turn {i}: "
            f"reply={turn_eval.reply_length} chars, latency={turn_eval.latency_ms:.0f}ms"
        )

        # Carry forward
        blueprint = result.updated_blueprint
