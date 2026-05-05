"""
tools/executor.py — Tool execution dispatcher

Replaces the giant if-else chain in pc_control.py.
Dispatches tool calls to appropriate handlers based on tool name.
"""

import logging
from typing import Any, Dict, Optional

from .base import ToolResult
from .registry import get_registry, execute_tool as registry_execute

log = logging.getLogger("tool_executor")


class ToolExecutor:
    """
    Central dispatcher for tool execution.
    
    Routes tool calls to the appropriate handler and manages:
    - Pre-execution validation
    - Post-execution verification
    - Error handling and retry logic
    - Result formatting
    """
    
    def __init__(self):
        self._registry = get_registry()
        self._execution_history = []
        self._max_history = 100
    
    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        verify: bool = True,
    ) -> ToolResult:
        """
        Execute a tool with the given arguments.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Dictionary of tool arguments
            verify: Whether to attempt post-execution verification
            
        Returns:
            ToolResult with success/failure status
        """
        log.info(f"Executing tool: {tool_name} with args: {arguments}")
        
        # Check if tool exists first
        if not self._registry.has_tool(tool_name):
            error_msg = f"Unknown tool: '{tool_name}'"
            available = sorted(self._registry.get_tool_names())
            if available:
                # Find similar names
                similar = [t for t in available if tool_name.lower() in t.lower()]
                if similar:
                    error_msg += f". Did you mean: {', '.join(similar[:3])}?"
                error_msg += f"\nAvailable tools: {', '.join(available[:15])}"
                if len(available) > 15:
                    error_msg += f"... ({len(available)} total)"
            
            result = ToolResult.fail(error=error_msg, exit_code=-2)
            result.tool_name = tool_name
            return result
        
        # Execute via registry (includes validation)
        result = registry_execute(tool_name, **arguments)
        
        # Store in history
        self._execution_history.append({
            "tool": tool_name,
            "args": arguments,
            "success": result.success,
        })
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]
        
        # Attempt verification if requested and tool succeeded
        if verify and result.success:
            verify_result = self._verify_execution(tool_name, arguments, result)
            result.verified = verify_result["verified"]
            result.verify_msg = verify_result["message"]
        
        return result
    
    def _verify_execution(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: ToolResult,
    ) -> Dict[str, Any]:
        """
        Attempt to verify that a tool execution had the intended effect.
        
        Args:
            tool_name: Name of executed tool
            arguments: Arguments that were passed
            result: Execution result
            
        Returns:
            Dict with 'verified' (bool) and 'message' (str)
        """
        # Default: assume verified if no specific verification logic
        verified_checks = {
            "set_volume": self._verify_volume,
            "open_app": self._verify_app_open,
            "close_app": self._verify_app_closed,
            "create_file": self._verify_file_exists,
            "delete_file": self._verify_file_deleted,
        }
        
        check_func = verified_checks.get(tool_name)
        if check_func:
            try:
                return check_func(arguments, result)
            except Exception as e:
                log.warning(f"Verification failed for {tool_name}: {e}")
                return {"verified": False, "message": f"Verification error: {e}"}
        
        # No specific verification - mark as not verified but not an error
        return {"verified": False, "message": "No verification check defined"}
    
    def _verify_volume(self, arguments: Dict, result: ToolResult) -> Dict[str, Any]:
        """Verify volume was set correctly."""
        from .audio.volume import get_current_volume
        
        expected_level = arguments.get("level")
        if expected_level is None:
            return {"verified": False, "message": "No level specified"}
        
        actual_level = get_current_volume()
        if actual_level == expected_level:
            return {"verified": True, "message": f"Volume confirmed at {actual_level}%"}
        else:
            return {"verified": False, "message": f"Expected {expected_level}%, got {actual_level}%"}
    
    def _verify_app_open(self, arguments: Dict, result: ToolResult) -> Dict[str, Any]:
        """Verify app is running."""
        import psutil
        
        # Support both 'app' (preferred) and 'app_name' (legacy) parameter names
        app_name = arguments.get("app") or arguments.get("app_name", "")
        if not app_name:
            return {"verified": False, "message": "No app name specified"}
        app_name = app_name.lower()
        
        for proc in psutil.process_iter(["name"]):
            if app_name in proc.info["name"].lower():
                return {"verified": True, "message": f"{app_name} is running"}
        
        return {"verified": False, "message": f"{app_name} not found in running processes"}
    
    def _verify_app_closed(self, arguments: Dict, result: ToolResult) -> Dict[str, Any]:
        """Verify app is not running."""
        import psutil
        
        # Support both 'app' (preferred) and 'app_name' (legacy) parameter names
        app_name = arguments.get("app") or arguments.get("app_name", "")
        if not app_name:
            return {"verified": False, "message": "No app name specified"}
        app_name = app_name.lower()
        
        for proc in psutil.process_iter(["name"]):
            if app_name in proc.info["name"].lower():
                return {"verified": False, "message": f"{app_name} is still running"}
        
        return {"verified": True, "message": f"{app_name} is not running"}
    
    def _verify_file_exists(self, arguments: Dict, result: ToolResult) -> Dict[str, Any]:
        """Verify file was created."""
        import os
        
        path = arguments.get("path", "")
        if not path:
            return {"verified": False, "message": "No path specified"}
        
        if os.path.exists(path):
            return {"verified": True, "message": f"File exists: {path}"}
        else:
            return {"verified": False, "message": f"File not found: {path}"}
    
    def _verify_file_deleted(self, arguments: Dict, result: ToolResult) -> Dict[str, Any]:
        """Verify file was deleted."""
        import os
        
        path = arguments.get("path", "")
        if not path:
            return {"verified": False, "message": "No path specified"}
        
        if not os.path.exists(path):
            return {"verified": True, "message": f"File deleted: {path}"}
        else:
            return {"verified": False, "message": f"File still exists: {path}"}
    
    def get_execution_history(self, limit: int = 10) -> list:
        """Get recent execution history."""
        return self._execution_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear execution history."""
        self._execution_history.clear()


# Global executor instance
_executor: Optional[ToolExecutor] = None


def get_executor() -> ToolExecutor:
    """Get the global tool executor instance."""
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
    return _executor


def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    verify: bool = True,
) -> ToolResult:
    """Execute a tool via the global executor."""
    return get_executor().execute(tool_name, arguments, verify)
