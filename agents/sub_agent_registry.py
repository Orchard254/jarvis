"""
Sub-agent registry for JARVIS.

Jarvis uses this to discover available sub-agents and route tasks to the
right one. Sub-agents register themselves at import time via `register()`.

Usage (in orchestrator or jarvis.py)
--------------------------------------
    from agents.sub_agent_registry import registry

    # List all available sub-agents (for system prompt injection)
    agents_info = registry.list_agents()

    # Route a task to the best sub-agent by keyword matching
    agent = registry.route("search the web for Python tutorials")

    # Or fetch by name directly
    agent = registry.get("research")

    # Run the task
    from agents.base_agent import SubAgentTask
    result = agent.run(SubAgentTask(goal="Find latest AI news", timeout=60))
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base_agent import SubAgentBase, SubAgentTask, SubAgentResult

logger = logging.getLogger(__name__)


class SubAgentRegistry:
    """Thread-safe registry of named sub-agents."""

    def __init__(self):
        self._agents: dict[str, "SubAgentBase"] = {}

    def register(self, agent: "SubAgentBase") -> None:
        """Add a sub-agent. Overwrites any existing agent with the same name."""
        self._agents[agent.name] = agent
        logger.info(f"SubAgentRegistry: registered '{agent.name}'")

    def get(self, name: str) -> "SubAgentBase | None":
        """Return a sub-agent by exact name, or None."""
        return self._agents.get(name)

    def list_agents(self) -> list[dict]:
        """Return info dicts for all registered sub-agents (for Jarvis's prompt)."""
        return [a.info() for a in self._agents.values()]

    def route(self, goal: str) -> "SubAgentBase | None":
        """
        Pick the best sub-agent for a given goal string using keyword matching.

        Scoring: each sub-agent gets +1 point per capability keyword that
        appears in the goal, +2 if the agent name itself appears. Returns the
        highest-scoring agent, or None if no agent scores above zero.

        This is intentionally simple. Jarvis's LLM can do smarter routing by
        naming the sub-agent explicitly in its BATCH_TOOL_PLAN.
        """
        goal_lower = goal.lower()
        scores: dict[str, int] = {}

        for name, agent in self._agents.items():
            score = 0
            if name in goal_lower:
                score += 2
            for cap in agent.capabilities:
                # Turn "web_search" → ["web", "search"] and check each word
                words = re.split(r"[_\-]", cap.lower())
                for word in words:
                    if word and len(word) > 3 and word in goal_lower:
                        score += 1
            scores[name] = score

        if not scores:
            return None

        best_name = max(scores, key=lambda k: scores[k])
        if scores[best_name] == 0:
            return None

        return self._agents[best_name]

    def inject_into_agents(self, execute_fn, verify_fn) -> None:
        """
        Inject the orchestrator's execute_fn and verify_fn into all registered
        sub-agents. Call this once after the orchestrator starts up.
        """
        for agent in self._agents.values():
            agent._execute = execute_fn
            agent._verify = verify_fn

    def describe_for_prompt(self) -> str:
        """
        Return a compact markdown table of sub-agents for injection into
        Jarvis's system prompt — so Jarvis knows what delegation options exist.
        """
        if not self._agents:
            return ""
        lines = [
            "## Available Sub-Agents",
            "Delegate complex tasks using `delegate_to_subagent` tool.\n",
            "| Agent | Capabilities | Description |",
            "|-------|-------------|-------------|",
        ]
        for agent in self._agents.values():
            caps = ", ".join(agent.capabilities[:6])
            lines.append(f"| `{agent.name}` | {caps} | {agent.description} |")
        return "\n".join(lines)


# Global singleton — import this everywhere
registry = SubAgentRegistry()


def register(agent: "SubAgentBase") -> None:
    """Module-level convenience wrapper for registry.register()."""
    registry.register(agent)
