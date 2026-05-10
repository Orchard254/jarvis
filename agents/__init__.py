"""
Tier 3 Multi-Agent Collaborative System

This module implements a self-healing, multi-agent architecture with:
- Planner Agent: Breaks complex goals into dependency-aware steps
- Coder Agent: Generates safe, executable Python scripts
- Executor Agent: Handles tool interaction and error recovery
- Supervisor: Routes tasks and manages state across agents
- Dynamic Handoff: Tasks flow automatically between agents
- Shared Context: Unified memory and state preservation
"""

from agents.planner_agent import PlannerAgent
from agents.coder_agent import CoderAgent
from agents.executor_agent import ExecutorAgent
from agents.supervisor import Supervisor
from agents.shared_context import SharedContext

__all__ = [
    "PlannerAgent",
    "CoderAgent",
    "ExecutorAgent",
    "Supervisor",
    "SharedContext",
]
