"""
tools/consolidated.py — 30-tool consolidated schema

This module implements the final 30-tool schema with zero duplication.
Complexity moves into arguments, not tool count.
"""

import logging
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult

log = logging.getLogger("consolidated_tools")

# ============================================================================
# 1. APPLICATION & WINDOW CONTROL (4 tools)
# ============================================================================


class AppControlTool(BaseTool):
    """Open, close, or list applications."""
    
    name = "app_control"
    description = "Control applications: open, close, or list running apps."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["open", "close", "list"],
            "description": "Action to perform",
        },
        "app_name": {
            "type": "string",
            "description": "Name of the application (required for open/close)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["open", "close", "list"]:
            return False, f"Invalid action: {action}. Must be open, close, or list."
        if action in ["open", "close"] and not kwargs.get("app_name"):
            return False, f"app_name required for {action} action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        # Delegate to existing implementations
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        app_name = kwargs.get("app_name")
        
        if action == "list":
            return registry.execute("list_running_apps", limit=kwargs.get("limit", 20))
        elif action == "open":
            return registry.execute("open_app", app=app_name)
        elif action == "close":
            force = kwargs.get("force", True)
            return registry.execute("close_app", app=app_name, force=force)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class WindowControlTool(BaseTool):
    """Focus, minimize, maximize, close, or list windows."""
    
    name = "window_control"
    description = "Control windows: focus, minimize, maximize, close, or list all windows."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["focus", "minimize", "maximize", "close", "list"],
            "description": "Action to perform",
        },
        "window_id": {
            "type": "string",
            "description": "Window identifier (optional for list, required for others)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["focus", "minimize", "maximize", "close", "list"]:
            return False, f"Invalid action: {action}."
        if action != "list" and not kwargs.get("window_id"):
            return False, f"window_id required for {action} action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        window_id = kwargs.get("window_id")
        
        if action == "list":
            return registry.execute("get_window_list")
        elif action == "focus":
            return registry.execute("focus_window", window_id=window_id)
        elif action == "minimize":
            return registry.execute("minimize_window", window_id=window_id)
        elif action == "maximize":
            # May need to implement or delegate
            return ToolResult.ok(f"Maximize window {window_id} - placeholder")
        elif action == "close":
            return registry.execute("close_window", window_id=window_id)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class BrowserControlTool(BaseTool):
    """Control browser: open, close, new tab, close tab, list tabs."""
    
    name = "browser_control"
    description = "Control the web browser: open, close, manage tabs."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["open", "close", "new_tab", "close_tab", "list_tabs"],
            "description": "Action to perform",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        valid_actions = ["open", "close", "new_tab", "close_tab", "list_tabs"]
        if action not in valid_actions:
            return False, f"Invalid action: {action}."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        
        if action == "open":
            url = kwargs.get("url", "https://www.google.com")
            return registry.execute("open_url", url=url)
        elif action == "close":
            return registry.execute("close_browser")
        elif action == "new_tab":
            url = kwargs.get("url")
            if url:
                return registry.execute("navigate_to_url", url=url, new_tab=True)
            return ToolResult.ok("New tab opened")
        elif action == "close_tab":
            tab_id = kwargs.get("tab_id")
            return registry.execute("close_tab", tab_id=tab_id)
        elif action == "list_tabs":
            return ToolResult.ok("Listing tabs - placeholder")
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class TabControlTool(BaseTool):
    """Switch or close browser tabs."""
    
    name = "tab_control"
    description = "Switch between tabs or close a specific tab."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["switch", "close"],
            "description": "Action to perform",
        },
        "tab_id": {
            "type": "string",
            "description": "Tab identifier",
        },
    }
    required_parameters = ["action", "tab_id"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["switch", "close"]:
            return False, f"Invalid action: {action}."
        if not kwargs.get("tab_id"):
            return False, "tab_id is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        tab_id = kwargs.get("tab_id")
        
        if action == "switch":
            return registry.execute("switch_tab", tab_id=tab_id)
        elif action == "close":
            return registry.execute("close_tab", tab_id=tab_id)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


# ============================================================================
# 2. INTERACTION LAYER (2 tools)
# ============================================================================


class ComputerInteractTool(BaseTool):
    """Click, type, keypress, or scroll on the computer."""
    
    name = "computer_interact"
    description = "Low-level computer interaction: click, type, send keypress, scroll."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["click", "type", "keypress", "scroll"],
            "description": "Interaction type",
        },
        "target": {
            "type": "string",
            "description": "Target coordinates or element (e.g., 'x,y' for click)",
        },
        "value": {
            "type": "string",
            "description": "Value to type or key to press",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["click", "type", "keypress", "scroll"]:
            return False, f"Invalid action: {action}."
        if action == "type" and not kwargs.get("value"):
            return False, "value required for type action."
        if action == "keypress" and not kwargs.get("value"):
            return False, "value (key) required for keypress action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        target = kwargs.get("target")
        value = kwargs.get("value")
        
        if action == "click":
            if target:
                x, y = map(int, target.split(","))
                return registry.execute("click_at", x=x, y=y)
            return registry.execute("click_element", selector=value)
        elif action == "type":
            return registry.execute("type_text", text=value)
        elif action == "keypress":
            return registry.execute("press_key", key=value)
        elif action == "scroll":
            direction = value or "down"
            return ToolResult.ok(f"Scroll {direction} - placeholder")
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class WebInteractTool(BaseTool):
    """Click, fill, submit, or extract from web pages."""
    
    name = "web_interact"
    description = "Web page interaction: click, fill input, submit form, extract content."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["click", "fill", "submit", "extract"],
            "description": "Interaction type",
        },
        "selector": {
            "type": "string",
            "description": "CSS selector or XPath for the target element",
        },
        "value": {
            "type": "string",
            "description": "Value to fill or extract",
        },
    }
    required_parameters = ["action", "selector"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["click", "fill", "submit", "extract"]:
            return False, f"Invalid action: {action}."
        if not kwargs.get("selector"):
            return False, "selector is required."
        if action == "fill" and not kwargs.get("value"):
            return False, "value required for fill action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        selector = kwargs.get("selector")
        value = kwargs.get("value")
        
        if action == "click":
            return registry.execute("click_element", selector=selector)
        elif action == "fill":
            return registry.execute("fill_input", selector=selector, value=value)
        elif action == "submit":
            return registry.execute("submit_form", selector=selector)
        elif action == "extract":
            return registry.execute("extract_content", selector=selector)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


# ============================================================================
# 3. VISION & PERCEPTION (3 tools)
# ============================================================================


class ScreenshotTool(BaseTool):
    """Take a screenshot of the current screen."""
    
    name = "screenshot"
    description = "Capture a screenshot of the current screen."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        return registry.execute("screenshot")


class VisionAnalyzeTool(BaseTool):
    """Analyze an image with a query."""
    
    name = "vision_analyze"
    description = "Analyze an image using vision AI with a specific query."
    parameters = {
        "image": {
            "type": "string",
            "description": "Path to image or base64 encoded image",
        },
        "query": {
            "type": "string",
            "description": "Question or instruction for analyzing the image",
        },
    }
    required_parameters = ["image", "query"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("image"):
            return False, "image is required."
        if not kwargs.get("query"):
            return False, "query is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        image = kwargs.get("image")
        query = kwargs.get("query")
        
        return registry.execute("analyze_screen", image=image, query=query)


class FindOnScreenTool(BaseTool):
    """Find an object or text on the screen."""
    
    name = "find_on_screen"
    description = "Locate a target object, icon, or text on the screen."
    parameters = {
        "image": {
            "type": "string",
            "description": "Optional reference image to find",
        },
        "target_description": {
            "type": "string",
            "description": "Description of what to find (text, icon, button, etc.)",
        },
    }
    required_parameters = ["target_description"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("target_description"):
            return False, "target_description is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        image = kwargs.get("image")
        target = kwargs.get("target_description")
        
        return registry.execute("find_on_screen", image=image, target=target)


# ============================================================================
# 4. FILE SYSTEM (3 tools)
# ============================================================================


class FileSystemTool(BaseTool):
    """Read, write, delete, open, or list files."""
    
    name = "file_system"
    description = "File operations: read, write, delete, open, or list directory contents."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["read", "write", "delete", "open", "list"],
            "description": "File operation to perform",
        },
        "path": {
            "type": "string",
            "description": "File or directory path",
        },
        "content": {
            "type": "string",
            "description": "Content to write (for write action)",
        },
    }
    required_parameters = ["action", "path"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["read", "write", "delete", "open", "list"]:
            return False, f"Invalid action: {action}."
        if not kwargs.get("path"):
            return False, "path is required."
        if action == "write" and not kwargs.get("content"):
            return False, "content required for write action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        path = kwargs.get("path")
        content = kwargs.get("content")
        
        if action == "read":
            return registry.execute("read_file", path=path)
        elif action == "write":
            return registry.execute("create_file", path=path, content=content)
        elif action == "delete":
            return registry.execute("delete_file", path=path)
        elif action == "open":
            return registry.execute("open_file", path=path)
        elif action == "list":
            return registry.execute("list_files", path=path)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class FileSearchTool(BaseTool):
    """Search for files by name or content."""
    
    name = "file_search"
    description = "Search for files by name pattern or content."
    parameters = {
        "query": {
            "type": "string",
            "description": "Search query (filename pattern or content)",
        },
        "path": {
            "type": "string",
            "description": "Directory to search in (optional, defaults to home)",
        },
    }
    required_parameters = ["query"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("query"):
            return False, "query is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        query = kwargs.get("query")
        path = kwargs.get("path")
        
        # May need to implement file search or delegate
        return ToolResult.ok(f"Searching for '{query}' in {path or 'default location'} - placeholder")


class FileMetadataTool(BaseTool):
    """Get metadata about a file."""
    
    name = "file_metadata"
    description = "Get file metadata: size, creation date, modification date, permissions."
    parameters = {
        "path": {
            "type": "string",
            "description": "File path",
        },
    }
    required_parameters = ["path"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("path"):
            return False, "path is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        import os
        import stat
        from datetime import datetime
        
        path = kwargs.get("path")
        
        try:
            stat_info = os.stat(path)
            metadata = {
                "size": stat_info.st_size,
                "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                "accessed": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
            }
            return ToolResult.ok(str(metadata))
        except Exception as e:
            return ToolResult.fail(error=f"Failed to get metadata: {e}")


# ============================================================================
# 5. SYSTEM & OS (4 tools)
# ============================================================================


class SystemQueryTool(BaseTool):
    """Query system information: info, health, uptime, processes, time."""
    
    name = "system_query"
    description = "Query system status: general info, health check, uptime, running processes, or current time."
    parameters = {
        "type": {
            "type": "string",
            "enum": ["info", "health", "uptime", "processes", "time"],
            "description": "Type of system query",
        },
    }
    required_parameters = ["type"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        query_type = kwargs.get("type")
        valid_types = ["info", "health", "uptime", "processes", "time"]
        if query_type not in valid_types:
            return False, f"Invalid type: {query_type}."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        query_type = kwargs.get("type")
        
        if query_type == "info":
            return registry.execute("system_info")
        elif query_type == "health":
            return registry.execute("system_health")
        elif query_type == "uptime":
            return registry.execute("get_uptime")
        elif query_type == "processes":
            return registry.execute("get_top_processes")
        elif query_type == "time":
            return registry.execute("get_time")
        
        return ToolResult.fail(error=f"Unknown query type: {query_type}")


class ProcessControlTool(BaseTool):
    """List, kill, or inspect processes."""
    
    name = "process_control"
    description = "Control processes: list all, kill by PID, or inspect process details."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["list", "kill", "inspect"],
            "description": "Action to perform",
        },
        "process_id": {
            "type": "integer",
            "description": "Process ID (required for kill/inspect)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["list", "kill", "inspect"]:
            return False, f"Invalid action: {action}."
        if action in ["kill", "inspect"] and not kwargs.get("process_id"):
            return False, f"process_id required for {action} action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        pid = kwargs.get("process_id")
        
        if action == "list":
            return registry.execute("get_top_processes")
        elif action == "kill":
            return registry.execute("task_kill", pid=pid)
        elif action == "inspect":
            return registry.execute("task_output", pid=pid)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class PowerControlTool(BaseTool):
    """Shutdown, restart, sleep, or lock the computer."""
    
    name = "power_control"
    description = "Power management: shutdown, restart, sleep, or lock the PC."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["shutdown", "restart", "sleep", "lock"],
            "description": "Power action to perform",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["shutdown", "restart", "sleep", "lock"]:
            return False, f"Invalid action: {action}."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        
        if action == "shutdown":
            return registry.execute("shutdown_pc")
        elif action == "restart":
            return registry.execute("restart_pc")
        elif action == "sleep":
            return registry.execute("sleep_pc")
        elif action == "lock":
            return registry.execute("lock_pc")
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class SettingsControlTool(BaseTool):
    """Control system settings: brightness, dark mode, volume."""
    
    name = "settings_control"
    description = "Control system settings: brightness, dark mode toggle, or volume level."
    parameters = {
        "setting": {
            "type": "string",
            "enum": ["brightness", "dark_mode", "volume"],
            "description": "Setting to control",
        },
        "value": {
            "type": "string",
            "description": "Value to set (percentage for brightness/volume, true/false for dark_mode)",
        },
    }
    required_parameters = ["setting"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        setting = kwargs.get("setting")
        if setting not in ["brightness", "dark_mode", "volume"]:
            return False, f"Invalid setting: {setting}."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        setting = kwargs.get("setting")
        value = kwargs.get("value")
        
        if setting == "brightness":
            level = int(value) if value else 50
            return registry.execute("set_brightness", level=level)
        elif setting == "dark_mode":
            enable = value.lower() == "true" if value else True
            return registry.execute("toggle_dark_mode", enable=enable)
        elif setting == "volume":
            level = int(value) if value else 50
            return registry.execute("set_volume", level=level)
        
        return ToolResult.fail(error=f"Unknown setting: {setting}")


# ============================================================================
# 6. NETWORK (2 tools)
# ============================================================================


class NetworkQueryTool(BaseTool):
    """Query network status: wifi, IP, connection status."""
    
    name = "network_query"
    description = "Query network information: WiFi status, IP address, or connection status."
    parameters = {
        "type": {
            "type": "string",
            "enum": ["wifi", "ip", "status"],
            "description": "Type of network query",
        },
    }
    required_parameters = ["type"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        query_type = kwargs.get("type")
        if query_type not in ["wifi", "ip", "status"]:
            return False, f"Invalid type: {query_type}."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        query_type = kwargs.get("type")
        
        if query_type == "wifi":
            return registry.execute("get_wifi")
        elif query_type == "ip":
            return registry.execute("get_ip")
        elif query_type == "status":
            return ToolResult.ok("Network status - placeholder")
        
        return ToolResult.fail(error=f"Unknown query type: {query_type}")


class NetworkTestTool(BaseTool):
    """Test network connectivity: ping or latency check."""
    
    name = "network_test"
    description = "Test network connectivity: ping a host or measure latency."
    parameters = {
        "type": {
            "type": "string",
            "enum": ["ping", "latency"],
            "description": "Type of network test",
        },
        "target": {
            "type": "string",
            "description": "Target host to test (e.g., google.com)",
        },
    }
    required_parameters = ["type", "target"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        test_type = kwargs.get("type")
        if test_type not in ["ping", "latency"]:
            return False, f"Invalid type: {test_type}."
        if not kwargs.get("target"):
            return False, "target is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        test_type = kwargs.get("type")
        target = kwargs.get("target")
        
        if test_type == "ping":
            return registry.execute("ping", host=target)
        elif test_type == "latency":
            return registry.execute("ping", host=target)
        
        return ToolResult.fail(error=f"Unknown test type: {test_type}")


# ============================================================================
# 7. EXECUTION LAYER (3 tools)
# ============================================================================


class ShellExecuteTool(BaseTool):
    """Execute shell commands."""
    
    name = "shell_execute"
    description = "Execute a shell command with optional admin privileges."
    parameters = {
        "command": {
            "type": "string",
            "description": "Shell command to execute",
        },
        "admin": {
            "type": "boolean",
            "description": "Run with admin privileges (default: false)",
        },
    }
    required_parameters = ["command"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("command"):
            return False, "command is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        command = kwargs.get("command")
        admin = kwargs.get("admin", False)
        
        return registry.execute("run_command", command=command, admin=admin)


class PythonExecuteTool(BaseTool):
    """Execute Python code."""
    
    name = "python_execute"
    description = "Execute Python code safely."
    parameters = {
        "code": {
            "type": "string",
            "description": "Python code to execute",
        },
    }
    required_parameters = ["code"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("code"):
            return False, "code is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        code = kwargs.get("code")
        return registry.execute("run_python", code=code)


class TaskManagerTool(BaseTool):
    """Manage background tasks: start, check status, wait, kill, get result."""
    
    name = "task_manager"
    description = "Manage background tasks: start new task, check status, wait for completion, kill, or get result."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["start", "status", "wait", "kill", "result"],
            "description": "Task management action",
        },
        "task_id": {
            "type": "string",
            "description": "Task identifier (required for status/wait/kill/result)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["start", "status", "wait", "kill", "result"]:
            return False, f"Invalid action: {action}."
        if action in ["status", "wait", "kill", "result"] and not kwargs.get("task_id"):
            return False, f"task_id required for {action} action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        task_id = kwargs.get("task_id")
        command = kwargs.get("command")
        
        if action == "start":
            return registry.execute("task_start", command=command)
        elif action == "status":
            return registry.execute("task_check", task_id=task_id)
        elif action == "wait":
            return registry.execute("task_wait", task_id=task_id)
        elif action == "kill":
            return registry.execute("task_kill", task_id=task_id)
        elif action == "result":
            return registry.execute("task_output", task_id=task_id)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


# ============================================================================
# 8. WEB & SEARCH (2 tools)
# ============================================================================


class WebSearchTool(BaseTool):
    """Search the web."""
    
    name = "web_search"
    description = "Search the web using a query."
    parameters = {
        "query": {
            "type": "string",
            "description": "Search query",
        },
    }
    required_parameters = ["query"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("query"):
            return False, "query is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        query = kwargs.get("query")
        return registry.execute("search_web", query=query)


class WebNavigateTool(BaseTool):
    """Navigate to a URL."""
    
    name = "web_navigate"
    description = "Navigate to a specific URL in the browser."
    parameters = {
        "url": {
            "type": "string",
            "description": "URL to navigate to",
        },
    }
    required_parameters = ["url"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("url"):
            return False, "url is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        url = kwargs.get("url")
        return registry.execute("navigate_to_url", url=url)


# ============================================================================
# 9. STATE & MEMORY (2 tools)
# ============================================================================


class NotesManagerTool(BaseTool):
    """Create, read, or delete notes."""
    
    name = "notes_manager"
    description = "Manage notes: create new note, read existing notes, or delete."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["create", "read", "delete"],
            "description": "Action to perform",
        },
        "content": {
            "type": "string",
            "description": "Note content (for create) or note ID (for read/delete)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["create", "read", "delete"]:
            return False, f"Invalid action: {action}."
        if action == "create" and not kwargs.get("content"):
            return False, "content required for create action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        content = kwargs.get("content")
        
        if action == "create":
            return registry.execute("create_note", content=content)
        elif action == "read":
            return registry.execute("read_notes", note_id=content)
        elif action == "delete":
            return registry.execute("delete_note", note_id=content)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class TodoManagerTool(BaseTool):
    """Add, list, complete, or delete todo items."""
    
    name = "todo_manager"
    description = "Manage todo list: add item, list all, mark complete, or delete."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["add", "list", "complete", "delete"],
            "description": "Action to perform",
        },
        "item": {
            "type": "string",
            "description": "Todo item text (for add) or item ID (for complete/delete)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["add", "list", "complete", "delete"]:
            return False, f"Invalid action: {action}."
        if action == "add" and not kwargs.get("item"):
            return False, "item required for add action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        item = kwargs.get("item")
        
        if action == "add":
            return registry.execute("add_todo", task=item)
        elif action == "list":
            return registry.execute("list_todos")
        elif action == "complete":
            return registry.execute("complete_todo", task_id=item)
        elif action == "delete":
            return registry.execute("delete_todo", task_id=item)
        
        return ToolResult.fail(error=f"Unknown action: {action}")


# ============================================================================
# 10. UTILITIES (5 tools)
# ============================================================================


class ClipboardTool(BaseTool):
    """Copy to or paste from clipboard."""
    
    name = "clipboard"
    description = "Clipboard operations: copy text to clipboard or paste from clipboard."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["copy", "paste"],
            "description": "Clipboard action",
        },
        "content": {
            "type": "string",
            "description": "Content to copy (for copy action)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["copy", "paste"]:
            return False, f"Invalid action: {action}."
        if action == "copy" and not kwargs.get("content"):
            return False, "content required for copy action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        content = kwargs.get("content")
        
        if action == "copy":
            return registry.execute("copy_to_clipboard", text=content)
        elif action == "paste":
            return registry.execute("paste_from_clipboard")
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class TimerTool(BaseTool):
    """Set, check, or cancel a timer."""
    
    name = "timer"
    description = "Timer management: set a timer, check status, or cancel."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["set", "check", "cancel"],
            "description": "Timer action",
        },
        "duration": {
            "type": "string",
            "description": "Duration in seconds or 'X minutes' format (for set action)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["set", "check", "cancel"]:
            return False, f"Invalid action: {action}."
        if action == "set" and not kwargs.get("duration"):
            return False, "duration required for set action."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        duration = kwargs.get("duration")
        
        if action == "set":
            return registry.execute("set_timer", duration=duration)
        elif action == "check":
            return ToolResult.ok("Timer check - placeholder")
        elif action == "cancel":
            return ToolResult.ok("Timer cancelled - placeholder")
        
        return ToolResult.fail(error=f"Unknown action: {action}")


class CalculateTool(BaseTool):
    """Calculate mathematical expressions."""
    
    name = "calculate"
    description = "Evaluate mathematical expressions."
    parameters = {
        "expression": {
            "type": "string",
            "description": "Mathematical expression to evaluate",
        },
    }
    required_parameters = ["expression"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        if not kwargs.get("expression"):
            return False, "expression is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        expression = kwargs.get("expression")
        return registry.execute("calculate", expression=expression)


class TextTransformTool(BaseTool):
    """Summarize, rewrite, or translate text."""
    
    name = "text_transform"
    description = "Transform text: summarize, rewrite, or translate."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["summarize", "rewrite", "translate"],
            "description": "Transformation type",
        },
        "text": {
            "type": "string",
            "description": "Text to transform",
        },
    }
    required_parameters = ["action", "text"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["summarize", "rewrite", "translate"]:
            return False, f"Invalid action: {action}."
        if not kwargs.get("text"):
            return False, "text is required."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        # This would typically call an LLM for transformation
        action = kwargs.get("action")
        text = kwargs.get("text")
        
        # Placeholder - would call LLM in production
        return ToolResult.ok(f"{action.capitalize()} operation on text - placeholder")


class DateTimeTool(BaseTool):
    """Get current time or convert timezones."""
    
    name = "date_time"
    description = "Get current date/time or convert between timezones."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["now", "convert"],
            "description": "DateTime action",
        },
        "input": {
            "type": "string",
            "description": "Timezone for conversion (for convert action)",
        },
    }
    required_parameters = ["action"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        action = kwargs.get("action")
        if action not in ["now", "convert"]:
            return False, f"Invalid action: {action}."
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        
        action = kwargs.get("action")
        tz = kwargs.get("input")
        
        if action == "now":
            return registry.execute("get_date")
        elif action == "convert":
            return ToolResult.ok(f"Timezone conversion for {tz} - placeholder")
        
        return ToolResult.fail(error=f"Unknown action: {action}")


# Export all consolidated tools
CONSOLIDATED_TOOLS = [
    # 1. Application & Window Control (4)
    AppControlTool,
    WindowControlTool,
    BrowserControlTool,
    TabControlTool,
    # 2. Interaction Layer (2)
    ComputerInteractTool,
    WebInteractTool,
    # 3. Vision & Perception (3)
    ScreenshotTool,
    VisionAnalyzeTool,
    FindOnScreenTool,
    # 4. File System (3)
    FileSystemTool,
    FileSearchTool,
    FileMetadataTool,
    # 5. System & OS (4)
    SystemQueryTool,
    ProcessControlTool,
    PowerControlTool,
    SettingsControlTool,
    # 6. Network (2)
    NetworkQueryTool,
    NetworkTestTool,
    # 7. Execution Layer (3)
    ShellExecuteTool,
    PythonExecuteTool,
    TaskManagerTool,
    # 8. Web & Search (2)
    WebSearchTool,
    WebNavigateTool,
    # 9. State & Memory (2)
    NotesManagerTool,
    TodoManagerTool,
    # 10. Utilities (5)
    ClipboardTool,
    TimerTool,
    CalculateTool,
    TextTransformTool,
    DateTimeTool,
]
