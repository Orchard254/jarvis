"""
Supervisor Agent - Tier 3 Multi-Agent System

Routes tasks and manages state across agents.
Coordinates dynamic handoff between Planner, Coder, and Executor agents.
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from agents.planner_agent import PlannerAgent
from agents.coder_agent import CoderAgent
from agents.executor_agent import ExecutorAgent
from agents.shared_context import SharedContext

logger = logging.getLogger(__name__)


class Supervisor:
    """
    Central coordinator for the multi-agent system.
    
    Responsibilities:
    - Task intake and initial routing
    - Dynamic agent handoff coordination
    - State management across agents
    - Progress tracking and reporting
    - Error escalation handling
    
    Implements the full workflow:
    1. Receive task from user/orchestrator
    2. Route to Planner for complex tasks
    3. Hand off to Coder for code generation
    4. Pass to Executor for execution with self-healing
    5. Track progress and manage retries
    6. Return final result or escalate failures
    """
    
    def __init__(self, memory=None):
        self._shared_context = SharedContext()
        self._planner = PlannerAgent(shared_context=self._shared_context)
        self._coder = CoderAgent(shared_context=self._shared_context)
        self._executor = ExecutorAgent(
            shared_context=self._shared_context,
            coder_agent=self._coder
        )
        self._memory = memory
        self._name = "Supervisor"
        
        # Task queue for async processing
        self._pending_tasks: Dict[str, Dict] = {}
        self._completed_tasks: Dict[str, Dict] = {}
        
        logger.info("Supervisor initialized with multi-agent collaboration system")
    
    def process_task(self, goal: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process a task through the multi-agent pipeline.
        
        Args:
            goal: The user's goal/request
            context: Optional context from previous interactions
            
        Returns:
            Dict with result, success status, agent_chain, execution_details
        """
        task_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        logger.info(f"Supervisor received task {task_id}: {goal[:60]}...")
        
        # Create task in shared context
        task_state = self._shared_context.create_task(task_id, goal)
        
        result = {
            "task_id": task_id,
            "goal": goal,
            "success": False,
            "result": None,
            "error": None,
            "agent_chain": [],
            "execution_time": 0,
            "steps_executed": 0,
            "self_heal_attempts": 0
        }
        
        try:
            # Step 1: Analyze and plan (Planner Agent)
            analysis = self._planner.analyze_task(goal)
            result["agent_chain"].append({
                "agent": "PlannerAgent",
                "action": "analyze",
                "outcome": analysis.get("recommendation", "unknown")
            })
            
            # Determine if planning/decomposition is needed
            if analysis.get("is_simple", True) and analysis.get("recommendation") == "direct_execution":
                # Simple task - go straight to execution
                logger.info(f"Task {task_id} classified as simple - direct execution")
                exec_result = self._execute_simple(goal, context)
            else:
                # Complex task - decompose and execute step by step
                logger.info(f"Task {task_id} requires decomposition")
                
                steps = self._planner.decompose(goal, context)
                validated, reason = self._planner.validate_plan(steps, goal)
                
                if not validated:
                    result["error"] = f"Plan validation failed: {reason}"
                    return result
                
                # Optimize the plan
                steps = self._planner.optimize_plan(steps)
                task_state.total_steps = len(steps)
                
                result["agent_chain"].append({
                    "agent": "PlannerAgent",
                    "action": "decompose",
                    "steps_count": len(steps)
                })
                
                # Guard: reject empty plans
                if not steps:
                    result["error"] = "Planner returned an empty plan"
                    return result

                # Execute each step with dynamic handoff
                exec_result = self._execute_plan(steps, goal, context, task_state)
            
            # Process execution result
            result["success"] = exec_result.get("success", False)
            result["result"] = exec_result.get("result")
            result["error"] = exec_result.get("error")
            result["self_heal_attempts"] = exec_result.get("self_heal_attempts", 0)
            result["steps_executed"] = task_state.current_step
            result["execution_time"] = time.time() - start_time
            
            # Update task state
            self._shared_context.update_task(
                task_id,
                status="completed" if result["success"] else "failed",
                result=result["result"],
                error=result["error"]
            )
            
            # Store completed task
            self._completed_tasks[task_id] = result
            
            logger.info(
                f"Task {task_id} completed: success={result['success']}, "
                f"time={result['execution_time']:.2f}s"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Supervisor task processing failed: {e}", exc_info=True)
            result["error"] = str(e)
            result["execution_time"] = time.time() - start_time
            
            self._shared_context.update_task(
                task_id,
                status="failed",
                error=str(e)
            )
            
            return result
    
    def _execute_simple(self, goal: str, context: Optional[Dict]) -> Dict[str, Any]:
        """Execute a simple task directly."""
        # Generate code for simple task
        code_result = self._coder.generate_code(goal, context)
        
        if not code_result.get("success"):
            return {
                "success": False,
                "error": f"Code generation failed: {code_result.get('explanation', 'unknown')}"
            }
        
        # Execute the generated code
        task_spec = {
            "type": "code",
            "code": code_result.get("code", ""),
            "description": goal
        }
        
        return self._executor.execute_task(task_spec)
    
    def _execute_plan(self, steps: List[str], goal: str, 
                      context: Optional[Dict], task_state) -> Dict[str, Any]:
        """
        Execute a multi-step plan with dynamic handoff between agents.
        
        Each step flows: Planner -> Coder -> Executor -> (back to Coder if fix needed)
        """
        cumulative_result = []
        working_context = dict(context) if context else {}
        
        for i, step in enumerate(steps):
            task_state.current_step = i + 1
            logger.info(f"Executing step {i+1}/{len(steps)}: {step[:50]}...")
            
            # Update working context with previous results
            if cumulative_result:
                working_context["previous_results"] = cumulative_result
            
            # Coder Agent: Generate code for this step
            code_result = self._coder.generate_code(step, working_context)
            
            if not code_result.get("success"):
                return {
                    "success": False,
                    "error": f"Step {i+1} code generation failed: {code_result.get('explanation', 'unknown')}",
                    "failed_at_step": i + 1
                }
            
            # Executor Agent: Execute with self-healing
            task_spec = {
                "type": "code",
                "code": code_result.get("code", ""),
                "description": step,
                "step_number": i + 1,
                "task_id": task_state.task_id
            }
            
            exec_result = self._executor.execute_task(task_spec)
            
            if not exec_result.get("success"):
                # Self-healing was attempted but may have failed
                if exec_result.get("self_heal_attempts", 0) > 0:
                    logger.warning(
                        f"Step {i+1} failed after {exec_result['self_heal_attempts']} self-heal attempts"
                    )
                
                return {
                    "success": False,
                    "error": exec_result.get("error", f"Step {i+1} execution failed"),
                    "failed_at_step": i + 1,
                    "self_heal_attempts": exec_result.get("self_heal_attempts", 0)
                }
            
            # Store result for next step
            step_result = exec_result.get("result", {})
            if isinstance(step_result, dict):
                working_context[f"step_{i}_result"] = step_result
            cumulative_result.append({
                "step": i + 1,
                "description": step,
                "result": step_result
            })
        
        # All steps completed successfully
        return {
            "success": True,
            "result": cumulative_result,
            "steps_completed": len(steps)
        }
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a task."""
        if task_id in self._pending_tasks:
            return self._pending_tasks[task_id]
        if task_id in self._completed_tasks:
            return self._completed_tasks[task_id]
        return self._shared_context.get_task(task_id)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status."""
        return {
            "pending_tasks": len(self._pending_tasks),
            "completed_tasks": len(self._completed_tasks),
            "recent_failures": len(self._shared_context.get_recent_failures(10)),
            "executor_stats": self._executor.get_performance_stats(),
            "context_size": len(self._shared_context._execution_history)
        }
    
    def reset(self):
        """Reset supervisor state."""
        self._pending_tasks.clear()
        self._completed_tasks.clear()
        self._shared_context.clear_working_memory()
        logger.info("Supervisor reset complete")
