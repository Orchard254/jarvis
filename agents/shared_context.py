"""
Shared Context for Multi-Agent System

Provides unified memory and state preservation across all agents.
Enables dynamic handoff with full context transfer.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskState:
    """Represents the current state of a task being processed."""
    task_id: str
    original_goal: str
    current_step: int = 0
    total_steps: int = 0
    status: str = "pending"  # pending, running, completed, failed, paused
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SharedContext:
    """
    Centralized context manager for multi-agent collaboration.
    
    Provides:
    - Task state tracking across agent handoffs
    - Shared working memory for intermediate results
    - Execution history for self-healing analysis
    - Agent coordination state
    """
    
    def __init__(self):
        self._task_states: Dict[str, TaskState] = {}
        self._working_memory: Dict[str, Any] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._agent_states: Dict[str, Dict[str, Any]] = {}
        self._lock = __import__("threading").Lock()
        
    def create_task(self, task_id: str, goal: str, steps: Optional[List[str]] = None) -> TaskState:
        """Create a new task with optional step breakdown."""
        with self._lock:
            state = TaskState(
                task_id=task_id,
                original_goal=goal,
                total_steps=len(steps) if steps else 0,
                metadata={"steps": steps or []}
            )
            self._task_states[task_id] = state
            logger.info(f"Created task {task_id}: {goal[:60]}...")
            return state
    
    def get_task(self, task_id: str) -> Optional[TaskState]:
        """Retrieve task state by ID."""
        return self._task_states.get(task_id)
    
    def update_task(self, task_id: str, **kwargs) -> Optional[TaskState]:
        """Update task state fields."""
        with self._lock:
            state = self._task_states.get(task_id)
            if not state:
                return None
            for key, value in kwargs.items():
                if hasattr(state, key):
                    setattr(state, key, value)
            state.updated_at = time.time()
            return state
    
    def set_working_memory(self, key: str, value: Any) -> None:
        """Store intermediate result in shared working memory."""
        with self._lock:
            self._working_memory[key] = value
            logger.debug(f"Working memory set: {key}")
    
    def get_working_memory(self, key: str, default: Any = None) -> Any:
        """Retrieve value from working memory."""
        return self._working_memory.get(key, default)
    
    def clear_working_memory(self) -> None:
        """Clear all working memory."""
        with self._lock:
            self._working_memory.clear()
    
    def record_execution(self, agent: str, action: str, result: Any, 
                         success: bool, error: Optional[str] = None) -> None:
        """Record an execution event for self-healing analysis."""
        with self._lock:
            entry = {
                "timestamp": time.time(),
                "agent": agent,
                "action": action,
                "result": result,
                "success": success,
                "error": error,
            }
            self._execution_history.append(entry)
            # Cap history to prevent unbounded growth
            if len(self._execution_history) > 1000:
                self._execution_history = self._execution_history[-500:]
            logger.debug(f"Recorded execution: {agent}.{action} -> {'OK' if success else 'FAIL'}")
    
    def get_recent_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent failed executions for self-healing analysis."""
        with self._lock:
            failures = [e for e in self._execution_history if not e["success"]]
            return failures[-limit:]
    
    def get_execution_chain(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all execution events related to a task."""
        with self._lock:
            return [
                e for e in self._execution_history 
                if e.get("task_id") == task_id or e.get("related_task") == task_id
            ]
    
    def set_agent_state(self, agent_name: str, state: Dict[str, Any]) -> None:
        """Store current state of an agent (for handoff)."""
        with self._lock:
            self._agent_states[agent_name] = {
                "updated_at": time.time(),
                **state
            }
    
    def get_agent_state(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve agent state."""
        return self._agent_states.get(agent_name)
    
    def get_full_context(self, task_id: str) -> Dict[str, Any]:
        """
        Get complete context for task handoff.
        Includes task state, relevant working memory, and execution history.
        """
        task = self.get_task(task_id)
        return {
            "task": {
                "id": task.task_id if task else task_id,
                "goal": task.original_goal if task else "",
                "current_step": task.current_step if task else 0,
                "total_steps": task.total_steps if task else 0,
                "status": task.status if task else "unknown",
                "metadata": task.metadata if task else {},
            },
            "working_memory": dict(self._working_memory),
            "recent_failures": self.get_recent_failures(5),
            "agent_states": dict(self._agent_states),
        }
    
    def reset_task(self, task_id: str) -> None:
        """Reset a task for retry."""
        with self._lock:
            if task_id in self._task_states:
                state = self._task_states[task_id]
                state.current_step = 0
                state.status = "pending"
                state.error = None
                state.result = None
                state.updated_at = time.time()
