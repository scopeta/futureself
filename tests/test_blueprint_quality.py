"""Tests for the rule-based blueprint quality checker."""
from __future__ import annotations

from datetime import date, timedelta

from futureself.blueprint_quality import QualityReport, check_quality
from futureself.schemas import (
    BioData,
    BiomarkerEntry,
    ContextData,
    ConversationTurn,
    PsychData,
    UserBlueprint,
)


def test_blank_blueprint_flags_all_missing():
    report = check_quality(UserBlueprint())

    assert isinstance(report, QualityReport)
    fields = {f.field for f in report.flags}
    assert "bio.age" in fields
    assert "bio.sex" in fields
    assert "bio.height_weight" in fields
    assert "context.location_country" in fields
    assert "psych.goals" in fields
    # Blank blueprint has no conversation → "low" flag fires.
    assert "conversation_history" in fields


def test_score_decreases_with_missing_fields():
    full = UserBlueprint(
        bio=BioData(age=30, sex="F", height_cm=170, weight_kg=65),
        psych=PsychData(goals=["longevity"]),
        context=ContextData(location_country="SG", occupation="engineer"),
        conversation_history=[ConversationTurn(role="user", content="hi")],
    )
    blank = UserBlueprint()

    assert check_quality(full).score > check_quality(blank).score
    # A fully populated blueprint has no flags at all.
    assert check_quality(full).flags == []
    assert check_quality(full).score == 100


def test_score_is_clamped_to_zero():
    # A totally empty blueprint with stale biomarkers shouldn't go negative.
    old_date = (date.today() - timedelta(days=800)).isoformat()
    bp = UserBlueprint(
        bio=BioData(
            biomarker_history=[
                BiomarkerEntry(marker=f"m{i}", value=1.0, unit="x", date=old_date, source=None)
                for i in range(10)
            ]
        )
    )
    report = check_quality(bp)
    assert report.score >= 0


def test_stale_biomarker_flagged():
    old_date = (date.today() - timedelta(days=400)).isoformat()
    bp = UserBlueprint(
        bio=BioData(
            biomarker_history=[
                BiomarkerEntry(marker="LDL", value=120, unit="mg/dL", date=old_date, source=None)
            ]
        )
    )
    report = check_quality(bp)
    assert any(f.severity == "stale" and "LDL" in f.field for f in report.flags)


def test_recent_biomarker_not_flagged():
    recent_date = (date.today() - timedelta(days=30)).isoformat()
    bp = UserBlueprint(
        bio=BioData(
            biomarker_history=[
                BiomarkerEntry(marker="LDL", value=120, unit="mg/dL", date=recent_date, source=None)
            ]
        )
    )
    report = check_quality(bp)
    assert not any(f.severity == "stale" for f in report.flags)


def test_malformed_biomarker_date_does_not_crash():
    bp = UserBlueprint(
        bio=BioData(
            biomarker_history=[
                BiomarkerEntry(marker="LDL", value=120, unit="mg/dL", date="not-a-date", source=None)
            ]
        )
    )
    # Should not raise; malformed date is silently ignored for the staleness check.
    report = check_quality(bp)
    assert not any(f.severity == "stale" for f in report.flags)


def test_recommendations_reference_flagged_fields():
    bp = UserBlueprint()
    report = check_quality(bp)
    recs_text = " ".join(report.recommendations).lower()
    assert "bio" in recs_text or "age" in recs_text
    assert "goal" in recs_text
