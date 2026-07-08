"""Tests for Curator v1 — rule-based context-quality nudges."""
from __future__ import annotations

from datetime import date

from futureself.schemas import BioData, BiomarkerEntry, ContextData, PsychData, UserBlueprint
from futureself.web.curator import curate

TODAY = date(2026, 7, 8)

FULL = UserBlueprint(
    bio=BioData(age=40, sex="M", height_cm=180, weight_kg=78),
    psych=PsychData(goals=["live well"]),
    context=ContextData(location_country="SG"),
)


def _bp_with_marker(marker: str, when: str) -> UserBlueprint:
    return FULL.model_copy(
        update={
            "bio": FULL.bio.model_copy(
                update={
                    "biomarker_history": [
                        BiomarkerEntry(marker=marker, value=1.0, unit="x", date=when, source=None)
                    ]
                }
            )
        }
    )


# ---------------------------------------------------------------------------
# Rule 1: transcript growth → fact review
# ---------------------------------------------------------------------------


def test_facts_review_fires_at_threshold(monkeypatch):
    monkeypatch.setenv("FUTURESELF_FACT_REVIEW_EVERY", "30")
    assert curate(FULL, 29, TODAY) == []
    nudges = curate(FULL, 30, TODAY)
    assert [n.kind for n in nudges] == ["facts_review"]
    assert nudges[0].action == "review_facts"


def test_facts_review_bucket_id_changes_each_cycle(monkeypatch):
    monkeypatch.setenv("FUTURESELF_FACT_REVIEW_EVERY", "30")
    first = curate(FULL, 35, TODAY)[0].id
    second = curate(FULL, 65, TODAY)[0].id
    assert first != second  # dismissing one bucket doesn't silence the next


def test_facts_review_disabled_with_zero(monkeypatch):
    monkeypatch.setenv("FUTURESELF_FACT_REVIEW_EVERY", "0")
    assert curate(FULL, 500, TODAY) == []


# ---------------------------------------------------------------------------
# Rule 2: retest protocols
# ---------------------------------------------------------------------------


def test_stale_marker_uses_protocol_interval():
    # HbA1c protocol = 6 months → 7-month-old measurement is stale.
    nudges = curate(_bp_with_marker("HbA1c", "2025-12-01"), 0, TODAY)
    assert [n.kind for n in nudges] == ["stale_test"]
    assert "6 months" in nudges[0].message
    assert nudges[0].action == "blueprint"


def test_fresh_marker_not_flagged():
    assert curate(_bp_with_marker("HbA1c", "2026-03-01"), 0, TODAY) == []


def test_only_latest_measurement_counts():
    bp = FULL.model_copy(
        update={
            "bio": FULL.bio.model_copy(
                update={
                    "biomarker_history": [
                        BiomarkerEntry(marker="LDL", value=120, unit="mg/dL", date="2024-01-01", source=None),
                        BiomarkerEntry(marker="LDL", value=104, unit="mg/dL", date="2026-06-20", source=None),
                    ]
                }
            )
        }
    )
    assert curate(bp, 0, TODAY) == []  # latest is fresh → no nudge


def test_stale_id_is_stable_per_measurement():
    n = curate(_bp_with_marker("Testosterone", "2025-01-15"), 0, TODAY)[0]
    assert n.id == "stale:testosterone:2025-01-15"


def test_malformed_date_ignored():
    assert curate(_bp_with_marker("LDL", "not-a-date"), 0, TODAY) == []


# ---------------------------------------------------------------------------
# Rule 3: blueprint gaps + prioritization
# ---------------------------------------------------------------------------


def test_gap_nudges_for_blank_blueprint():
    nudges = curate(UserBlueprint(), 0, TODAY)
    assert nudges and all(n.kind == "gap" for n in nudges)
    assert all(n.action == "blueprint" for n in nudges)


def test_capped_at_three_and_prioritized(monkeypatch):
    monkeypatch.setenv("FUTURESELF_FACT_REVIEW_EVERY", "10")
    bp = UserBlueprint(  # blank + stale marker + long transcript
        bio=BioData(
            biomarker_history=[
                BiomarkerEntry(marker="LDL", value=1, unit="x", date="2024-01-01", source=None)
            ]
        )
    )
    nudges = curate(bp, 50, TODAY)
    assert len(nudges) == 3
    assert nudges[0].kind == "facts_review"
    assert nudges[1].kind == "stale_test"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


async def test_nudges_endpoint(client):
    r = await client.post(
        "/api/auth/register", json={"email": "curator@example.com", "password": "password123"}
    )
    h = {"Authorization": f"Bearer {r.json()['session_token']}"}
    resp = await client.get("/api/curator/nudges", headers=h)
    assert resp.status_code == 200
    nudges = resp.json()["nudges"]
    # Blank blueprint → gap nudges with the documented shape.
    assert nudges and {"id", "kind", "message", "action"} <= set(nudges[0].keys())
