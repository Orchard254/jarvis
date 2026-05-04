"""
tools/apps/launcher.py — Application launcher tools

Tools for: open app, close app, list running apps
Uses subprocess and psutil for app management.
"""

import logging
import os
import subprocess
import time
from typing import Any, Optional

import psutil

from ..base import BaseTool, ToolResult

log = logging.getLogger("app_tools")

# Global tracking of last opened window handle (hwnd) for focus management
_last_opened_hwnd: Optional[int] = None
_last_opened_app: Optional[str] = None


def get_last_opened_hwnd() -> Optional[int]:
    """Get the hwnd of the last opened application."""
    return _last_opened_hwnd


def clear_last_opened_tracking():
    """Clear the last opened window tracking."""
    global _last_opened_hwnd, _last_opened_app
    _last_opened_hwnd = None
    _last_opened_app = None


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
        global _last_opened_hwnd, _last_opened_app
        
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
                    
                    # App already running - still try to bring its window to foreground
                    hwnd = find_window_by_process(executable)
                    if hwnd:
                        bring_to_foreground(hwnd)
                        _last_opened_hwnd = hwnd
                        _last_opened_app = app_name
                        log.info(f"Brought existing {app_name} window to foreground")
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
                        # Wait for window to appear and bring to foreground
                        time.sleep(1.0)
                        hwnd = find_window_by_process(executable)
                        if hwnd:
                            bring_to_foreground(hwnd)
                            _last_opened_hwnd = hwnd
                            _last_opened_app = app_name
                        return ToolResult.ok(f"Opening {app_name} with automation support (debug port 9222)")
                
                subprocess.Popen([executable], shell=True)
            
            # Wait briefly for window to appear and bring to foreground
            time.sleep(0.5)
            hwnd = find_window_by_process(executable)
            if hwnd:
                bring_to_foreground(hwnd)
                _last_opened_hwnd = hwnd
                _last_opened_app = app_name
                log.info(f"Brought newly opened {app_name} to foreground (hwnd={hwnd})")
            
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


# Helper functions for window management (using ctypes for Windows API)

def find_window_by_process(process_name: str) -> Optional[int]:
    """
    Find a window handle (hwnd) by process name.
    
    Returns the hwnd of the first matching window, or None if not found.
    """
    import ctypes
    from ctypes import wintypes
    
    # Get the process ID
    target_proc = process_name.lower()
    pid = None
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if target_proc in proc.info["name"].lower():
                pid = proc.info["pid"]
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if pid is None:
        return None
    
    # Find window by PID
    found_hwnd = None
    
    def callback(hwnd: int, lparam: int) -> bool:
        nonlocal found_hwnd
        from ctypes import windll
        
        # Check if window is visible
        if windll.user32.IsWindowVisible(hwnd):
            # Get the process ID for this window
            window_pid = ctypes.c_ulong()
            windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            
            if window_pid.value == pid:
                # Get window title to verify it's a real window
                title_buf = ctypes.create_unicode_buffer(256)
                windll.user32.GetWindowTextW(hwnd, title_buf, 256)
                if title_buf.value:  # Only consider windows with titles
                    found_hwnd = hwnd
                    return False  # Stop enumeration
        
        return True  # Continue enumeration
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    enum_func = WNDENUMPROC(callback)
    ctypes.windll.user32.EnumWindows(enum_func, 0)
    
    return found_hwnd


def bring_to_foreground(hwnd: int) -> bool:
    """
    Bring a window to the foreground.
    
    This uses proper Windows API calls to ensure the window actually receives focus.
    """
    import ctypes
    from ctypes import wintypes
    
    # Restore if minimized
    SW_RESTORE = 9
    ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
    
    # Try to set foreground - Windows may block this if another app is active
    # Use AttachThreadInput to bypass some restrictions
    try:
        # Get the foreground window and its thread
        fg_window = ctypes.windll.user32.GetForegroundWindow()
        fg_thread = ctypes.windll.user32.GetWindowThreadProcessId(fg_window, None)
        
        # Get our thread ID
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        
        # Attach our thread to the foreground thread
        ctypes.windll.user32.AttachThreadInput(fg_thread, current_thread, True)
        
        # Set focus and foreground
        ctypes.windll.user32.SetFocus(hwnd)
        result = ctypes.windll.user32.SetForegroundWindow(hwnd) != 0
        
        # Detach threads
        ctypes.windll.user32.AttachThreadInput(fg_thread, current_thread, False)
        
        return result
    except Exception as e:
        log.debug(f"AttachThreadInput failed, using simple SetForegroundWindow: {e}")
        # Fallback to simple approach
        return ctypes.windll.user32.SetForegroundWindow(hwnd) != 0
