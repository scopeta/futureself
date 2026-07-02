"""Client for the deployed FutureSelf hosted agent (Foundry Responses endpoint).

After the cutover (spec §11), the BFF no longer runs the agent in-process. It
delegates synthesis to the **single** agent definition built by
``orchestrator.build_agent`` and deployed via ``main.py`` (the Foundry Responses
host), and remains the system of record for the Postgres-backed Blueprint.

The Foundry agent Responses endpoint is **stateless** per external caller —
end-user conversation isolation isn't offered yet (see the Foundry "agent
applications" docs). So the BFF sends the full per-turn context (profile + known
facts + recent history + message) on every call and persists conversation
history itself; ``store=False`` keeps the endpoint stateless.

Auth: Microsoft Entra (Azure RBAC) — the caller identity (managed identity in
production, ``az login`` locally) needs the **Foundry User** role on the agent
resource. No API key path is supported by the endpoint.
"""
from __future__ import annotations

import os
from functools import lru_cache

from futureself.schemas import ConversationTurn, UserBlueprint

# Entra scope for the Foundry data plane (services.ai.azure.com).
_SCOPE = "https://ai.azure.com/.default"

# Recent-turns window sent to the (stateless) agent each turn. Bounds per-turn
# tokens; the full transcript stays in the ``messages`` store.
_HISTORY_WINDOW = int(os.getenv("FUTURESELF_HISTORY_WINDOW", "10"))


@lru_cache(maxsize=1)
def _client() -> object:
    """Build (once) the async OpenAI client pointed at the hosted agent endpoint.

    Cached so the credential and HTTP connection pool are reused across turns.
    Cloud SDKs are imported lazily so unrelated code paths don't need them.

    Raises:
        ValueError: If ``FOUNDRY_AGENT_ENDPOINT`` is not configured.
    """
    from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415
    from openai import AsyncOpenAI  # noqa: PLC0415

    endpoint = os.getenv("FOUNDRY_AGENT_ENDPOINT", "").rstrip("/")
    if not endpoint:
        raise ValueError(
            "FOUNDRY_AGENT_ENDPOINT is required — the hosted agent's Responses "
            "base URL, e.g. https://<resource>.services.ai.azure.com/api/projects/"
            "<project>/agents/<agent>/endpoint/protocols/openai"
        )
    api_version = os.getenv("FOUNDRY_AGENT_API_VERSION", "v1")
    credential = DefaultAzureCredential()

    async def _token() -> str:
        # azure-identity caches the token and refreshes only when near expiry,
        # so resolving per request is cheap.
        return (await credential.get_token(_SCOPE)).token

    return AsyncOpenAI(
        api_key=_token,
        base_url=endpoint,
        default_query={"api-version": api_version},
    )


def build_user_context(
    blueprint: UserBlueprint,
    recent_messages: list[ConversationTurn],
    user_message: str,
) -> str:
    """Render the per-turn context block sent to the (stateless) hosted agent.

    Bounded and non-redundant: the profile is durable domain state only (the
    transcript is **not** dumped inside it), known facts render once, and the
    recent-turns window is supplied by the caller from the ``messages`` store.
    """
    history_lines = [f"{turn.role.upper()}: {turn.content}" for turn in recent_messages]

    facts_section = (
        "\n\nKNOWN FACTS ABOUT USER:\n" + "\n".join(f"- {f}" for f in blueprint.inferred_facts)
        if blueprint.inferred_facts
        else ""
    )
    history_section = (
        "\n\nCONVERSATION HISTORY:\n" + "\n".join(history_lines)
        if history_lines
        else ""
    )

    return (
        f"USER PROFILE:\n{blueprint.model_dump_json(indent=2)}"
        f"{facts_section}"
        f"{history_section}"
        f"\n\nUSER MESSAGE:\n{user_message}"
    )


async def synthesize(
    blueprint: UserBlueprint,
    recent_messages: list[ConversationTurn],
    user_message: str,
) -> str:
    """Run one turn against the hosted agent and return the reply text.

    Builds the bounded context block, calls the stateless Responses endpoint, and
    returns ``output_text``. Raises on transport/API errors — the caller maps
    them to a retryable 503.
    """
    client = _client()
    response = await client.responses.create(
        input=build_user_context(blueprint, recent_messages, user_message),
        store=False,  # stateless endpoint; the BFF owns conversation history
    )
    return response.output_text or ""
