"""Foundry Hosted Agent entrypoint.

Wraps the FutureSelf ChatAgent with the Azure AI Agent Server hosting
adapter, which starts an HTTP server on :8088 compatible with the
Foundry Agent Service Responses API.

Usage (local testing):
    python main.py

Usage (Foundry hosted deployment):
    Configured via Dockerfile CMD / azd agent manifest startupCommand.
"""
from __future__ import annotations

import os

from agent_framework import SkillsProvider
from agent_framework.azure import AzureAIAgentClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity import DefaultAzureCredential
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent / "src" / "futureself" / "skills"
_ORCHESTRATOR_PROMPT = (
    Path(__file__).parent / "prompts" / "orchestrator.md"
).read_text(encoding="utf-8")
_MODEL = "claude-opus-4-6"


def build_agent() -> object:
    """Build the FutureSelf ChatAgent."""
    skills_provider = SkillsProvider(skill_paths=_SKILLS_DIR)

    return AzureAIAgentClient(
        project_endpoint=os.environ["AZURE_FOUNDRY_ENDPOINT"],
        model_deployment_name=_MODEL,
        credential=DefaultAzureCredential(),
    ).as_agent(
        name="FutureSelf",
        instructions=_ORCHESTRATOR_PROMPT,
        context_providers=[skills_provider],
    )


if __name__ == "__main__":
    agent = build_agent()
    from_agent_framework(agent).run()
