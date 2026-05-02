"""
tools/apps/launcher.py — Application launcher tools

Tools for: open app, close app, list running apps
Uses subprocess and psutil for app management.
"""

import logging
import subprocess
from typing import Any

import psutil

from ..base import BaseTool, ToolResult

log = logging.getLogger("app_tools")


class OpenAppTool(BaseTool):
    """Open an application."""
    
    name = "open_app"
    description = "Open an application by name. Common apps: chrome, notepad, calculator, word, excel, edge, vscode, spotify."
    parameters = {
        "app_name": {
            "type": "string",
            "description": "Name of the application to open",
        },
    }
    required_parameters = ["app_name"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        app_name = kwargs.get("app_name")
        if not app_name or not isinstance(app_name, str):
            return False, "app_name must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        app_name = kwargs["app_name"].strip().lower()
        
        # Map common names to executables
        app_map = {
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "word": "winword.exe",
            "microsoft word": "winword.exe",
            "excel": "excel.exe",
            "microsoft excel": "excel.exe",
            "powerpoint": "powerpnt.exe",
            "edge": "msedge.exe",
            "microsoft edge": "msedge.exe",
            "vscode": "Code.exe",
            "visual studio code": "Code.exe",
            "spotify": "spotify.exe",
            "discord": "Discord.exe",
            "slack": "slack.exe",
            "teams": "Teams.exe",
            "outlook": "outlook.exe",
            "onenote": "onenote.exe",
            "paint": "mspaint.exe",
            "snipping tool": "SnippingTool.exe",
            "task manager": "Taskmgr.exe",
            "control panel": "control.exe",
            "settings": "ms-settings:",
            "store": "explorer.exe shell:AppsFolder",
            "file explorer": "explorer.exe",
            "terminal": "wt.exe",
            "powershell": "powershell.exe",
            "cmd": "cmd.exe",
            "command prompt": "cmd.exe",
        }
        
        executable = app_map.get(app_name, app_name)
        
        try:
            # Check if already running
            for proc in psutil.process_iter(["name"]):
                if executable.lower() in proc.info["name"].lower():
                    return ToolResult.ok(f"{app_name} is already running")
            
            # Try to start the app
            if executable.startswith("shell:"):
                # Special URI handler
                subprocess.Popen(["start", executable], shell=True)
            elif executable.endswith(":"):
                # Settings URI
                subprocess.Popen(["start", executable], shell=True)
            else:
                subprocess.Popen([executable], shell=True)
            
            return ToolResult.ok(f"Opening {app_name}")
            
        except Exception as e:
            log.error(f"Failed to open {app_name}: {e}")
            return ToolResult.fail(error=f"Failed to open {app_name}: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.0
    
    def risk_level(self) -> str:
        return "low"


class CloseAppTool(BaseTool):
    """Close/kill an application."""
    
    name = "close_app"
    description = "Force-close an application by name. Use with caution as unsaved work will be lost."
    parameters = {
        "app_name": {
            "type": "string",
            "description": "Name of the application to close",
        },
        "force": {
            "type": "boolean",
            "description": "Force kill without graceful shutdown (default: true)",
        },
    }
    required_parameters = ["app_name"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        app_name = kwargs.get("app_name")
        if not app_name or not isinstance(app_name, str):
            return False, "app_name must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        app_name = kwargs["app_name"].strip().lower()
        force = kwargs.get("force", True)
        
        closed_count = 0
        
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if app_name in proc.info["name"].lower():
                        if force:
                            proc.kill()
                        else:
                            proc.terminate()
                        closed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if closed_count > 0:
                return ToolResult.ok(f"Closed {closed_count} instance(s) of {app_name}")
            else:
                return ToolResult.ok(f"{app_name} was not running")
                
        except Exception as e:
            log.error(f"Failed to close {app_name}: {e}")
            return ToolResult.fail(error=f"Failed to close {app_name}: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "medium"  # Can cause data loss


class ListRunningAppsTool(BaseTool):
    """List all running applications."""
    
    name = "list_running_apps"
    description = "List all currently running applications with their process names and PIDs."
    parameters = {
        "limit": {
            "type": "integer",
            "description": "Maximum number of apps to return (default: 20)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        limit = kwargs.get("limit", 20)
        if not isinstance(limit, int) or limit < 1:
            return False, "limit must be a positive integer"
        if limit > 100:
            return False, "limit cannot exceed 100"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        limit = min(kwargs.get("limit", 20), 100)
        
        try:
            apps = []
            seen_names = set()
            
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    name = proc.info["name"]
                    if name and name not in seen_names:
                        apps.append((name, proc.info["pid"]))
                        seen_names.add(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Sort alphabetically and limit
            apps.sort(key=lambda x: x[0].lower())
            apps = apps[:limit]
            
            output = "\n".join(f"{name} (PID: {pid})" for name, pid in apps)
            return ToolResult.ok(f"Running apps ({len(apps)} shown):\n{output}")
            
        except Exception as e:
            log.error(f"Failed to list running apps: {e}")
            return ToolResult.fail(error=f"Failed to list running apps: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
LAUNCHER_TOOLS = [
    OpenAppTool,
    CloseAppTool,
    ListRunningAppsTool,
]
