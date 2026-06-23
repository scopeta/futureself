"""Foundry Hosted Agent container entrypoint.

Exposes the FutureSelf agent via the Azure AI Responses protocol
(POST /responses) on Hypercorn. The Foundry Hosted Agents platform calls
this endpoint per user turn; this container is not browser-facing — the
React BFF still talks to FastAPI (see web/app.py), and will be cut over
to proxy this endpoint as part of futureself-spec.md §11 completion.

Local testing:
    python main.py        # 0.0.0.0:8088
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agent_framework import Agent, SkillsProvider
from agent_framework_anthropic import AnthropicClient
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

load_dotenv()

_SKILLS_DIR = Path(__file__).parent / "src" / "futureself" / "skills"
_ORCHESTRATOR_PROMPT = (
    Path(__file__).parent / "prompts" / "orchestrator.md"
).read_text(encoding="utf-8")


def build_agent() -> Agent:
    """Build the FutureSelf MAF Agent.

    Mirrors ``orchestrator._build_agent``: ``AZURE_FOUNDRY_ENDPOINT`` selects
    the Foundry chat client (model-agnostic, Entra auth); otherwise falls
    back to Anthropic direct via ``ANTHROPIC_API_KEY``.
    """
    model = os.environ["FUTURESELF_MODEL"]
    skills_provider = SkillsProvider.from_paths(_SKILLS_DIR)

    endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "")
    if endpoint:
        from agent_framework_foundry import FoundryChatClient  # noqa: PLC0415
        from azure.identity import DefaultAzureCredential  # noqa: PLC0415

        client = FoundryChatClient(
            project_endpoint=endpoint,
            model=model,
            credential=DefaultAzureCredential(),
        )
    else:
        client = AnthropicClient(
            api_key=os.environ["ANTHROPIC_API_KEY"], model=model
        )

    return Agent(
        client,
        instructions=_ORCHESTRATOR_PROMPT,
        name="FutureSelf",
        context_providers=[skills_provider],
    )


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
