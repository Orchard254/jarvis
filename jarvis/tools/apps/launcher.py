"""
tools/apps/launcher.py — Application launcher tools

Tools for: open app, close app, list running apps
Uses subprocess and psutil for app management.
"""

import logging
import os
import subprocess
from typing import Any

import psutil

from ..base import BaseTool, ToolResult

log = logging.getLogger("app_tools")


# Complete app mappings as required - all entries from original pc_control.py
APP_MAPPINGS = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "spotify": "spotify.exe",
    "vscode": "Code.exe",
    "visual studio code": "Code.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "task manager": "Taskmgr.exe",
    "control panel": "control.exe",
    "settings": "ms-settings:",
}


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
        
        # Use the complete app_mappings dict
        executable = APP_MAPPINGS.get(app_name, app_name)
        
        try:
            # Check if already running
            for proc in psutil.process_iter(["name"]):
                if executable.lower() in proc.info["name"].lower():
                    log.info(f"{app_name} is already running")
                    # For Chrome, check if debug port is enabled
                    if app_name in ["chrome", "google chrome"]:
                        try:
                            cmdline = ' '.join(proc.cmdline())
                            if '--remote-debugging-port=' in cmdline:
                                # Extract the port number
                                for part in cmdline.split():
                                    if part.startswith('--remote-debugging-port='):
                                        port = part.split('=')[1]
                                        return ToolResult.ok(f"{app_name} is already running with automation support (debug port {port})")
                                return ToolResult.ok(f"{app_name} is already running with automation support")
                            else:
                                log.info("Chrome running without debug port. Launching second instance for automation...")
                                # Don't kill existing Chrome - launch a second instance with debug port
                                chrome_paths = [
                                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                                    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                                ]
                                chrome_path = None
                                for path in chrome_paths:
                                    if os.path.exists(path):
                                        chrome_path = path
                                        break
                                
                                if chrome_path:
                                    args = [
                                        chrome_path,
                                        "--remote-debugging-port=9222",
                                        "--no-first-run",
                                        "--no-default-browser-check",
                                        "--user-data-dir=" + os.path.join(os.getenv('TEMP', ''), 'jarvis_chrome_profile'),
                                    ]
                                    subprocess.Popen(args)
                                    return ToolResult.ok(f"Launched additional Chrome instance for automation (debug port 9222). Your original Chrome session remains unchanged.")
                        except Exception as e:
                            log.warning(f"Error checking Chrome cmdline: {e}")
                    
                    return ToolResult.ok(f"{app_name} is already running")
            
            # Try to start the app
            if executable.startswith("shell:") or executable.endswith(":"):
                # Special URI handler (e.g., ms-settings:)
                subprocess.Popen(["start", executable], shell=True)
            else:
                # For Chrome, always launch with debug port
                if app_name in ["chrome", "google chrome"]:
                    chrome_paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                    ]
                    chrome_path = None
                    for path in chrome_paths:
                        if os.path.exists(path):
                            chrome_path = path
                            break
                    
                    if chrome_path:
                        args = [
                            chrome_path,
                            "--remote-debugging-port=9222",
                            "--no-first-run",
                            "--no-default-browser-check",
                        ]
                        subprocess.Popen(args)
                        return ToolResult.ok(f"Opening {app_name} with automation support (debug port 9222)")
                
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
