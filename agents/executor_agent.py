"""
Executor Agent - Tier 3 Multi-Agent System

Handles tool interaction and error recovery.
Executes code and manages the Execute-Detect-Analyze-Patch-Retry workflow.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from safety.executor import execute as safety_execute
from tools import TOOL_REGISTRY
from tools.system import execute_code

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    Responsible for executing tasks and handling errors.
    
    Implements the self-healing workflow:
    1. EXECUTE: Run the task/code
    2. DETECT: Identify if execution failed
    3. ANALYZE: Determine root cause of failure
    4. PATCH: Generate fix (via CoderAgent)
    5. RETRY: Attempt with corrected approach
    
    Features:
    - Infinite loop prevention
    - Drift detection
    - Graceful fallback mechanisms
    - Retry with exponential backoff
    """
    
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 1.0  # seconds
    MAX_RETRY_DELAY = 10.0
    
    def __init__(self, shared_context=None, coder_agent=None):
        self._shared_context = shared_context
        self._coder_agent = coder_agent
        self._name = "ExecutorAgent"
        self._retry_counts: Dict[str, int] = {}
        self._execution_times: Dict[str, List[float]] = {}
        self._previous_fixes: Dict[str, List[str]] = {}  # Track previous fix attempts per task
    
    def execute_task(self, task_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task with full self-healing capabilities.
        
        Args:
            task_spec: Dict containing:
                - type: 'code' or 'tool'
                - code: Python code (if type='code')
                - tool_name: Tool to call (if type='tool')
                - args: Arguments for tool
                - description: Human-readable description
                
        Returns:
            Dict with success, result, error, retries, self_heal_attempts
        """
        task_id = task_spec.get("task_id", f"task_{time.time()}")
        
        if self._shared_context:
            self._shared_context.set_agent_state(self._name, {
                "action": "execute_task",
                "task_id": task_id,
                "type": task_spec.get("type", "unknown")
            })
        
        result = {
            "success": False,
            "result": None,
            "error": None,
            "retries": 0,
            "self_heal_attempts": 0,
            "task_id": task_id
        }
        
        # Initialize tracking for this task
        if task_id not in self._previous_fixes:
            self._previous_fixes[task_id] = []
        
        original_code = task_spec.get("code", "")
        current_code = original_code
        retry_count = 0
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # EXECUTE phase
                exec_result = self._execute_internal(task_spec, current_code)
                
                # DETECT phase
                if self._is_success(exec_result):
                    result["success"] = True
                    result["result"] = exec_result
                    result["retries"] = attempt
                    
                    if self._shared_context:
                        self._shared_context.record_execution(
                            self._name, f"execute_{task_spec.get('type', 'task')}",
                            exec_result, success=True
                        )
                    
                    logger.info(f"ExecutorAgent: Task {task_id[:8]} succeeded on attempt {attempt + 1}")
                    return result
                
                # Failure detected - proceed to self-healing
                error_msg = self._extract_error(exec_result)
                result["error"] = error_msg
                result["retries"] = attempt
                
                if attempt >= self.MAX_RETRIES:
                    break  # Max retries reached
                
                # ANALYZE phase
                diagnosis = self._analyze_failure(error_msg, current_code, task_spec)
                
                # PATCH phase (if we have a coder agent)
                if self._coder_agent and current_code:
                    # Build context with full failure history
                    fix_context = {
                        "diagnosis": diagnosis,
                        "retry_count": retry_count,
                        "previous_fixes": self._previous_fixes.get(task_id, [])
                    }
                    
                    fix_result = self._attempt_self_heal(current_code, error_msg, fix_context)
                    if fix_result.get("success") and fix_result.get("fixed_code"):
                        current_code = fix_result["fixed_code"]
                        result["self_heal_attempts"] += 1
                        
                        # Record this fix attempt for future context
                        fix_summary = f"Attempt #{retry_count + 1}: {fix_result.get('diagnosis', 'unknown')} - Changes: {fix_result.get('changes_made', [])}"
                        self._previous_fixes[task_id].append(fix_summary)
                        
                        # Update task spec with fixed code
                        task_spec = {**task_spec, "code": current_code}
                        
                        logger.info(f"Self-heal patch applied: {fix_result.get('diagnosis', 'unknown')}")
                    else:
                        logger.warning(f"Self-heal failed: {fix_result.get('diagnosis', 'unknown')}")
                        # Still record the failed attempt
                        self._previous_fixes[task_id].append(f"Attempt #{retry_count + 1}: FAILED - {fix_result.get('diagnosis', 'unknown')}")
                
                retry_count += 1
                
                # Exponential backoff before retry
                delay = min(self.BASE_RETRY_DELAY * (2 ** attempt), self.MAX_RETRY_DELAY)
                time.sleep(delay)
                
            except Exception as e:
                error_msg = str(e)
                result["error"] = error_msg
                result["retries"] = attempt
                
                logger.error(f"ExecutorAgent exception: {e}")
                
                if attempt >= self.MAX_RETRIES:
                    break
                
                # Try to recover from exceptions too
                if self._coder_agent and current_code:
                    fix_context = {
                        "diagnosis": {"type": "exception"},
                        "retry_count": retry_count,
                        "previous_fixes": self._previous_fixes.get(task_id, [])
                    }
                    fix_result = self._attempt_self_heal(current_code, error_msg, fix_context)
                    if fix_result.get("success") and fix_result.get("fixed_code"):
                        current_code = fix_result["fixed_code"]
                        task_spec = {**task_spec, "code": current_code}
                        result["self_heal_attempts"] += 1
                        
                        # Record this fix attempt
                        fix_summary = f"Attempt #{retry_count + 1} (exception recovery): {fix_result.get('diagnosis', 'unknown')}"
                        self._previous_fixes[task_id].append(fix_summary)
                    
                    retry_count += 1
        
        # Final failure - apply graceful fallback
        if not result["success"]:
            fallback = self._get_fallback(task_spec, result["error"])
            if fallback:
                result["fallback_applied"] = True
                result["fallback_result"] = fallback
        
        if self._shared_context:
            self._shared_context.record_execution(
                self._name, f"execute_{task_spec.get('type', 'task')}",
                result, success=result["success"]
            )
        
        return result
    
    def execute_tool(self, tool_name: str, args: Dict[str, Any], 
                     plan: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute a tool with error handling.
        
        Args:
            tool_name: Name of the tool to execute
            args: Arguments to pass to the tool
            plan: Optional plan metadata for confidence scoring
            
        Returns:
            Dict with tool execution result
        """
        if self._shared_context:
            self._shared_context.set_agent_state(self._name, {
                "action": "execute_tool",
                "tool": tool_name
            })
        
        start_time = time.time()
        
        try:
            if tool_name not in TOOL_REGISTRY:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}"
                }
            
            tool_fn = TOOL_REGISTRY[tool_name]
            result = safety_execute(tool_name, tool_fn, args, plan=plan)
            
            elapsed = time.time() - start_time
            self._record_execution_time(tool_name, elapsed)
            
            if self._shared_context:
                self._shared_context.record_execution(
                    self._name, f"tool_{tool_name}",
                    result, success=result.get("success", False)
                )
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            self._record_execution_time(tool_name, elapsed)
            
            error_result = {
                "success": False,
                "error": str(e),
                "tool": tool_name
            }
            
            if self._shared_context:
                self._shared_context.record_execution(
                    self._name, f"tool_{tool_name}",
                    error_result, success=False
                )
            
            return error_result
    
    def _execute_internal(self, task_spec: Dict, code: str) -> Dict[str, Any]:
        """Internal execution logic."""
        task_type = task_spec.get("type", "code")
        
        if task_type == "code":
            # Execute Python code
            result = safety_execute(
                "execute_code",
                execute_code,
                {"code": code, "language": "python"},
                plan=task_spec.get("plan")
            )
            return result
        elif task_type == "tool":
            # Execute a tool
            return self.execute_tool(
                task_spec.get("tool_name"),
                task_spec.get("args", {}),
                plan=task_spec.get("plan")
            )
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}
    
    def _is_success(self, result: Dict) -> bool:
        """Determine if execution was successful."""
        if not isinstance(result, dict):
            return False
        
        # Check explicit success flag
        if "success" in result:
            return result.get("success", False)
        
        # Check for error indicators
        if result.get("error"):
            return False
        if result.get("stderr"):
            return False
        
        # Default to success if we have a result
        return True
    
    def _extract_error(self, result: Dict) -> str:
        """Extract error message from failed result."""
        if not isinstance(result, dict):
            return str(result)
        
        # Try various error fields
        for field in ["error", "stderr", "message", "exception"]:
            if result.get(field):
                return str(result[field])
        
        return "Unknown error"
    
    def _analyze_failure(self, error_msg: str, code: str, 
                         task_spec: Dict) -> Dict[str, Any]:
        """Analyze the root cause of a failure."""
        error_lower = error_msg.lower()
        
        analysis = {
            "type": "unknown",
            "severity": "medium",
            "recoverable": True,
            "suggested_action": "retry_with_fix"
        }
        
        # Classify error type
        if "syntax" in error_lower or "invalid syntax" in error_lower:
            analysis["type"] = "syntax_error"
            analysis["recoverable"] = True
        elif "nameerror" in error_lower or "not defined" in error_lower:
            analysis["type"] = "name_error"
            analysis["recoverable"] = True
        elif "filenotfound" in error_lower or "no such file" in error_lower:
            analysis["type"] = "file_not_found"
            analysis["suggested_action"] = "verify_path"
        elif "permission" in error_lower or "access is denied" in error_lower:
            analysis["type"] = "permission_error"
            analysis["recoverable"] = False
            analysis["suggested_action"] = "escalate"
        elif "timeout" in error_lower or "timed out" in error_lower:
            analysis["type"] = "timeout"
            analysis["suggested_action"] = "increase_timeout"
        elif "module" in error_lower and "not found" in error_lower:
            analysis["type"] = "missing_module"
            analysis["suggested_action"] = "install_or_alternative"
        
        # Check for infinite loop indicators
        if self._detect_infinite_loop(code):
            analysis["type"] = "infinite_loop"
            analysis["recoverable"] = True
            analysis["suggested_action"] = "add_termination"
        
        return analysis
    
    def _attempt_self_heal(self, code: str, error_msg: str, 
                           diagnosis: Dict) -> Dict[str, Any]:
        """Attempt to fix the code using the CoderAgent."""
        if not self._coder_agent:
            return {"success": False, "diagnosis": "No coder agent available"}
        
        return self._coder_agent.fix_code(code, error_msg, {"diagnosis": diagnosis})
    
    def _detect_infinite_loop(self, code: str) -> bool:
        """Detect potential infinite loops in code."""
        # Simple heuristic checks
        import re
        
        # Look for while True without obvious break
        while_matches = re.findall(r'while\s+True\s*:', code)
        if while_matches:
            # Check if there's a break statement in the same block
            if 'break' not in code:
                return True
        
        # Look for recursion without base case
        func_defs = re.findall(r'def\s+(\w+)\s*\([^)]*\):', code)
        for func_name in func_defs:
            # Check if function calls itself
            if re.search(rf'{func_name}\s*\(', code):
                # Very basic check - real detection would need AST analysis
                pass
        
        return False
    
    def _detect_drift(self, original_intent: str, current_result: Dict) -> bool:
        """Detect if execution has drifted from original intent."""
        # Placeholder for drift detection
        # Would compare expected outcome vs actual result
        return False
    
    def _get_fallback(self, task_spec: Dict, error: str) -> Optional[Any]:
        """Get graceful fallback for failed task."""
        task_type = task_spec.get("type", "code")
        
        if task_type == "code":
            # Return informative error message
            return {
                "message": "Code execution failed after multiple attempts",
                "error": error,
                "suggestion": "Please review the code or try a different approach"
            }
        
        return None
    
    def _record_execution_time(self, operation: str, elapsed: float):
        """Record execution time for performance monitoring."""
        if operation not in self._execution_times:
            self._execution_times[operation] = []
        self._execution_times[operation].append(elapsed)
        
        # Keep only last 100 measurements
        if len(self._execution_times[operation]) > 100:
            self._execution_times[operation] = self._execution_times[operation][-100:]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for this agent."""
        stats = {}
        for op, times in self._execution_times.items():
            if times:
                stats[op] = {
                    "avg": sum(times) / len(times),
                    "min": min(times),
                    "max": max(times),
                    "count": len(times)
                }
        return stats
