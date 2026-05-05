"""
jarvis/execution/task_executor.py — Plan-Execute-Verify Loop Engine

Transforms JARVIS from reactive tool-caller to proactive autonomous agent.
Implements state-aware task execution with verification, error recovery, and memory.

Key Features:
- Multi-step task planning with explicit state tracking
- Action verification before proceeding to next step
- Automatic retry with fallback strategies on failure
- Duplicate action detection to prevent loops
- Visual confirmation integration (optional)
- Timeout protection for each step
"""

import logging
import time
import subprocess
import sys
import os
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json

from ..tools.base import ToolResult
from ..tools.registry import get_registry, execute_tool

logger = logging.getLogger("task_executor")


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VerificationStrategy(Enum):
    """How to verify an action succeeded."""
    NONE = "none"  # No verification (fast but unreliable)
    TOOL_RESULT = "tool_result"  # Check tool returned success
    VISUAL = "visual"  # Use screen perception to verify
    CUSTOM = "custom"  # Custom verification function
    STATE_CHECK = "state_check"  # Check application/window state changed as expected


@dataclass
class TaskStep:
    """A single step in a multi-step task."""
    tool_name: str
    parameters: Dict[str, Any]
    description: str = ""
    verification_strategy: VerificationStrategy = VerificationStrategy.TOOL_RESULT
    verification_keyword: Optional[str] = None  # For visual verification
    custom_verify_fn: Optional[Callable] = None
    timeout: float = 30.0
    max_retries: int = 2
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[ToolResult] = None
    error_message: Optional[str] = None
    duration: float = 0.0


@dataclass
class TaskPlan:
    """Complete plan for a multi-step task."""
    task_id: str
    description: str
    steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    total_duration: float = 0.0
    context: Dict[str, Any] = field(default_factory=dict)


