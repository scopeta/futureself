"""Curator v1 — deterministic context-quality policy (no LLM, no second agent).

The Curator's job is keeping the *context* the Future Self reasons over fresh
and high-quality: prompting a fact review when the transcript grows, flagging
measurements that are stale per recommended retest protocols, and pointing out
high-value Blueprint gaps. In v1 all of that is **rules** — cheap, predictable,
testable. Its output is neutral UI copy surfaced by the frontend, never a second
persona speaking to the user (single-voice rule, AGENTS.md). The documented
evolution path (spec §11.36) adds an off-turn LLM pass (v2) and an A2A consult
of the Future Self (v3) only when these rules demonstrably fall short.

Nudge ids are stable so the UI can dismiss them durably:
- ``facts:<bucket>``       — reappears every ``FUTURESELF_FACT_REVIEW_EVERY`` turns
- ``stale:<marker>:<date>`` — clears itself when a newer measurement is added
- ``gap:<field>``           — one-time per missing field
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from futureself.blueprint_quality import check_quality
from futureself.schemas import UserBlueprint

# Recommended retest intervals in months, by normalized marker name. Anything
# not listed falls back to _DEFAULT_RETEST_MONTHS. Intervals follow common
# adult-wellness protocols (semiannual glycemic control, annual panels).
RETEST_PROTOCOLS_MONTHS: dict[str, int] = {
    "hba1c": 6,
    "fasting glucose": 12,
    "glucose": 12,
    "ldl": 12,
    "hdl": 12,
    "total cholesterol": 12,
    "triglycerides": 12,
    "apob": 12,
    "testosterone": 12,
    "vitamin d": 12,
    "vitamin_d": 12,
    "tsh": 12,
    "ferritin": 12,
    "crp": 12,
    "hs-crp": 12,
    "creatinine": 12,
}
_DEFAULT_RETEST_MONTHS = 12

_MAX_NUDGES = 3


@dataclass
class Nudge:
    """One curator suggestion, rendered as neutral copy by the UI."""

    id: str
    kind: Literal["facts_review", "stale_test", "gap"]
    message: str
    action: Literal["review_facts", "blueprint"]


def _fact_review_every() -> int:
    return int(os.getenv("FUTURESELF_FACT_REVIEW_EVERY", "30"))


def _months_since(iso_date: str, today: date) -> int | None:
    """Whole months between an ISO date and today; None if unparseable."""
    try:
        then = datetime.fromisoformat(iso_date).date()
    except ValueError:
        return None
    return (today.year - then.year) * 12 + (today.month - then.month)


def curate(
    blueprint: UserBlueprint, message_count: int, today: date | None = None
) -> list[Nudge]:
    """Compute the current nudges for a user. Pure; safe on any Blueprint."""
    today = today or date.today()
    nudges: list[Nudge] = []

    # 1. Transcript growth → suggest the distill→confirm→prune cycle (§11.1).
    every = _fact_review_every()
    if every > 0 and message_count >= every:
        bucket = message_count // every
        nudges.append(
            Nudge(
                id=f"facts:{bucket}",
                kind="facts_review",
                message=(
                    "Your conversation is getting long. Review & save the durable "
                    "facts, then prune the history — nothing important gets lost."
                ),
                action="review_facts",
            )
        )

    # 2. Stale measurements per retest protocol (latest data point per marker).
    latest: dict[str, str] = {}
    for entry in blueprint.bio.biomarker_history:
        key = entry.marker.strip().lower()
        if key not in latest or entry.date > latest[key]:
            latest[key] = entry.date
    for key, last_date in sorted(latest.items()):
        months = _months_since(last_date, today)
        if months is None:
            continue
        interval = RETEST_PROTOCOLS_MONTHS.get(key, _DEFAULT_RETEST_MONTHS)
        if months >= interval:
            pretty = key.replace("_", " ").title()
            nudges.append(
                Nudge(
                    id=f"stale:{key}:{last_date}",
                    kind="stale_test",
                    message=(
                        f"Your last {pretty} measurement is from {last_date} — "
                        f"recommended retest interval is {interval} months. "
                        "A fresh data point sharpens the guidance."
                    ),
                    action="blueprint",
                )
            )

    # 3. High-value Blueprint gaps (reuse the quality checker's missing flags).
    _GAP_COPY = {
        "psych.goals": "Add a goal or two — guidance gets much sharper with a target.",
        "bio.age": "Adding your age helps calibrate every recommendation.",
        "bio.sex": "Adding your sex improves biomarker reference ranges.",
        "bio.height_weight": "Height and weight unlock body-composition guidance.",
        "context.location_country": "Your country shapes healthcare and environment advice.",
    }
    for flag in check_quality(blueprint).flags:
        if flag.severity == "missing" and flag.field in _GAP_COPY:
            nudges.append(
                Nudge(
                    id=f"gap:{flag.field}",
                    kind="gap",
                    message=_GAP_COPY[flag.field],
                    action="blueprint",
                )
            )

    # Priority: facts_review > stale_test > gap (list is built in that order).
    return nudges[:_MAX_NUDGES]
