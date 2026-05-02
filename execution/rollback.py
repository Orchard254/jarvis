"""Rollback manager for transactional execution.

Provides rollback capabilities for failed operations by tracking
and executing inverse actions for tools that support them.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable
from enum import Enum, auto
import logging
import asyncio

logger = logging.getLogger(__name__)


class RollbackStatus(Enum):
    """Status of a rollback action."""
    PENDING = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()  # Not applicable or already rolled back


@dataclass
class RollbackAction:
    """Definition of a single rollback action.
    
    Attributes:
        action_id: Unique identifier for this action
        original_tool: Name of the tool that was originally executed
        original_params: Parameters used in the original execution
        rollback_type: Type of rollback ('inverse', 'cleanup', 'compensating')
        execute_fn: Async function to perform the rollback
        description: Human-readable description of what will be rolled back
        priority: Execution order (lower = first)
        required: If False, rollback can fail without halting
        status: Current execution status
        error: Error message if rollback failed
    """
    action_id: str
    original_tool: str
    original_params: dict[str, Any]
    rollback_type: str  # 'inverse', 'cleanup', 'compensating'
    execute_fn: Optional[Awaitable[bool]] = None
    description: str = ""
    priority: int = 0
    required: bool = True
    status: RollbackStatus = RollbackStatus.PENDING
    error: Optional[str] = None
    
    @classmethod
    def create_inverse(
        cls,
        action_id: str,
        original_tool: str,
        original_params: dict[str, Any],
        inverse_tool: str,
        inverse_params: dict[str, Any],
        tool_runner: Any,
        description: str = "",
        required: bool = True,
    ) -> 'RollbackAction':
        """Create a rollback action that executes an inverse tool.
        
        Args:
            action_id: Unique identifier
            original_tool: Original tool name
            original_params: Original parameters
            inverse_tool: Tool to execute for rollback
            inverse_params: Parameters for rollback tool
            tool_runner: ToolRunner instance to use
            description: Optional description
            required: Whether this rollback is required
            
        Returns:
            Configured RollbackAction
        """
        async def execute_fn():
            result = await tool_runner.execute(inverse_tool, inverse_params)
            return result.success
        
        return cls(
            action_id=action_id,
            original_tool=original_tool,
            original_params=original_params,
            rollback_type='inverse',
            execute_fn=execute_fn(),
            description=description or f"Undo {original_tool} with {inverse_tool}",
            required=required,
        )
    
    @classmethod
    def create_cleanup(
        cls,
        action_id: str,
        original_tool: str,
        original_params: dict[str, Any],
        cleanup_fn: Callable[[], Awaitable[bool]],
        description: str = "",
        required: bool = False,
    ) -> 'RollbackAction':
        """Create a rollback action that performs cleanup.
        
        Args:
            action_id: Unique identifier
            original_tool: Original tool name
            original_params: Original parameters
            cleanup_fn: Async cleanup function
            description: Optional description
            required: Whether this rollback is required
            
        Returns:
            Configured RollbackAction
        """
        return cls(
            action_id=action_id,
            original_tool=original_tool,
            original_params=original_params,
            rollback_type='cleanup',
            execute_fn=cleanup_fn(),
            description=description or f"Cleanup after {original_tool}",
            required=required,
        )
    
    @classmethod
    def create_compensating(
        cls,
        action_id: str,
        original_tool: str,
        original_params: dict[str, Any],
        compensating_action: Callable[[], Awaitable[bool]],
        description: str = "",
        required: bool = True,
    ) -> 'RollbackAction':
        """Create a rollback action with custom compensating logic.
        
        Compensating actions don't necessarily undo the original action,
        but restore the system to a consistent state.
        
        Args:
            action_id: Unique identifier
            original_tool: Original tool name
            original_params: Original parameters
            compensating_action: Custom compensating function
            description: Optional description
            required: Whether this rollback is required
            
        Returns:
            Configured RollbackAction
        """
        return cls(
            action_id=action_id,
            original_tool=original_tool,
            original_params=original_params,
            rollback_type='compensating',
            execute_fn=compensating_action(),
            description=description or f"Compensate for {original_tool}",
            required=required,
        )


@dataclass
class RollbackResult:
    """Result of executing rollback actions."""
    success: bool
    total_actions: int
    completed: int
    failed: int
    skipped: int
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class RollbackManager:
    """Manages rollback actions for failed plan executions.
    
    Responsibilities:
    - Register rollback actions during plan execution
    - Execute rollbacks in reverse order on failure
    - Track rollback status and results
    - Handle partial rollbacks gracefully
    """
    
    def __init__(self):
        self._plan_actions: dict[str, list[RollbackAction]] = {}
        self._execution_history: dict[str, RollbackResult] = {}
    
    def register_actions(self, plan_id: str, actions: list[RollbackAction]):
        """Register rollback actions for a plan.
        
        Args:
            plan_id: Plan identifier
            actions: List of rollback actions to register
        """
        if plan_id not in self._plan_actions:
            self._plan_actions[plan_id] = []
        
        self._plan_actions[plan_id].extend(actions)
        logger.debug(
            f"Registered {len(actions)} rollback actions for plan {plan_id}"
        )
    
    def get_actions(self, plan_id: str) -> list[RollbackAction]:
        """Get all registered rollback actions for a plan.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            List of rollback actions
        """
        return self._plan_actions.get(plan_id, [])
    
    async def execute_rollback(self, plan_id: str) -> bool:
        """Execute all rollback actions for a failed plan.
        
        Actions are executed in reverse order (LIFO) to properly
        undo nested operations. Required failures halt execution.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            True if all required rollbacks succeeded
        """
        actions = self._plan_actions.get(plan_id, [])
        if not actions:
            return True
        
        logger.info(f"Executing rollback for plan {plan_id} ({len(actions)} actions)")
        
        start_time = asyncio.get_event_loop().time() * 1000
        result = RollbackResult(
            success=True,
            total_actions=len(actions),
            completed=0,
            failed=0,
            skipped=0,
        )
        
        # Execute in reverse order
        for action in reversed(actions):
            if action.status != RollbackStatus.PENDING:
                result.skipped += 1
                continue
            
            action.status = RollbackStatus.EXECUTING
            
            try:
                if action.execute_fn is None:
                    logger.warning(
                        f"Rollback action {action.action_id} has no execute_fn, skipping"
                    )
                    action.status = RollbackStatus.SKIPPED
                    result.skipped += 1
                    continue
                
                success = await action.execute_fn
                
                if success:
                    action.status = RollbackStatus.COMPLETED
                    result.completed += 1
                    logger.debug(f"Rollback action {action.action_id} completed")
                else:
                    action.status = RollbackStatus.FAILED
                    action.error = "Execution returned False"
                    result.failed += 1
                    result.errors.append(
                        f"Action {action.action_id}: {action.error}"
                    )
                    
                    if action.required:
                        logger.error(
                            f"Required rollback action {action.action_id} failed, halting"
                        )
                        result.success = False
                        break
                        
            except Exception as e:
                action.status = RollbackStatus.FAILED
                action.error = str(e)
                result.failed += 1
                result.errors.append(f"Action {action.action_id}: {str(e)}")
                
                if action.required:
                    logger.exception(
                        f"Required rollback action {action.action_id} raised exception"
                    )
                    result.success = False
                    break
        
        result.duration_ms = (asyncio.get_event_loop().time() * 1000) - start_time
        self._execution_history[plan_id] = result
        
        if result.success:
            logger.info(f"Rollback for plan {plan_id} completed successfully")
        else:
            logger.warning(
                f"Rollback for plan {plan_id} partially failed: "
                f"{result.completed} completed, {result.failed} failed, "
                f"{result.skipped} skipped"
            )
        
        return result.success
    
    def get_rollback_result(self, plan_id: str) -> Optional[RollbackResult]:
        """Get the result of a previous rollback execution.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            RollbackResult or None if not found
        """
        return self._execution_history.get(plan_id)
    
    def clear_plan(self, plan_id: str):
        """Clear rollback actions for a plan after successful completion.
        
        Args:
            plan_id: Plan identifier
        """
        if plan_id in self._plan_actions:
            del self._plan_actions[plan_id]
            logger.debug(f"Cleared rollback actions for plan {plan_id}")
    
    def clear_all(self):
        """Clear all registered rollback actions."""
        self._plan_actions.clear()
        self._execution_history.clear()
        logger.debug("Cleared all rollback actions and history")
    
    def get_pending_actions_count(self, plan_id: str) -> int:
        """Get count of pending rollback actions for a plan.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            Number of pending actions
        """
        actions = self._plan_actions.get(plan_id, [])
        return sum(1 for a in actions if a.status == RollbackStatus.PENDING)
