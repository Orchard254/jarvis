"""
tools/tasks/background.py — Background task management tools

Tools for: task manager, background processes
Uses psutil, subprocess, and ctypes for process management.
Includes AdvancedTaskManager with all required methods.
"""

import ctypes
import logging
import subprocess
import time
from typing import Any, Dict, List, Optional

import psutil

from ..base import BaseTool, ToolResult

log = logging.getLogger("task_tools")


class AdvancedTaskManager:
    """
    Advanced task manager for background process control.
    
    Provides methods for starting commands, monitoring tasks,
    capturing output, and managing background processes.
    """
    
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._task_counter = 0
    
    def _is_process_running(self, pid: int) -> bool:
        """
        Check if a process is running using ctypes windll.kernel32.
        
        Args:
            pid: Process ID to check
            
        Returns:
            True if process is running, False otherwise
        """
        try:
            # Use ctypes to call OpenProcess and GetExitCodeProcess
            kernel32 = ctypes.windll.kernel32
            
            # PROCESS_QUERY_INFORMATION = 0x0400
            h_process = kernel32.OpenProcess(0x0400, False, pid)
            
            if not h_process:
                return False
            
            try:
                exit_code = ctypes.c_ulong()
                result = kernel32.GetExitCodeProcess(h_process, ctypes.byref(exit_code))
                
                if not result:
                    return False
                
                # STILL_ACTIVE = 259
                return exit_code.value == 259
            finally:
                kernel32.CloseHandle(h_process)
        except Exception:
            # Fallback to psutil if ctypes fails
            try:
                proc = psutil.Process(pid)
                return proc.is_running()
            except psutil.NoSuchProcess:
                return False
    
    def start_command(self, command: str, shell: bool = True, capture_output: bool = False) -> str:
        """
        Start a command in the background.
        
        Args:
            command: Command to execute
            shell: Whether to run in shell mode
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            Task ID string
        """
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        
        try:
            if capture_output:
                proc = subprocess.Popen(
                    command,
                    shell=shell,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            else:
                proc = subprocess.Popen(
                    command,
                    shell=shell,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            
            self._tasks[task_id] = {
                "pid": proc.pid,
                "process": proc,
                "command": command,
                "start_time": time.time(),
                "status": "running",
                "output": "",
                "error": "",
            }
            
            return task_id
            
        except Exception as e:
            log.error(f"Failed to start command: {e}")
            raise
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a task.
        
        Args:
            task_id: Task ID to check
            
        Returns:
            Dict with status information
        """
        if task_id not in self._tasks:
            return {"status": "not_found", "error": f"Task {task_id} not found"}
        
        task = self._tasks[task_id]
        pid = task["pid"]
        
        if self._is_process_running(pid):
            task["status"] = "running"
        else:
            task["status"] = "completed"
            # Get exit code if available
            try:
                task["exit_code"] = task["process"].poll()
            except Exception:
                task["exit_code"] = None
        
        return {
            "task_id": task_id,
            "status": task["status"],
            "pid": pid,
            "command": task["command"],
            "start_time": task["start_time"],
            "exit_code": task.get("exit_code"),
        }
    
    def get_output(self, task_id: str) -> str:
        """
        Get the captured output from a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Captured stdout output
        """
        if task_id not in self._tasks:
            return ""
        
        task = self._tasks[task_id]
        proc = task.get("process")
        
        if proc and proc.stdout:
            # Read any available output without blocking
            try:
                import select
                if select.select([proc.stdout], [], [], 0)[0]:
                    task["output"] += proc.stdout.read()
            except (ImportError, Exception):
                # Windows doesn't have select for pipes, use non-blocking read
                try:
                    task["output"] += proc.stdout.read()
                except Exception:
                    pass
        
        return task.get("output", "")
    
    def check_output(self, task_id: str) -> tuple[bool, str]:
        """
        Check if there's new output from a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Tuple of (has_output, output_content)
        """
        old_output = self._tasks.get(task_id, {}).get("output", "")
        new_output = self.get_output(task_id)
        
        if new_output and new_output != old_output:
            return True, new_output
        return False, old_output
    
    def kill_task(self, task_id: str) -> bool:
        """
        Kill a running task.
        
        Args:
            task_id: Task ID to kill
            
        Returns:
            True if killed successfully, False otherwise
        """
        if task_id not in self._tasks:
            return False
        
        task = self._tasks[task_id]
        proc = task.get("process")
        
        if proc:
            try:
                proc.kill()
                task["status"] = "killed"
                return True
            except Exception as e:
                log.error(f"Failed to kill task {task_id}: {e}")
                return False
        
        return False
    
    def wait_task(self, task_id: str, timeout: Optional[float] = None) -> bool:
        """
        Wait for a task to complete.
        
        Args:
            task_id: Task ID to wait for
            timeout: Maximum time to wait in seconds (None = infinite)
            
        Returns:
            True if completed, False if timed out
        """
        if task_id not in self._tasks:
            return False
        
        task = self._tasks[task_id]
        proc = task.get("process")
        
        if proc:
            try:
                proc.wait(timeout=timeout)
                task["status"] = "completed"
                return True
            except subprocess.TimeoutExpired:
                return False
            except Exception as e:
                log.error(f"Error waiting for task {task_id}: {e}")
                return False
        
        return False
    
    def clear_completed(self) -> int:
        """
        Clear all completed tasks from tracking.
        
        Returns:
            Number of tasks cleared
        """
        cleared = 0
        to_remove = []
        
        for task_id, task in self._tasks.items():
            if task["status"] in ("completed", "killed"):
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del self._tasks[task_id]
            cleared += 1
        
        return cleared


# Global task manager instance
_task_manager: Optional[AdvancedTaskManager] = None


def get_task_manager() -> AdvancedTaskManager:
    """Get the global task manager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = AdvancedTaskManager()
    return _task_manager


class TaskStartTool(BaseTool):
    """Start a background task."""
    
    name = "task_start"
    description = "Start a command in the background and return a task ID."
    parameters = {
        "command": {
            "type": "string",
            "description": "Command to execute in background",
        },
        "capture_output": {
            "type": "boolean",
            "description": "Whether to capture stdout/stderr (default: false)",
        },
    }
    required_parameters = ["command"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        command = kwargs.get("command")
        if not command:
            return False, "command parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        command = kwargs["command"]
        capture_output = kwargs.get("capture_output", False)
        
        try:
            tm = get_task_manager()
            task_id = tm.start_command(command, capture_output=capture_output)
            return ToolResult.ok(f"Started background task: {task_id}")
        except Exception as e:
            log.error(f"Failed to start task: {e}")
            return ToolResult.fail(error=f"Failed to start task: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "medium"


class TaskCheckTool(BaseTool):
    """Check task status."""
    
    name = "task_check"
    description = "Check the status of a background task."
    parameters = {
        "task_id": {
            "type": "string",
            "description": "Task ID to check",
        },
    }
    required_parameters = ["task_id"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        task_id = kwargs.get("task_id")
        if not task_id:
            return False, "task_id parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        task_id = kwargs["task_id"]
        
        try:
            tm = get_task_manager()
            status = tm.get_task_status(task_id)
            
            if status.get("status") == "not_found":
                return ToolResult.fail(error=status.get("error", "Task not found"))
            
            output = f"Task {task_id}:\n"
            output += f"  Status: {status['status']}\n"
            output += f"  PID: {status['pid']}\n"
            output += f"  Command: {status['command']}\n"
            if status.get('exit_code') is not None:
                output += f"  Exit Code: {status['exit_code']}\n"
            
            return ToolResult.ok(output)
        except Exception as e:
            log.error(f"Failed to check task: {e}")
            return ToolResult.fail(error=f"Failed to check task: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "low"


class TaskOutputTool(BaseTool):
    """Get task output."""
    
    name = "task_output"
    description = "Get the captured output from a background task."
    parameters = {
        "task_id": {
            "type": "string",
            "description": "Task ID to get output from",
        },
    }
    required_parameters = ["task_id"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        task_id = kwargs.get("task_id")
        if not task_id:
            return False, "task_id parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        task_id = kwargs["task_id"]
        
        try:
            tm = get_task_manager()
            output = tm.get_output(task_id)
            
            if output:
                return ToolResult.ok(f"Output from {task_id}:\n{output}")
            else:
                return ToolResult.ok(f"No output captured for {task_id}")
        except Exception as e:
            log.error(f"Failed to get task output: {e}")
            return ToolResult.fail(error=f"Failed to get task output: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "low"


class TaskKillTool(BaseTool):
    """Kill a background task."""
    
    name = "task_kill"
    description = "Kill a running background task."
    parameters = {
        "task_id": {
            "type": "string",
            "description": "Task ID to kill",
        },
    }
    required_parameters = ["task_id"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        task_id = kwargs.get("task_id")
        if not task_id:
            return False, "task_id parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        task_id = kwargs["task_id"]
        
        try:
            tm = get_task_manager()
            
            if tm.kill_task(task_id):
                return ToolResult.ok(f"Killed task: {task_id}")
            else:
                return ToolResult.fail(error=f"Failed to kill task: {task_id}")
        except Exception as e:
            log.error(f"Failed to kill task: {e}")
            return ToolResult.fail(error=f"Failed to kill task: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "medium"


class TaskWaitTool(BaseTool):
    """Wait for a task to complete."""
    
    name = "task_wait"
    description = "Wait for a background task to complete."
    parameters = {
        "task_id": {
            "type": "string",
            "description": "Task ID to wait for",
        },
        "timeout": {
            "type": "integer",
            "description": "Maximum seconds to wait (default: 60)",
        },
    }
    required_parameters = ["task_id"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        task_id = kwargs.get("task_id")
        if not task_id:
            return False, "task_id parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        task_id = kwargs["task_id"]
        timeout = kwargs.get("timeout", 60)
        
        try:
            tm = get_task_manager()
            
            if tm.wait_task(task_id, timeout=timeout):
                return ToolResult.ok(f"Task {task_id} completed")
            else:
                return ToolResult.fail(error=f"Task {task_id} timed out after {timeout}s")
        except Exception as e:
            log.error(f"Failed to wait for task: {e}")
            return ToolResult.fail(error=f"Failed to wait for task: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return min(kwargs.get("timeout", 60), 30)
    
    def risk_level(self) -> str:
        return "low"


class TaskClearTool(BaseTool):
    """Clear completed tasks."""
    
    name = "task_clear"
    description = "Clear all completed tasks from tracking."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            tm = get_task_manager()
            count = tm.clear_completed()
            return ToolResult.ok(f"Cleared {count} completed task(s)")
        except Exception as e:
            log.error(f"Failed to clear tasks: {e}")
            return ToolResult.fail(error=f"Failed to clear tasks: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.1
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
TASK_TOOLS = [
    TaskStartTool,
    TaskCheckTool,
    TaskOutputTool,
    TaskKillTool,
    TaskWaitTool,
    TaskClearTool,
]
