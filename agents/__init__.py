"""
Multi-agent architecture:
  - jarvis: conversation + high-level planning (LLM_MODEL)
  - execution: tool orchestration, validation, verification, retries (EXECUTOR_MODEL + runtime)
  - sub_agents: specialized workers that Jarvis delegates complex tasks to
"""

from agents.jarvis import run as jarvis_run
from agents.execution import (
    ExecutionAgent,
    run_plan,
    run_native_tool_calls,
    validate_tool_call,
)
from agents.base_agent import SubAgentBase, SubAgentTask, SubAgentResult
from agents.sub_agent_registry import registry as sub_agent_registry

# Auto-register all built-in sub-agents on import
import agents.sub_agents  # noqa: F401

__all__ = [
    "jarvis_run",
    "run_plan",
    "run_native_tool_calls",
    "validate_tool_call",
    "ExecutionAgent",
    "SubAgentBase",
    "SubAgentTask",
    "SubAgentResult",
    "sub_agent_registry",
]