class TaskExecutor:
    """
    Executes multi-step tasks with verification and error recovery.
    
    Usage:
        executor = TaskExecutor()
        
        # Create a plan
        plan = executor.create_plan(
            task_id="search_cars_jiji",
            description="Search for cars on Jiji Kenya within budget",
            steps=[
                TaskStep(
                    tool_name="navigate_to_url",
                    parameters={"url": "https://jiji.co.ke"},
                    description="Open Jiji Kenya website",
                    verification_strategy=VerificationStrategy.VISUAL,
                    verification_keyword="Jiji"
                ),
                TaskStep(
                    tool_name="fill_input",
                    parameters={"selector": "label:Search", "value": "cars"},
                    description="Enter search term",
                    verification_strategy=VerificationStrategy.TOOL_RESULT
                ),
                # ... more steps
            ]
        )
        
        # Execute with verification
        result = executor.execute_plan(plan)
    """
    
    def __init__(self, enable_visual_verification: bool = True, use_separate_process: bool = True):
        self.enable_visual_verification = enable_visual_verification
        self.use_separate_process = use_separate_process
        self._active_plans: Dict[str, TaskPlan] = {}
        self._completed_tasks: List[str] = []
        self._action_history: List[Dict] = []  # Track all actions for loop detection
        
        # Try to import vision module
        self._perceptor = None
        if enable_visual_verification:
            try:
                from ..core.vision import get_perceptor
                self._perceptor = get_perceptor()
                logger.info("Visual verification enabled")
            except Exception as e:
                logger.warning(f"Visual verification unavailable: {e}")
                self.enable_visual_verification = False
    
    def create_plan(self, task_id: str, description: str, 
                   steps: Optional[List[TaskStep]] = None) -> TaskPlan:
        """Create a new task plan."""
        plan = TaskPlan(
            task_id=task_id,
            description=description,
            steps=steps or []
        )
        self._active_plans[task_id] = plan
        logger.info(f"Created task plan: {task_id} - {description}")
        return plan
    
    def add_step(self, plan: TaskPlan, tool_name: str, parameters: Dict[str, Any],
                description: str = "", 
                verification_strategy: VerificationStrategy = VerificationStrategy.TOOL_RESULT,
                verification_keyword: Optional[str] = None,
                timeout: float = 30.0,
                max_retries: int = 2) -> TaskStep:
        """Add a step to an existing plan."""
        step = TaskStep(
            tool_name=tool_name,
            parameters=parameters,
            description=description,
            verification_strategy=verification_strategy,
            verification_keyword=verification_keyword,
            timeout=timeout,
            max_retries=max_retries
        )
        plan.steps.append(step)
        return step
    
    def _check_duplicate_action(self, tool_name: str, parameters: Dict[str, Any], current_step_index: int = -1) -> bool:
        """Check if this exact action was recently performed (loop detection).
        
        Only flags duplicates if the same tool with identical parameters runs within a 2-second window,
        allowing legitimate repeated actions while preventing infinite loops.
        """
        current_time = time.time()
        
        # For 'wait' tool, allow multiple calls (they're often at different steps)
        if tool_name == "wait":
            return False
        
        # Look at last 10 actions
        recent_actions = self._action_history[-10:]
        
        for action in recent_actions:
            if (action["tool_name"] == tool_name and 
                action["parameters"] == parameters and
                current_time - action["timestamp"] < 2):  # Within last 2 seconds
                
                logger.warning(f"Duplicate action detected: {tool_name} with same parameters within 2s window")
                return True
        
        return False
    
    def _record_action(self, tool_name: str, parameters: Dict[str, Any], 
                      success: bool, duration: float):
        """Record an action to history for loop detection."""
        self._action_history.append({
            "tool_name": tool_name,
            "parameters": parameters,
            "timestamp": time.time(),
            "success": success,
            "duration": duration
        })
        
        # Keep only last 50 actions
        if len(self._action_history) > 50:
            self._action_history = self._action_history[-50:]
    
    def _verify_step(self, step: TaskStep) -> tuple[bool, str]:
        """
        Verify that a step completed successfully.
        
        Returns:
            Tuple of (is_success, message)
        """
        if step.verification_strategy == VerificationStrategy.NONE:
            return True, "No verification required"
        
        elif step.verification_strategy == VerificationStrategy.TOOL_RESULT:
            if step.result is None:
                return False, "No result available"
            if step.result.success:
                return True, f"Tool reported success: {step.result.output}"
            else:
                return False, f"Tool reported failure: {step.result.error}"
        
        elif step.verification_strategy == VerificationStrategy.VISUAL:
            if not self.enable_visual_verification or self._perceptor is None:
                logger.warning("Visual verification requested but not available")
                return True, "Visual verification skipped (unavailable)"
            
            if not step.verification_keyword:
                logger.warning("Visual verification requires keyword")
                return True, "Visual verification skipped (no keyword)"
            
            # Try to find keyword on screen
            found = self._perceptor.verify_element_visible(
                step.verification_keyword, 
                timeout=5
            )
            
            if found:
                return True, f"Verified '{step.verification_keyword}' visible on screen"
            else:
                return False, f"Could not verify '{step.verification_keyword}' on screen"
        
        elif step.verification_strategy == VerificationStrategy.STATE_CHECK:
            """
            Verify by checking the actual state of the target application/window.
            This is more reliable than just trusting tool results.
            """
            try:
                import psutil
                from win32gui import GetForegroundWindow, GetWindowText
                
                # For keyboard actions - trust tool result if it succeeded
                if step.tool_name == "press_key":
                    keys = step.parameters.get("keys", step.parameters.get("key", "")).lower()
                    
                    # If tool reported success, trust it
                    if step.result and step.result.success:
                        time.sleep(0.3)
                        logger.info(f"State check: Key press '{keys}' executed successfully")
                        return True, f"Verified: Key press '{keys}' executed"
                    
                    # For delete/clear actions, verify text changed
                    if "delete" in keys or "del" in keys or "backspace" in keys:
                        time.sleep(0.5)
                        hwnd = GetForegroundWindow()
                        title = GetWindowText(hwnd)
                        if title:
                            logger.info(f"State check: Delete action in window '{title}'")
                            return True, "Verified: Delete action executed"
                    
                    # For select all, just verify it executed
                    if "ctrl+a" in keys or "control+a" in keys or "selectall" in keys:
                        time.sleep(0.3)
                        logger.info(f"State check: Select All executed")
                        return True, "Verified: Select All action executed"
                    
                    # For copy/paste operations
                    if "ctrl+c" in keys or "ctrl+v" in keys:
                        time.sleep(0.3)
                        logger.info(f"State check: Copy/Paste executed")
                        return True, "Verified: Copy/Paste action executed"
                    
                    # For minimize/maximize/restore operations (Win+Down, Win+Up, etc.)
                    # These are hard to verify visually, so trust the tool if it didn't error
                    if "win+down" in keys or "win+up" in keys or "win+left" in keys or "win+right" in keys:
                        time.sleep(0.3)
                        logger.info(f"State check: Window management key '{keys}' executed")
                        return True, f"Verified: Window management key '{keys}' executed"
                    
                    # Default: if tool didn't report success, fail verification
                    if step.result and not step.result.success:
                        return False, f"State check failed: Tool reported failure"
                    
                    # For other keys, just trust the tool
                    return True, "State check passed: Key press executed"
                
                # For type_text, verify text was entered
                elif step.tool_name == "type_text":
                    if step.result and step.result.success:
                        time.sleep(0.3)
                        logger.info(f"State check: Text input executed")
                        return True, "Verified: Text was typed"
                
                # Default: trust tool result for other tools
                if step.result and step.result.success:
                    return True, f"State check passed: {step.result.output}"
                else:
                    return False, "State check failed: Tool did not report success"
                    
            except Exception as e:
                logger.warning(f"State check failed: {e}")
                # Fallback to trusting tool result
                if step.result and step.result.success:
                    return True, f"State check unavailable, trusting tool result: {step.result.output}"
                return False, f"State check error: {e}"
        
        elif step.verification_strategy == VerificationStrategy.CUSTOM:
            if step.custom_verify_fn is None:
                return False, "Custom verification function not provided"
            
            try:
                result = step.custom_verify_fn(step.result)
                if isinstance(result, tuple):
                    return result
                return bool(result), "Custom verification passed"
            except Exception as e:
                return False, f"Custom verification failed: {e}"
        
        return True, "Unknown verification strategy"
    
    def _execute_step_with_retry(self, step: TaskStep, plan: TaskPlan) -> bool:
        """Execute a single step with retry logic."""
        attempt = 0
        
        while attempt <= step.max_retries:
            # Validate parameters based on tool type
            from jarvis.core.predictive_planner import NO_PARAMETER_TOOLS, REQUIRED_PARAMETERS
            
            if step.tool_name not in NO_PARAMETER_TOOLS:
                # This tool requires parameters
                if step.parameters is None or not isinstance(step.parameters, dict):
                    step.error_message = f"Invalid parameters for {step.tool_name}: parameters must be a dict"
                    step.status = TaskStatus.FAILED
                    logger.error(f"Step validation failed: {step.error_message}")
                    return False
                
                # Check for obviously missing required parameters
                required = REQUIRED_PARAMETERS.get(step.tool_name, [])
                missing = [p for p in required if p not in step.parameters or not step.parameters[p]]
                if missing:
                    step.error_message = f"Missing required parameters for {step.tool_name}: {', '.join(missing)}"
                    step.status = TaskStatus.FAILED
                    logger.error(f"Step validation failed: {step.error_message}")
                    return False
            
            # Check for duplicate action (loop prevention)
            if self._check_duplicate_action(step.tool_name, step.parameters):
                step.error_message = "Duplicate action detected (possible loop)"
                step.status = TaskStatus.FAILED
                logger.warning(f"Skipping duplicate action: {step.tool_name}")
                return False
            
            # Check timeout
            start_time = time.time()
            
            try:
                logger.info(f"Executing step {step.tool_name} (attempt {attempt + 1})")
                
                # Execute the tool - execute_tool returns string, need to wrap in ToolResult
                from jarvis.tools.base import ToolResult
                
                if self.use_separate_process:
                    # Execute in a separate subprocess for isolation
                    result = self._execute_in_subprocess(step.tool_name, step.parameters)
                else:
                    # Execute in the same process (original behavior)
                    try:
                        result_value = execute_tool(step.tool_name, **step.parameters)
                        # If result is a string, wrap it in ToolResult
                        if isinstance(result_value, str):
                            result = ToolResult(success=True, output=result_value)
                        elif isinstance(result_value, dict):
                            result = ToolResult(**result_value)
                        else:
                            result = result_value
                    except Exception as exec_error:
                        # If execution raises exception, create failed ToolResult
                        result = ToolResult(success=False, error=str(exec_error))
                
                step.result = result
                step.duration = time.time() - start_time
                
                # Record action
                self._record_action(
                    step.tool_name, 
                    step.parameters,
                    result.success,
                    step.duration
                )
                
                # Verify the result
                verified, verify_msg = self._verify_step(step)
                logger.info(f"Verification: {verify_msg}")
                
                if verified:
                    step.status = TaskStatus.COMPLETED
                    return True
                else:
                    step.error_message = verify_msg
                    logger.warning(f"Verification failed: {verify_msg}")
                    
            except Exception as e:
                step.error_message = str(e)
                step.duration = time.time() - start_time
                logger.error(f"Step execution error: {e}")
                
                # Record failed action
                self._record_action(
                    step.tool_name,
                    step.parameters,
                    False,
                    step.duration
                )
            
            attempt += 1
            
            if attempt <= step.max_retries:
                wait_time = min(2 ** attempt, 10)  # Exponential backoff, max 10s
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
        
        step.status = TaskStatus.FAILED
        return False
    
    def _execute_in_subprocess(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute a tool in a separate subprocess for isolation.
        
        This prevents issues like window focus conflicts when executing tools that
        interact with GUI applications while the main JARVIS terminal is active.
        """
        from jarvis.tools.base import ToolResult
        
        try:
            # Prepare the subprocess call
            # We'll call a helper script that executes the tool and returns JSON
            script_path = Path(__file__).parent / "tool_runner.py"
            
            # Serialize parameters to JSON
            params_json = json.dumps(parameters)
            
            # Get the project root directory
            project_root = str(Path(__file__).parent.parent.parent)
            
            # Build the command with proper environment
            cmd = [
                sys.executable,
                str(script_path),
                tool_name,
                params_json
            ]
            
            # Create environment that inherits current venv
            env = os.environ.copy()
            
            # Ensure PYTHONPATH includes project root
            current_pythonpath = env.get('PYTHONPATH', '')
            if current_pythonpath:
                env['PYTHONPATH'] = f"{project_root}{os.pathsep}{current_pythonpath}"
            else:
                env['PYTHONPATH'] = project_root
            
            # Run the subprocess
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 60 second timeout for subprocess
                cwd=project_root,  # Run from project root
                env=env  # Pass the modified environment
            )
            
            # Parse the result
            if process.returncode == 0:
                try:
                    result_data = json.loads(process.stdout.strip())
                    return ToolResult(**result_data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse subprocess output: {process.stdout}")
                    return ToolResult(success=False, error=f"Invalid response format: {e}")
            else:
                error_msg = process.stderr.strip() or f"Subprocess exited with code {process.returncode}"
                logger.error(f"Subprocess execution failed: {error_msg}")
                return ToolResult(success=False, error=error_msg)
                
        except subprocess.TimeoutExpired:
            logger.error(f"Subprocess timed out for tool: {tool_name}")
            return ToolResult(success=False, error="Tool execution timed out")
        except Exception as e:
            logger.error(f"Subprocess execution failed: {e}")
            return ToolResult(success=False, error=str(e))
    
    def execute_plan(self, plan: TaskPlan, stop_on_failure: bool = False) -> TaskPlan:
        """
        Execute all steps in a plan sequentially.
        
        Args:
            plan: The task plan to execute
            stop_on_failure: If True, stop entire task on first failure
            
        Returns:
            Updated plan with results
        """
        logger.info(f"Starting task execution: {plan.task_id}")
        plan.status = TaskStatus.IN_PROGRESS
        start_time = time.time()
        
        for i, step in enumerate(plan.steps):
            plan.current_step_index = i
            logger.info(f"Executing step {i+1}/{len(plan.steps)}: {step.description or step.tool_name}")
            
            success = self._execute_step_with_retry(step, plan)
            
            if not success:
                logger.error(f"Step {i+1} failed: {step.error_message}")
                
                if stop_on_failure:
                    logger.info("Stopping task due to failure")
                    plan.status = TaskStatus.FAILED
                    break
                
                # Continue to next step anyway (best effort)
                logger.info("Continuing to next step despite failure")
        
        # Update final status
        plan.completed_at = time.time()
        plan.total_duration = plan.completed_at - start_time
        
        failed_steps = sum(1 for s in plan.steps if s.status == TaskStatus.FAILED)
        if failed_steps == 0:
            plan.status = TaskStatus.COMPLETED
            logger.info(f"Task completed successfully: {plan.task_id} ({plan.total_duration:.2f}s)")
        else:
            plan.status = TaskStatus.FAILED
            logger.warning(f"Task completed with {failed_steps} failures: {plan.task_id}")
        
        # Move to completed tasks
        self._completed_tasks.append(plan.task_id)
        if plan.task_id in self._active_plans:
            del self._active_plans[plan.task_id]
        
        return plan
    
    def get_task_summary(self, plan: TaskPlan) -> Dict[str, Any]:
        """Get a human-readable summary of task execution."""
        successful = sum(1 for s in plan.steps if s.status == TaskStatus.COMPLETED)
        failed = sum(1 for s in plan.steps if s.status == TaskStatus.FAILED)
        
        return {
            "task_id": plan.task_id,
            "description": plan.description,
            "status": plan.status.value,
            "total_steps": len(plan.steps),
            "successful_steps": successful,
            "failed_steps": failed,
            "duration_seconds": round(plan.total_duration, 2),
            "steps": [
                {
                    "step": i + 1,
                    "tool": step.tool_name,
                    "description": step.description,
                    "status": step.status.value,
                    "error": step.error_message,
                    "duration": round(step.duration, 2)
                }
                for i, step in enumerate(plan.steps)
            ]
        }
    
    def clear_history(self):
        """Clear action history (useful for starting fresh tasks)."""
        self._action_history.clear()
        logger.info("Action history cleared")


# Convenience functions for common workflows
def create_web_search_plan(task_id: str, url: str, search_term: str, 
                          search_selector: str = "input[name='q']",
                          submit_selector: str = "button[type='submit']") -> TaskPlan:
    """Create a standard web search plan."""
    executor = TaskExecutor()
    
    plan = executor.create_plan(
        task_id=task_id,
        description=f"Search for '{search_term}' on {url}"
    )
    
    executor.add_step(
        plan,
        tool_name="navigate_to_url",
        parameters={"url": url},
        description="Navigate to website",
        verification_strategy=VerificationStrategy.TOOL_RESULT
    )
    
    executor.add_step(
        plan,
        tool_name="fill_input",
        parameters={"selector": search_selector, "value": search_term},
        description="Enter search term",
        verification_strategy=VerificationStrategy.TOOL_RESULT
    )
    
    executor.add_step(
        plan,
        tool_name="click_element",
        parameters={"selector": submit_selector},
        description="Submit search",
        verification_strategy=VerificationStrategy.TOOL_RESULT
    )
    
    return plan


# Export main classes
__all__ = [
    "TaskExecutor",
    "TaskPlan",
    "TaskStep",
    "TaskStatus",
    "VerificationStrategy",
    "create_web_search_plan"
]
