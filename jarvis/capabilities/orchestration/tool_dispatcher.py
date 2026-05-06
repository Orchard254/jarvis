"""
tool_dispatcher: Executes selected tool

Routes execution requests to the appropriate capability implementation
with proper error handling and result validation.
"""

import logging
import time
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """
    Routes execution requests to appropriate capabilities with timeout protection.
    
    This is the execution engine that actually invokes capabilities. It provides:
    - Timeout protection for long-running operations
    - Error handling and recovery
    - Execution logging for debugging
    - Result validation
    """
    
    def __init__(self, max_workers: int = 5, default_timeout: float = 30.0):
        """
        Initialize the ToolDispatcher.
        
        Args:
            max_workers: Maximum concurrent tool executions
            default_timeout: Default timeout in seconds for tool execution
        """
        self._tools = {}
        self._execution_log = []
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def register_tool(self, name: str, tool_instance: Any):
        """
        Register a tool for dispatch.
        
        Args:
            name: Unique identifier for the tool
            tool_instance: Tool instance with execute() method
        """
        if not hasattr(tool_instance, 'execute'):
            raise ValueError(f"Tool '{name}' must have an execute() method")
        
        self._tools[name] = tool_instance
        logger.info(f"Registered tool: {name}")
    
    def unregister_tool(self, name: str):
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
    
    def execute(self, tool_name: str, parameters: Optional[dict] = None, 
                timeout: Optional[float] = None) -> dict:
        """
        Execute a tool with given parameters.
        
        Args:
            tool_name: Name of the capability to execute
            parameters: Parameters to pass to the tool
            timeout: Maximum execution time in seconds (uses default if None)
            
        Returns:
            Execution result with status, output/error, and metadata
        """
        if parameters is None:
            parameters = {}
        
        exec_timeout = timeout if timeout is not None else self._default_timeout
        
        # Check if tool exists
        if tool_name not in self._tools:
            error_msg = f"Tool '{tool_name}' not found"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "output": None,
                "tool": tool_name,
                "duration": 0.0
            }
        
        logger.info(f"Dispatching to {tool_name}: {parameters}")
        start_time = time.time()
        
        try:
            # Execute with timeout protection
            tool = self._tools[tool_name]
            result = self._execute_with_timeout(tool, parameters, exec_timeout)
            
            duration = time.time() - start_time
            
            # Validate result format
            if not isinstance(result, dict):
                result = {"output": result}
            
            # Ensure success flag exists
            if "success" not in result:
                result["success"] = True
            
            self._log_execution(tool_name, parameters, result, success=True, duration=duration)
            
            logger.info(f"Tool {tool_name} completed in {duration:.2f}s")
            
            return {
                "success": result.get("success", True),
                "error": result.get("error"),
                "output": result.get("output"),
                "tool": tool_name,
                "duration": duration
            }
            
        except FuturesTimeoutError:
            duration = time.time() - start_time
            error_msg = f"Tool execution timed out after {exec_timeout}s"
            logger.error(error_msg)
            
            self._log_execution(
                tool_name, parameters, {"error": error_msg}, 
                success=False, duration=duration
            )
            
            return {
                "success": False,
                "error": error_msg,
                "output": None,
                "tool": tool_name,
                "duration": duration
            }
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Tool execution failed: {tool_name} - {error_msg}")
            
            self._log_execution(
                tool_name, parameters, {"error": error_msg}, 
                success=False, duration=duration
            )
            
            return {
                "success": False,
                "error": error_msg,
                "output": None,
                "tool": tool_name,
                "duration": duration
            }
    
    def _execute_with_timeout(self, tool: Any, parameters: dict, timeout: float) -> Any:
        """
        Execute tool with timeout protection.
        
        Args:
            tool: Tool instance to execute
            parameters: Parameters for execution
            timeout: Timeout in seconds
            
        Returns:
            Tool execution result
            
        Raises:
            FuturesTimeoutError: If execution exceeds timeout
        """
        future = self._executor.submit(tool.execute, **parameters)
        
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise
    
    def _log_execution(self, tool_name: str, params: dict, result: dict, 
                       success: bool, duration: float = 0.0):
        """
        Log tool execution for debugging and evaluation.
        
        Args:
            tool_name: Name of executed tool
            params: Parameters passed to tool
            result: Result from tool execution
            success: Whether execution was successful
            duration: Execution duration in seconds
        """
        log_entry = {
            "timestamp": time.time(),
            "tool": tool_name,
            "parameters": params,
            "result": result,
            "success": success,
            "duration": duration
        }
        
        self._execution_log.append(log_entry)
        
        # Keep only last 1000 entries to prevent memory bloat
        if len(self._execution_log) > 1000:
            self._execution_log = self._execution_log[-1000:]
    
    def get_available_tools(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())
    
    def get_tool_info(self, tool_name: str) -> Optional[dict]:
        """
        Get information about a registered tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool information or None if not found
        """
        if tool_name not in self._tools:
            return None
        
        tool = self._tools[tool_name]
        return {
            "name": tool_name,
            "type": type(tool).__name__,
            "module": type(tool).__module__,
            "has_execute": hasattr(tool, 'execute')
        }
    
    def get_execution_log(self, limit: int = 100, 
                          filter_success: Optional[bool] = None) -> list[dict]:
        """
        Get recent execution log.
        
        Args:
            limit: Maximum number of entries to return
            filter_success: Filter by success status (None = all)
            
        Returns:
            List of log entries
        """
        log = self._execution_log[-limit:]
        
        if filter_success is not None:
            log = [entry for entry in log if entry["success"] == filter_success]
        
        return log
    
    def clear_execution_log(self):
        """Clear the execution log."""
        self._execution_log.clear()
    
    def get_statistics(self) -> dict:
        """
        Get dispatcher statistics.
        
        Returns:
            Dictionary with execution statistics
        """
        if not self._execution_log:
            return {
                "total_executions": 0,
                "successful": 0,
                "failed": 0,
                "avg_duration": 0.0
            }
        
        total = len(self._execution_log)
        successful = sum(1 for e in self._execution_log if e["success"])
        failed = total - successful
        avg_duration = sum(e["duration"] for e in self._execution_log) / total
        
        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0.0,
            "avg_duration": avg_duration,
            "registered_tools": len(self._tools)
        }
    
    def shutdown(self):
        """Shutdown the dispatcher and release resources."""
        logger.info("Shutting down ToolDispatcher...")
        self._executor.shutdown(wait=True)
        logger.info("ToolDispatcher shutdown complete")


# Singleton instance
_dispatcher_instance = None


def get_tool_dispatcher(max_workers: int = 5, 
                        default_timeout: float = 30.0) -> ToolDispatcher:
    """
    Get or create ToolDispatcher singleton.
    
    Args:
        max_workers: Maximum concurrent executions
        default_timeout: Default timeout in seconds
        
    Returns:
        ToolDispatcher instance
    """
    global _dispatcher_instance
    if _dispatcher_instance is None:
        _dispatcher_instance = ToolDispatcher(
            max_workers=max_workers,
            default_timeout=default_timeout
        )
    return _dispatcher_instance
