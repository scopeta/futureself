"""Foundry Hosted Agent container entrypoint (optional Foundry on-ramp).

Exposes the FutureSelf agent via the Azure AI Responses protocol
(POST /responses) on Hypercorn for the Foundry Hosted Agents platform.

Topology (futureself-spec.md §11): the browser-facing React BFF (``web/app.py``)
owns orchestration in-process via ``orchestrator.run_turn`` — this is the
canonical path for the active Anthropic-direct deployment, and it keeps the
Postgres-backed Blueprint, conversation history, and fact extraction. This
Responses host is the *optional* Foundry path; the BFF only proxies it once
Foundry Agent Service manages thread memory (``FOUNDRY_PROJECT_ENDPOINT`` set).
Both paths build the identical agent via ``orchestrator.build_agent`` — one
source of truth, no drift.

Local testing:
    python main.py        # 0.0.0.0:8088
"""
from __future__ import annotations

import asyncio
import os

from azure.ai.agentserver.responses import (
    CreateResponse,
    FoundryStorageProvider,
    ResponseContext,
    ResponseProviderProtocol,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
    TextResponse,
)
from dotenv import load_dotenv

from futureself.orchestrator import build_agent

load_dotenv()


def _build_storage() -> ResponseProviderProtocol | None:
    """Return the response store, or ``None`` for in-memory fallback.

    Foundry sets ``FOUNDRY_PROJECT_ENDPOINT`` on deployed containers; when
    present, persist conversation history through Foundry storage so it
    survives compute scale-to-zero. Locally, returning ``None`` lets the
    host use ``InMemoryResponseProvider`` — sufficient for development.
    """
    if not os.getenv("FOUNDRY_PROJECT_ENDPOINT"):
        return None
    from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

    return FoundryStorageProvider(credential=DefaultAzureCredential())


def _format_history_item(item: object) -> str | None:
    """Best-effort ``ROLE: text`` extraction from a history item.

    Duck-typed so the formatter survives schema evolution in the beta SDK.
    """
    role = (getattr(item, "role", None) or "assistant").lower()
    content = getattr(item, "content", None) or []
    if not isinstance(content, list):
        return None
    texts = [t for t in (getattr(p, "text", None) for p in content) if isinstance(t, str) and t]
    if not texts:
        return None
    return f"{role.upper()}: {' '.join(texts)}"


_options = ResponsesServerOptions(default_fetch_history_count=20)
app = ResponsesAgentServerHost(options=_options, store=_build_storage())
_agent = build_agent()


@app.response_handler
async def handle_response(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
) -> TextResponse:
    """Per-turn handler: assemble platform history + current message, run the agent.

    Blueprint loading and fact extraction (``orchestrator.run_turn``) stay in
    the BFF until the Foundry isolation-key ↔ Postgres user_id binding lands
    (futureself-spec.md §11 + Phase 6.5). For now this handler runs the
    agent stateless against Foundry-managed conversation history.
    """
    user_message = await context.get_input_text()
    history_lines = [
        line for item in await context.get_history() if (line := _format_history_item(item))
    ]
    user_ctx = (
        "CONVERSATION HISTORY:\n"
        + "\n".join(history_lines)
        + f"\n\nUSER MESSAGE:\n{user_message}"
        if history_lines
        else user_message
    )

    session = _agent.create_session()
    result = await _agent.run(user_ctx, session=session)
    return TextResponse(context, request, text=result.text or "")


if __name__ == "__main__":
    app.run()
