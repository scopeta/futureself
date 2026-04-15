"""Rule-based blueprint data quality checks.

No LLM calls — purely deterministic logic.
Returns a QualityReport that the API and UI can surface to the user.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel

from futureself.schemas import UserBlueprint

_STALE_BIOMARKER_DAYS = 365  # flag biomarkers older than 12 months


class QualityFlag(BaseModel):
    """A single quality issue."""

    field: str
    severity: Literal["missing", "stale", "low"]
    message: str


class QualityReport(BaseModel):
    """Aggregated quality report for a UserBlueprint."""

    score: int
    """0–100. Higher is better."""
    flags: list[QualityFlag]
    recommendations: list[str]


def check_quality(blueprint: UserBlueprint) -> QualityReport:
    """Run all quality checks and return a QualityReport.

    Args:
        blueprint: The user's current profile.

    Returns:
        QualityReport with score, flags, and recommendations.
    """
    flags: list[QualityFlag] = []

    # --- Bio completeness ---
    bio = blueprint.bio
    if bio.age is None:
        flags.append(QualityFlag(field="bio.age", severity="missing", message="Age is not set — personalisation will be limited."))
    if bio.sex is None:
        flags.append(QualityFlag(field="bio.sex", severity="missing", message="Sex is not set — some health recommendations may be less accurate."))
    if bio.height_cm is None or bio.weight_kg is None:
        flags.append(QualityFlag(field="bio.height_weight", severity="missing", message="Height or weight is missing — BMI and fitness advice will be generic."))

    # --- Context completeness ---
    ctx = blueprint.context
    if ctx.location_country is None:
        flags.append(QualityFlag(field="context.location_country", severity="missing", message="Country is not set — geopolitics and healthcare access advice cannot be personalised."))
    if ctx.occupation is None:
        flags.append(QualityFlag(field="context.occupation", severity="low", message="Occupation is not set — time management and financial advice may be less relevant."))

    # --- Goals ---
    if not blueprint.psych.goals:
        flags.append(QualityFlag(field="psych.goals", severity="missing", message="No goals defined — the agent cannot align advice with your priorities."))

    # --- Biomarker freshness ---
    today = date.today()
    for entry in bio.biomarker_history:
        try:
            entry_date = datetime.fromisoformat(entry.date).date()
        except (ValueError, AttributeError):
            continue
        age_days = (today - entry_date).days
        if age_days > _STALE_BIOMARKER_DAYS:
            flags.append(QualityFlag(
                field=f"bio.biomarker_history.{entry.marker}",
                severity="stale",
                message=f"{entry.marker} was last measured {age_days // 30} months ago — consider retesting.",
            ))

    # --- Conversation history ---
    if len(blueprint.conversation_history) == 0:
        flags.append(QualityFlag(field="conversation_history", severity="low", message="No conversation history yet — the agent will start fresh."))

    # Score: start at 100, deduct per flag
    deductions = {"missing": 15, "stale": 5, "low": 3}
    score = max(0, 100 - sum(deductions[f.severity] for f in flags))

    recommendations = _recommendations(flags)

    return QualityReport(score=score, flags=flags, recommendations=recommendations)


def _recommendations(flags: list[QualityFlag]) -> list[str]:
    recs: list[str] = []
    fields = {f.field for f in flags}
    if "bio.age" in fields or "bio.sex" in fields or "bio.height_weight" in fields:
        recs.append("Complete your basic bio (age, sex, height, weight) for personalised recommendations.")
    if "context.location_country" in fields:
        recs.append("Add your location to unlock geopolitics and healthcare access insights.")
    if "psych.goals" in fields:
        recs.append("Set at least one goal so your Future Self can guide you toward it.")
    stale = [f for f in flags if f.severity == "stale"]
    if stale:
        recs.append(f"Update {len(stale)} stale biomarker(s) with recent lab results.")
    return recs
