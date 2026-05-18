"""
AgentRegistry — metadata store for every agent in the system.
Pure data: no logic, no base classes, no routing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from tools import TOOL_SCHEMAS, TOOL_DOMAINS, TOOL_STAGES

logger = logging.getLogger(__name__)


@dataclass
class AgentSpec:
    name: str
    description: str
    model: str
    prompt_template: str
    tools: list[str] | str         # list of tool names, or "__all__"
    capabilities: list[str]        # e.g. ["chat", "execute", "summarize"]
    temperature: float
    agent_class: str               # dotted path, e.g. "agents.director.JarvisAgent"


class AgentRegistry:
    _agents: dict[str, AgentSpec] = {}

    @classmethod
    def register(cls, spec: AgentSpec) -> None:
        cls._agents[spec.name] = spec
        logger.debug("AgentRegistry: registered '%s' (%s)", spec.name, spec.description)

    @classmethod
    def get(cls, name: str) -> AgentSpec | None:
        return cls._agents.get(name)

    @classmethod
    def get_all(cls) -> dict[str, AgentSpec]:
        return dict(cls._agents)

    @classmethod
    def get_by_capability(cls, capability: str) -> list[AgentSpec]:
        return [a for a in cls._agents.values() if capability in a.capabilities]

    @classmethod
    def get_info(cls) -> dict[str, Any]:
        """Return a dict of system-awareness data for prompt injection."""
        tool_count = len(TOOL_SCHEMAS)
        domain_counts: dict[str, int] = {}
        for s in TOOL_SCHEMAS:
            name = s["function"]["name"]
            domain = TOOL_DOMAINS.get(name, "other")
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        domain_lines = sorted(f"{d}: {c}" for d, c in domain_counts.items())

        agent_lines = []
        for spec in cls._agents.values():
            caps = ", ".join(spec.capabilities)
            agent_lines.append(f"  {spec.name}: {spec.description} [{caps}]")

        return {
            "tool_count": tool_count,
            "tool_domains": "\n".join(f"    {l}" for l in domain_lines),
            "agent_count": len(cls._agents),
            "agent_info": "\n".join(agent_lines),
        }


def register_defaults():
    """Register the default agents from settings."""
    from settings import AGENTS as agent_configs

    for name, cfg in agent_configs.items():
        spec = AgentSpec(name=name, **cfg)
        AgentRegistry.register(spec)
