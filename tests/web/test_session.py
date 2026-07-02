"""Tests for the DB-backed session layer (``futureself.web.session``)."""
from __future__ import annotations

from starlette.requests import Request

from futureself.schemas import BioData, ConversationTurn, UserBlueprint
from futureself.web.session import (
    append_messages,
    create_session,
    get_blueprint_from_bearer,
    get_recent_messages,
    get_token_from_bearer,
    get_user_id_from_token,
    save_blueprint,
)


def _request_with_bearer(token: str | None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {"type": "http", "headers": headers}
    return Request(scope)


async def test_create_session_returns_usable_token(db):
    token = await create_session(db, UserBlueprint())
    assert isinstance(token, str)
    assert len(token) >= 30

    # Token can be resolved back to its blueprint.
    request = _request_with_bearer(token)
    blueprint = await get_blueprint_from_bearer(request, db)
    assert blueprint is not None
    assert isinstance(blueprint, UserBlueprint)


async def test_create_session_persists_seed_blueprint(db):
    seed = UserBlueprint(bio=BioData(age=42), inferred_facts=["User is 42"])
    token = await create_session(db, seed)

    blueprint = await get_blueprint_from_bearer(_request_with_bearer(token), db)
    assert blueprint.bio.age == 42
    assert blueprint.inferred_facts == ["User is 42"]


async def test_get_blueprint_returns_none_for_missing_token(db):
    result = await get_blueprint_from_bearer(_request_with_bearer("nope"), db)
    assert result is None


async def test_get_blueprint_returns_none_without_auth_header(db):
    result = await get_blueprint_from_bearer(_request_with_bearer(None), db)
    assert result is None


async def test_get_token_validates_against_session_store(db):
    token = await create_session(db, UserBlueprint())

    assert await get_token_from_bearer(_request_with_bearer(token), db) == token
    assert await get_token_from_bearer(_request_with_bearer("bogus"), db) is None


async def test_save_blueprint_updates_persisted_row(db):
    token = await create_session(db, UserBlueprint())

    updated = UserBlueprint(bio=BioData(age=50), inferred_facts=["User is 50"])
    await save_blueprint(token, updated, db)

    refreshed = await get_blueprint_from_bearer(_request_with_bearer(token), db)
    assert refreshed.bio.age == 50
    assert refreshed.inferred_facts == ["User is 50"]


async def test_save_blueprint_is_noop_for_unknown_token(db):
    # Should not raise even if the token doesn't exist.
    await save_blueprint("does-not-exist", UserBlueprint(), db)


# ---------------------------------------------------------------------------
# Message store (transcript, decoupled from the Blueprint)
# ---------------------------------------------------------------------------


async def _user_id_for(token: str, db):
    return await get_user_id_from_token(_request_with_bearer(token), db)


async def test_append_and_get_recent_messages_windowed(db):
    token = await create_session(db, UserBlueprint())
    user_id = await _user_id_for(token, db)

    await append_messages(db, user_id, [
        ConversationTurn(role="user", content="m1"),
        ConversationTurn(role="assistant", content="r1"),
    ])
    await append_messages(db, user_id, [ConversationTurn(role="user", content="m2")])

    # Last 2, returned oldest→newest.
    recent = await get_recent_messages(db, user_id, 2)
    assert [(t.role, t.content) for t in recent] == [("assistant", "r1"), ("user", "m2")]


async def test_get_recent_messages_orders_oldest_to_newest(db):
    token = await create_session(db, UserBlueprint())
    user_id = await _user_id_for(token, db)

    await append_messages(
        db, user_id, [ConversationTurn(role="user", content=f"m{i}") for i in range(5)]
    )
    recent = await get_recent_messages(db, user_id, 10)
    assert [t.content for t in recent] == ["m0", "m1", "m2", "m3", "m4"]


async def test_messages_isolated_per_user(db):
    t1 = await create_session(db, UserBlueprint())
    t2 = await create_session(db, UserBlueprint())
    u1, u2 = await _user_id_for(t1, db), await _user_id_for(t2, db)

    await append_messages(db, u1, [ConversationTurn(role="user", content="secret")])
    assert await get_recent_messages(db, u2, 10) == []
