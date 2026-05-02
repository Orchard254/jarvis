"""Control plane for orchestrating plan execution.

Coordinates the execution of multi-step plans, managing tool calls,
skill invocations, error handling, and rollback on failures.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional
import logging

from jarvis.execution.tool_runner import ToolRunner, ToolResult
from jarvis.execution.skill_runner import SkillRunner
from jarvis.execution.rollback import RollbackManager, RollbackAction
from jarvis.safety.audit_log import AuditLog
from jarvis.config.config import get_config

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Status of plan execution."""
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    ROLLED_BACK = auto()
    PARTIAL = auto()  # Some steps completed before failure


@dataclass
class StepResult:
    """Result of executing a single plan step."""
    step_index: int
    step_type: str  # 'tool' or 'skill'
    name: str
    status: ExecutionStatus
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    rollback_actions: list[RollbackAction] = field(default_factory=list)


@dataclass
class PlanExecutionResult:
    """Result of executing an entire plan."""
    status: ExecutionStatus
    step_results: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error: Optional[str] = None
    rolled_back: bool = False


class ControlPlane:
    """Orchestrates plan execution with safety and rollback support.
    
    The control plane is responsible for:
    - Executing multi-step plans sequentially
    - Coordinating tool and skill runners
    - Managing rollback on failures
    - Logging all execution steps for audit
    - Tracking execution state and results
    """
    
    def __init__(self, audit_log: AuditLog):
        self.config = get_config()
        self.audit_log = audit_log
        self.tool_runner = ToolRunner(audit_log)
        self.skill_runner = SkillRunner(audit_log)
        self.rollback_manager = RollbackManager()
        
        self._current_plan_id: Optional[str] = None
        self._execution_context: dict[str, Any] = {}
    
    async def execute_plan(
        self,
        plan_id: str,
        steps: list[dict[str, Any]],
        context: Optional[dict[str, Any]] = None,
        enable_rollback: bool = True,
    ) -> PlanExecutionResult:
        """Execute a multi-step plan.
        
        Args:
            plan_id: Unique identifier for this plan execution
            steps: List of step definitions, each containing:
                - type: 'tool' or 'skill'
                - name: Tool or skill name
                - params: Parameters to pass
                - optional: If True, continue on failure
            context: Execution context shared across steps
            enable_rollback: Whether to attempt rollback on failure
            
        Returns:
            PlanExecutionResult with status and step results
        """
        self._current_plan_id = plan_id
        self._execution_context = context or {}
        
        result = PlanExecutionResult(status=ExecutionStatus.RUNNING)
        start_time = self._current_time_ms()
        
        logger.info(f"Starting plan execution: {plan_id} with {len(steps)} steps")
        self.audit_log.log_plan_start(plan_id, steps)
        
        try:
            for i, step in enumerate(steps):
                step_result = await self._execute_step(i, step)
                result.step_results.append(step_result)
                
                # Track rollback actions
                if step_result.rollback_actions:
                    self.rollback_manager.register_actions(
                        plan_id, step_result.rollback_actions
                    )
                
                # Handle step failure
                if step_result.status == ExecutionStatus.FAILED:
                    if not step.get('optional', False):
                        logger.warning(
                            f"Step {i} failed: {step_result.error}. "
                            f"Halting plan execution."
                        )
                        result.status = ExecutionStatus.FAILED
                        result.error = step_result.error
                        break
                    else:
                        logger.info(f"Optional step {i} failed, continuing...")
                
                # Check for cancellation
                if self._is_cancelled():
                    logger.info(f"Plan {plan_id} cancelled by user")
                    result.status = ExecutionStatus.FAILED
                    result.error = "Cancelled by user"
                    break
            
            # Determine final status
            if result.status == ExecutionStatus.RUNNING:
                result.status = ExecutionStatus.COMPLETED
                logger.info(f"Plan {plan_id} completed successfully")
            
            # Handle rollback if needed
            elif enable_rollback and result.status == ExecutionStatus.FAILED:
                rollback_result = await self._attempt_rollback(plan_id)
                if rollback_result:
                    result.rolled_back = True
                    result.status = ExecutionStatus.ROLLED_BACK
                    logger.info(f"Plan {plan_id} rolled back successfully")
                else:
                    result.status = ExecutionStatus.PARTIAL
                    logger.warning(f"Plan {plan_id} failed with partial rollback")
            
        except Exception as e:
            logger.exception(f"Unexpected error in plan {plan_id}: {e}")
            result.status = ExecutionStatus.FAILED
            result.error = str(e)
            
            if enable_rollback:
                rollback_result = await self._attempt_rollback(plan_id)
                if rollback_result:
                    result.rolled_back = True
                    result.status = ExecutionStatus.ROLLED_BACK
        
        finally:
            result.total_duration_ms = self._current_time_ms() - start_time
            self.audit_log.log_plan_end(
                plan_id, result.status.value, result.total_duration_ms
            )
            self._current_plan_id = None
        
        return result
    
    async def _execute_step(self, index: int, step: dict[str, Any]) -> StepResult:
        """Execute a single plan step."""
        step_type = step.get('type', 'tool')
        name = step.get('name', 'unknown')
        params = step.get('params', {})
        
        logger.debug(f"Executing step {index}: {step_type} '{name}'")
        
        start_time = self._current_time_ms()
        step_result = StepResult(
            step_index=index,
            step_type=step_type,
            name=name,
            status=ExecutionStatus.PENDING,
        )
        
        try:
            if step_type == 'tool':
                tool_result = await self.tool_runner.execute(name, params)
                step_result.result = tool_result.output
                step_result.status = (
                    ExecutionStatus.COMPLETED 
                    if tool_result.success 
                    else ExecutionStatus.FAILED
                )
                step_result.error = tool_result.error
                step_result.rollback_actions = tool_result.rollback_actions
                
            elif step_type == 'skill':
                skill_result = await self.skill_runner.execute(
                    name, params, self._execution_context
                )
                step_result.result = skill_result.output
                step_result.status = (
                    ExecutionStatus.COMPLETED 
                    if skill_result.success 
                    else ExecutionStatus.FAILED
                )
                step_result.error = skill_result.error
                step_result.rollback_actions = skill_result.rollback_actions
                
            else:
                raise ValueError(f"Unknown step type: {step_type}")
                
        except Exception as e:
            logger.exception(f"Error executing step {index}: {e}")
            step_result.status = ExecutionStatus.FAILED
            step_result.error = str(e)
        
        step_result.duration_ms = self._current_time_ms() - start_time
        
        # Log step completion
        self.audit_log.log_step(
            self._current_plan_id,
            index,
            step_type,
            name,
            step_result.status.value,
            step_result.duration_ms,
            step_result.error,
        )
        
        return step_result
    
    async def _attempt_rollback(self, plan_id: str) -> bool:
        """Attempt to rollback all actions from a failed plan."""
        actions = self.rollback_manager.get_actions(plan_id)
        if not actions:
            logger.info(f"No rollback actions registered for plan {plan_id}")
            return True
        
        logger.info(f"Rolling back {len(actions)} actions for plan {plan_id}")
        success = await self.rollback_manager.execute_rollback(plan_id)
        
        if success:
            self.audit_log.log_rollback(plan_id, True)
        else:
            self.audit_log.log_rollback(plan_id, False)
        
        return success
    
    def _current_time_ms(self) -> float:
        """Get current time in milliseconds."""
        import time
        return time.time() * 1000
    
    def _is_cancelled(self) -> bool:
        """Check if current execution has been cancelled."""
        # Placeholder for cancellation check
        # Could be implemented with threading.Event or similar
        return False
    
    def cancel_current_plan(self):
        """Cancel the currently executing plan."""
        # Set cancellation flag
        # Implementation depends on concurrency model
        logger.info("Cancellation requested for current plan")
