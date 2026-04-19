"""Foundry Hosted Agent Service entrypoint.

Wraps the FutureSelf ChatAgent with the Azure AI Agent Server hosting
adapter, which starts an HTTP server on :8088 compatible with the
Foundry Agent Service Responses API.

Usage (local testing):
    python main.py

Usage (Foundry hosted deployment):
    Configured via Dockerfile CMD / azd agent manifest startupCommand.

NOTE: Requires azure-ai-agentserver-agentframework (not yet on public PyPI).
      See AGENTS.md "Cloud Deployment / Target" for current status.
"""
from __future__ import annotations

import os
from pathlib import Path

from agent_framework import Agent, SkillsProvider
from agent_framework_anthropic import AnthropicClient

_SKILLS_DIR = Path(__file__).parent / "src" / "futureself" / "skills"
_ORCHESTRATOR_PROMPT = (
    Path(__file__).parent / "prompts" / "orchestrator.md"
).read_text(encoding="utf-8")


def build_agent() -> object:
    """Build the FutureSelf ChatAgent using current MAF API.

    Uses AnthropicClient (Anthropic direct) when ANTHROPIC_API_KEY is set,
    or FoundryChatClient when AZURE_FOUNDRY_ENDPOINT is set — same selection
    logic as orchestrator.py._build_agent().
    """
    model = os.environ["FUTURESELF_MODEL"]
    skills_provider = SkillsProvider(skill_paths=_SKILLS_DIR)

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
        api_key = os.environ["ANTHROPIC_API_KEY"]
        client = AnthropicClient(api_key=api_key, model=model)

    return Agent(
        client,
        instructions=_ORCHESTRATOR_PROMPT,
        name="FutureSelf",
        context_providers=[skills_provider],
    )


if __name__ == "__main__":
    from azure.ai.agentserver.agentframework import from_agent_framework  # noqa: PLC0415

    from_agent_framework(build_agent()).run()
