"""
Sub-agent base class for JARVIS multi-agent architecture.

Architecture
------------
User → Jarvis (orchestrator / planner)
           ↓  delegates via SubAgentTask
       SubAgent (specialized worker)
           ↓  returns SubAgentResult
       Jarvis (synthesizes + replies to user)

Each sub-agent:
  - Has a name, description, and capability list
  - Accepts a SubAgentTask (goal + context)
  - Runs its own focused tool loop (no user-facing language)
  - Returns a SubAgentResult with summary + structured data

Sub-agents do NOT talk to the user directly — only Jarvis does.
Sub-agents do NOT spawn other sub-agents — only Jarvis delegates.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class SubAgentTask:
    """
    A unit of work handed from Jarvis to a sub-agent.

    Attributes
    ----------
    goal        Human-readable description of what needs to be done.
    context     Optional dict of supporting data (e.g. file paths, search
                terms, prior results) the sub-agent can use.
    timeout     Max seconds the sub-agent may run before being cancelled.
    task_id     Unique ID for tracking and logging.
    """
    goal: str
    context: dict[str, Any] = field(default_factory=dict)
    timeout: float = 120.0
    task_id: str = ""

    def __post_init__(self):
        if not self.task_id:
            import uuid
            self.task_id = str(uuid.uuid4())[:8]


@dataclass
class SubAgentResult:
    """
    The outcome returned by a sub-agent to Jarvis.

    Attributes
    ----------
    success     Whether the task completed without errors.
    summary     A concise natural-language summary of what was done and found.
                Jarvis will include this verbatim (or paraphrase it) in its
                reply to the user.
    data        Structured output — tool results, extracted values, file paths,
                search hits, etc.  Jarvis can query specific keys from this.
    error       Error message if success=False.
    tool_calls  Log of every tool call made (for audit/transparency).
    elapsed_s   Wall-clock seconds the sub-agent ran.
    agent_name  Name of the sub-agent that produced this result.
    """
    success: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    elapsed_s: float = 0.0
    agent_name: str = ""


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class SubAgentBase:
    """
    Abstract base class for all JARVIS sub-agents.

    Subclasses must:
      - Set `name` (unique, kebab-case, e.g. "research")
      - Set `description` (one sentence, shown to Jarvis during routing)
      - Set `capabilities` (list of tool names this agent primarily uses)
      - Implement `run(task) -> SubAgentResult`

    Subclasses should NOT:
      - Print to stdout (use logger)
      - Call ollama_client directly (use the provided execute_fn / helper methods)
      - Spawn other sub-agents
    """

    name: str = "base"
    description: str = "Base sub-agent (not meant to be used directly)"
    capabilities: list[str] = []

    def __init__(self, execute_fn=None, verify_fn=None):
        """
        Parameters
        ----------
        execute_fn  The safety-gated tool executor from the orchestrator.
                    Signature: execute_fn(tool_name: str, args: dict) -> dict
        verify_fn   The post-execution verifier.
                    Signature: verify_fn(tool_name: str, result: dict, goal: str) -> dict
        """
        self._execute = execute_fn
        self._verify = verify_fn
        self._log = logging.getLogger(f"subagent.{self.name}")

    def run(self, task: SubAgentTask) -> SubAgentResult:
        """
        Entry point. Override this in subclasses.

        The base implementation raises NotImplementedError — subclasses must
        provide their own focused tool loop.
        """
        raise NotImplementedError(f"SubAgent '{self.name}' has not implemented run()")

    # ------------------------------------------------------------------
    # Helper methods available to all subclasses
    # ------------------------------------------------------------------

    def _tool(self, tool_name: str, **kwargs) -> dict:
        """
        Call a tool through the safety-gated executor.

        Returns the tool result dict. Logs the call and any failure.
        """
        if self._execute is None:
            raise RuntimeError(
                f"SubAgent '{self.name}' has no execute_fn — "
                "was it initialized by the orchestrator?"
            )
        self._log.info(f"tool: {tool_name}({list(kwargs.keys())})")
        result = self._execute(tool_name, kwargs)
        if not result.get("success"):
            self._log.warning(f"tool {tool_name} failed: {result.get('error', '?')[:200]}")
        return result

    def _tool_ok(self, tool_name: str, **kwargs) -> tuple[bool, dict]:
        """
        Convenience wrapper: call a tool and return (success, result).

        Unwraps the safety executor envelope so sub-agents see raw tool keys
        (answer, elements, text, fallback, etc.) instead of an empty outer dict.
        """
        result = self._tool(tool_name, **kwargs)
        ok = result.get("success", False)
        data = result.get("data", result)  # safety envelope nests keys under "data"
        return ok, data

    def _summarize_result(self, results: list[dict]) -> str:
        """
        Build a short plaintext summary from a list of tool results.
        Subclasses can override for domain-specific formatting.
        """
        lines = []
        for r in results:
            tool = r.get("tool", "?")
            ok = r.get("success", False)
            if ok:
                content = (
                    r.get("content")
                    or r.get("output")
                    or r.get("status")
                    or r.get("answer")
                    or "ok"
                )
                lines.append(f"[{tool}] {str(content)[:200]}")
            else:
                lines.append(f"[{tool}] FAILED: {r.get('error', '?')[:150]}")
        return "\n".join(lines) if lines else "No results."

    def info(self) -> dict:
        """Return a description dict for Jarvis's routing table."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
        }
