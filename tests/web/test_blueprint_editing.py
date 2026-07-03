"""Tests for Blueprint editability: partial-merge PATCH + biomarker time series."""
from __future__ import annotations


async def _session(client) -> dict:
    r = await client.post("/api/session/create")
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


LDL_JAN = {"marker": "LDL", "value": 120, "unit": "mg/dL", "date": "2026-01-05", "source": None}
LDL_JUN = {"marker": "LDL", "value": 104, "unit": "mg/dL", "date": "2026-06-20", "source": "lab"}
TESTO = {"marker": "Testosterone", "value": 550, "unit": "ng/dL", "date": "2026-03-10", "source": None}


# ---------------------------------------------------------------------------
# Partial-merge PATCH (the old replace semantics wiped sibling fields)
# ---------------------------------------------------------------------------


async def test_patch_bio_preserves_biomarkers(client):
    h = await _session(client)
    await client.post("/api/blueprint/biomarkers", json=LDL_JAN, headers=h)

    # Onboarding-style partial patch — must NOT wipe biomarker_history.
    r = await client.patch("/api/blueprint/bio", json={"age": 41, "sex": "F"}, headers=h)
    bio = r.json()["bio"]
    assert bio["age"] == 41
    assert len(bio["biomarker_history"]) == 1


async def test_patch_psych_preserves_other_fields(client):
    h = await _session(client)
    await client.patch("/api/blueprint/psych", json={"goals": ["live to 100"]}, headers=h)
    r = await client.patch("/api/blueprint/psych", json={"stress_level": "low"}, headers=h)
    psych = r.json()["psych"]
    assert psych["goals"] == ["live to 100"]
    assert psych["stress_level"] == "low"


async def test_patch_context_preserves_other_fields(client):
    h = await _session(client)
    await client.patch("/api/blueprint/context", json={"occupation": "engineer"}, headers=h)
    r = await client.patch("/api/blueprint/context", json={"location_country": "SG"}, headers=h)
    ctx = r.json()["context"]
    assert ctx["occupation"] == "engineer"
    assert ctx["location_country"] == "SG"


async def test_patch_bio_invalid_field_type_422(client):
    h = await _session(client)
    r = await client.patch("/api/blueprint/bio", json={"age": "not-a-number"}, headers=h)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Biomarkers as data points over time
# ---------------------------------------------------------------------------


async def test_biomarker_measurements_accumulate_per_marker(client):
    # New measurement of an existing marker = another dated data point.
    h = await _session(client)
    await client.post("/api/blueprint/biomarkers", json=LDL_JAN, headers=h)
    await client.post("/api/blueprint/biomarkers", json=TESTO, headers=h)
    r = await client.post("/api/blueprint/biomarkers", json=LDL_JUN, headers=h)

    history = r.json()["bio"]["biomarker_history"]
    ldl = [e for e in history if e["marker"] == "LDL"]
    assert len(history) == 3
    assert [e["date"] for e in ldl] == ["2026-01-05", "2026-06-20"]


async def test_put_biomarkers_edits_and_deletes(client):
    h = await _session(client)
    for entry in (LDL_JAN, LDL_JUN, TESTO):
        await client.post("/api/blueprint/biomarkers", json=entry, headers=h)

    # Edit the June LDL value and delete the testosterone entry.
    edited = {**LDL_JUN, "value": 99.0}
    r = await client.put("/api/blueprint/biomarkers", json=[LDL_JAN, edited], headers=h)
    assert r.status_code == 200
    history = r.json()["bio"]["biomarker_history"]
    assert len(history) == 2
    assert history[1]["value"] == 99.0
    assert all(e["marker"] == "LDL" for e in history)


async def test_put_biomarkers_preserves_rest_of_bio(client):
    h = await _session(client)
    await client.patch("/api/blueprint/bio", json={"age": 50}, headers=h)
    r = await client.put("/api/blueprint/biomarkers", json=[LDL_JAN], headers=h)
    assert r.json()["bio"]["age"] == 50
