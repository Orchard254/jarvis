"""
tools/tasks/background.py — Background task management tools

Tools for: task manager, background processes
Uses psutil and subprocess for process management.
"""

import logging
import subprocess
from typing import Any, Dict, List, Optional

import psutil

from ..base import BaseTool, ToolResult

log = logging.getLogger("task_tools")


class TaskManagerTool(BaseTool):
    """View and manage running tasks/processes."""
    
    name = "task_manager"
    description = "Get information about running processes or kill a specific process by name or PID."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["list", "kill"],
            "description": "Action to perform: 'list' to show processes, 'kill' to terminate one",
        },
        "process_name": {
            "type": "string",
            "description": "Process name to kill (required for kill action)",
        },
        "pid": {
            "type": "integer",
            "description": "Process ID to kill (alternative to process_name)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["list", "kill"]:
            return False, "action must be 'list' or 'kill'"
        
        if action == "kill":
            process_name = kwargs.get("process_name")
            pid = kwargs.get("pid")
            if not process_name and pid is None:
                return False, "Either process_name or pid is required for kill action"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list")
        
        if action == "list":
            return self._list_processes()
        else:
            process_name = kwargs.get("process_name")
            pid = kwargs.get("pid")
            return self._kill_process(process_name, pid)
    
    def _list_processes(self) -> ToolResult:
        """List top processes by resource usage."""
        try:
            processes = []
            
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    info = proc.info
                    processes.append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "cpu": info["cpu_percent"] or 0,
                        "memory": info["memory_percent"] or 0,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Sort by CPU usage and take top 15
            processes.sort(key=lambda x: x["cpu"], reverse=True)
            top_processes = processes[:15]
            
            lines = ["Top processes by CPU:"]
            for p in top_processes:
                lines.append(f"  {p['name']:25} PID: {p['pid']:6}  CPU: {p['cpu']:5.1f}%  Mem: {p['memory']:5.1f}%")
            
            return ToolResult.ok("\n".join(lines))
            
        except Exception as e:
            log.error(f"Failed to list processes: {e}")
            return ToolResult.fail(error=f"Failed to list processes: {e}")
    
    def _kill_process(self, process_name: Optional[str], pid: Optional[int]) -> ToolResult:
        """Kill a process by name or PID."""
        try:
            killed_count = 0
            
            if pid is not None:
                # Kill by PID
                try:
                    proc = psutil.Process(pid)
                    proc.kill()
                    killed_count = 1
                except psutil.NoSuchProcess:
                    return ToolResult.fail(error=f"No process found with PID {pid}")
                except psutil.AccessDenied:
                    return ToolResult.fail(error=f"Access denied to kill process {pid}")
            else:
                # Kill by name
                for proc in psutil.process_iter(["pid", "name"]):
                    try:
                        if process_name.lower() in proc.info["name"].lower():
                            proc.kill()
                            killed_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            
            if killed_count > 0:
                return ToolResult.ok(f"Killed {killed_count} process(es) matching '{process_name or pid}'")
            else:
                return ToolResult.fail(error=f"No processes found matching '{process_name}'")
                
        except Exception as e:
            log.error(f"Failed to kill process: {e}")
            return ToolResult.fail(error=f"Failed to kill process: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "high"  # Can kill important processes


# Export all tool classes
TASK_TOOLS = [
    TaskManagerTool,
]
