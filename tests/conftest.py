"""Shared pytest fixtures for FutureSelf tests."""
from __future__ import annotations

import pytest

from futureself.schemas import (
    BioData,
    ContextData,
    PsychData,
    UserBlueprint,
)


@pytest.fixture
def blank_blueprint() -> UserBlueprint:
    """A fully empty UserBlueprint."""
    return UserBlueprint()


@pytest.fixture
def sample_blueprint() -> UserBlueprint:
    """A realistic UserBlueprint for scenario testing."""
    return UserBlueprint(
        bio=BioData(age=34, conditions=[]),
        psych=PsychData(goals=["adventure", "community"], stress_level="medium"),
        context=ContextData(occupation="software engineer", income_usd_annual=95000),
    )
