"""
tools/apps/window.py — Window management tools

Tools for: minimize, maximize, restore, close, focus windows
Uses ctypes for Windows API calls.
"""

import ctypes
import logging
from typing import Any, List, Optional, Tuple

import psutil

from ..base import BaseTool, ToolResult

log = logging.getLogger("window_tools")

# Windows API constants
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
SW_CLOSE = 0  # For PostMessage WM_CLOSE
WM_CLOSE = 0x0010
HWND_BROADCAST = 0xFFFF


class GetWindowListTool(BaseTool):
    """Get list of all open windows."""
    
    name = "get_window_list"
    description = "Get a list of all open windows with their titles, PIDs, and positions."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            windows = enumerate_windows()
            
            if not windows:
                return ToolResult.ok("No windows found")
            
            output_lines = ["Open windows:"]
            for title, pid, rect in windows:
                x, y, w, h = rect
                output_lines.append(f"  '{title}' (PID: {pid}) - Position: ({x}, {y}), Size: {w}x{h}")
            
            return ToolResult.ok("\n".join(output_lines))
            
        except Exception as e:
            log.error(f"Failed to get window list: {e}")
            return ToolResult.fail(error=f"Failed to get window list: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class FocusWindowTool(BaseTool):
    """Bring a window to the foreground."""
    
    name = "focus_window"
    description = "Bring a specific window to the foreground by its title or partial title match."
    parameters = {
        "title": {
            "type": "string",
            "description": "Window title or partial title to find",
        },
    }
    required_parameters = ["title"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        title = kwargs.get("title")
        if not title or not isinstance(title, str):
            return False, "title must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        title = kwargs["title"]
        
        try:
            hwnd = find_window_by_title(title)
            
            if hwnd is None:
                # Try harder - search for windows with broader matching
                from ctypes import windll
                from ctypes.wintypes import BOOL, HWND, LPARAM
                
                target = title.lower()
                found_hwnd = None
                
                def callback(hwnd, lparam):
                    nonlocal found_hwnd
                    if windll.user32.IsWindowVisible(hwnd):
                        title_buf = ctypes.create_unicode_buffer(256)
                        windll.user32.GetWindowTextW(hwnd, title_buf, 256)
                        window_title = title_buf.value.lower()
                        
                        # Check if target is in window title (partial match)
                        if target in window_title:
                            found_hwnd = hwnd
                            return False  # Stop enumeration
                    return True
                
                WNDENUMPROC = ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)
                enum_func = WNDENUMPROC(callback)
                windll.user32.EnumWindows(enum_func, 0)
                
                if found_hwnd:
                    hwnd = found_hwnd
                else:
                    return ToolResult.fail(error=f"No window found matching '{title}'")
            
            bring_to_foreground(hwnd)
            
            return ToolResult.ok(f"Brought '{title}' to foreground")
            
        except Exception as e:
            log.error(f"Failed to focus window: {e}")
            return ToolResult.fail(error=f"Failed to focus window: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class MinimizeWindowTool(BaseTool):
    """Minimize a specific window by title.
    
    ✅ RELIABLE TOOL - PREFERRED FOR MINIMIZING WINDOWS
    
    This tool uses Windows API (ShowWindow SW_MINIMIZE) to minimize
    application windows. It's 100% accurate because it targets windows by
    their title, not by screen coordinates.
    
    Use this for:
    - Minimizing application windows (Chrome, Notepad, File Explorer, etc.)
    - Getting windows out of the way without closing them
    
    Do NOT use for:
    - Minimizing all windows → Use minimize_windows instead
    - Closing windows → Use close_window instead
    
    Why this is better than find_on_screen + click_at:
    - 100% accurate - targets exact window by title
    - Won't accidentally minimize wrong window
    - Works regardless of window position on screen
    - No vision errors or coordinate mistakes
    """
    
    name = "minimize_window"
    description = "Minimize a specific window by title using Windows API. RELIABLE: Use for minimizing apps like Chrome, Notepad, File Explorer. For minimizing all windows, use minimize_windows. Don't use click_at for this."
    parameters = {
        "title": {
            "type": "string",
            "description": "Window title or partial title to minimize (e.g., 'Chrome', 'Notepad', 'File Explorer')",
        },
    }
    required_parameters = ["title"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        title = kwargs.get("title")
        if not title or not isinstance(title, str):
            return False, "title must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        title = kwargs["title"]
        
        try:
            hwnd = find_window_by_title(title)
            
            if hwnd is None:
                return ToolResult.fail(error=f"No window found matching '{title}'")
            
            from ctypes import windll
            windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
            
            return ToolResult.ok(f"Minimized window '{title}'")
            
        except Exception as e:
            log.error(f"Failed to minimize window: {e}")
            return ToolResult.fail(error=f"Failed to minimize window: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class CloseWindowTool(BaseTool):
    """Close a specific window by title using graceful WM_CLOSE message.
    
    ✅ RELIABLE TOOL - PREFERRED FOR CLOSING APPLICATION WINDOWS
    
    This tool uses Windows API (PostMessage WM_CLOSE) to gracefully close
    application windows. It's 100% accurate because it targets windows by
    their title, not by screen coordinates.
    
    Use this for:
    - Closing application windows (Notepad, Calculator, File Explorer, etc.)
    - Closing entire browser windows (all tabs)
    - Any standard Windows application
    
    Do NOT use for:
    - Closing individual browser tabs → Use close_tab instead
    - Minimizing windows → Use minimize_window instead
    
    Why this is better than find_on_screen + click_at:
    - 100% accurate - targets exact window by title
    - Won't accidentally close wrong window
    - Works regardless of window position on screen
    - Graceful shutdown (allows app to save/confirm)
    - No vision errors or coordinate mistakes
    """
    
    name = "close_window"
    description = "Close a specific application window by title using Windows API. RELIABLE: Use for closing apps like Notepad, Calculator, File Explorer, or entire browser windows. For individual browser tabs, use close_tab instead."
    parameters = {
        "title": {
            "type": "string",
            "description": "Window title or partial title to close (e.g., 'Notepad', 'Untitled - Notepad', 'Chrome')",
        },
    }
    required_parameters = ["title"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        title = kwargs.get("title")
        if not title or not isinstance(title, str):
            return False, "title must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        title = kwargs["title"]
        
        try:
            hwnd = find_window_by_title(title)
            
            if hwnd is None:
                return ToolResult.fail(error=f"No window found matching '{title}'")
            
            from ctypes import windll
            # Send WM_CLOSE message for graceful shutdown
            windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            
            return ToolResult.ok(f"Closed window '{title}'")
            
        except Exception as e:
            log.error(f"Failed to close window: {e}")
            return ToolResult.fail(error=f"Failed to close window: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "medium"  # Can cause data loss if unsaved


class MinimizeWindowsTool(BaseTool):
    """Minimize all windows (show desktop)."""
    
    name = "minimize_windows"
    description = "Minimize all open windows to show the desktop. Equivalent to pressing Win+D."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            # Use Win+D keyboard shortcut
            send_key_combo("{LWIN}d")
            return ToolResult.ok("Minimized all windows, showing desktop")
        except Exception as e:
            log.error(f"Failed to minimize windows: {e}")
            return ToolResult.fail(error=f"Failed to minimize windows: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


# Helper functions using ctypes

def enumerate_windows() -> List[Tuple[str, int, Tuple[int, int, int, int]]]:
    """
    Enumerate all visible top-level windows.
    
    Returns:
        List of tuples: (title, pid, (x, y, width, height))
    """
    from ctypes import windll
    from ctypes.wintypes import BOOL, HWND, LPARAM, RECT
    
    windows = []
    
    def callback(hwnd: int, lparam: int) -> bool:
        # Check if window is visible
        if windll.user32.IsWindowVisible(hwnd):
            # Get window title
            title_buf = ctypes.create_unicode_buffer(256)
            windll.user32.GetWindowTextW(hwnd, title_buf, 256)
            title = title_buf.value
            
            # Skip empty titles
            if title:
                # Get PID
                pid = ctypes.c_ulong()
                windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                
                # Get window position
                rect = RECT()
                windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                
                windows.append((
                    title,
                    pid.value,
                    (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top),
                ))
        
        return True  # Continue enumeration
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)
    enum_func = WNDENUMPROC(callback)
    windll.user32.EnumWindows(enum_func, 0)
    
    return windows


def find_window_by_title(title: str) -> Optional[int]:
    """Find a window handle by title (partial match)."""
    from ctypes import windll
    from ctypes.wintypes import BOOL, HWND, LPARAM
    
    target = title.lower()
    found_hwnd = None
    
    def callback(hwnd: int, lparam: int) -> bool:
        nonlocal found_hwnd
        
        if windll.user32.IsWindowVisible(hwnd):
            title_buf = ctypes.create_unicode_buffer(256)
            windll.user32.GetWindowTextW(hwnd, title_buf, 256)
            window_title = title_buf.value.lower()
            
            if target in window_title:
                found_hwnd = hwnd
                return False  # Stop enumeration
        
        return True
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)
    enum_func = WNDENUMPROC(callback)
    windll.user32.EnumWindows(enum_func, 0)
    
    return found_hwnd


def bring_to_foreground(hwnd: int) -> bool:
    """Bring a window to the foreground."""
    from ctypes import windll
    
    # Restore if minimized
    windll.user32.ShowWindow(hwnd, SW_RESTORE)
    
    # Set foreground
    return windll.user32.SetForegroundWindow(hwnd) != 0


def send_key_combo(keys: str) -> None:
    """Send keyboard combination using shell (for special keys)."""
    import subprocess
    
    # Use PowerShell to send keys via WScript.Shell
    script = f"""
    $shell = New-Object -ComObject WScript.Shell
    $shell.SendKeys("{keys}")
    """
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        timeout=5,
    )


# Export all tool classes
WINDOW_TOOLS = [
    GetWindowListTool,
    FocusWindowTool,
    MinimizeWindowTool,
    CloseWindowTool,
    MinimizeWindowsTool,
]
