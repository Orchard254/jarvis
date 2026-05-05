"""
tools/refactored_examples.py — Refactored tool definitions with strict schemas

This file demonstrates the refactored tool pattern with:
1. Strict naming convention: <domain>.<verb>_<object>
2. Typed JSON schemas with enums for constrained inputs
3. Proper validation and execution

These are EXAMPLES showing the pattern. In production, each tool would be
in its own module following this same structure.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult

log = logging.getLogger("refactored_tools")


# =============================================================================
# SYSTEM TOOLS
# =============================================================================

class SystemLockPCTool(BaseTool):
    """Lock the computer immediately."""
    
    name = "system.lock_pc"
    description = "Lock the PC immediately using Windows lock screen. Safe operation that doesn't close any apps or files."
    category = "system"
    
    # Strict typed schema
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            subprocess.run(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                check=False,
            )
            return ToolResult.ok("PC locked successfully")
        except Exception as e:
            log.error(f"Failed to lock PC: {e}")
            return ToolResult.fail(error=f"Failed to lock PC: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class SystemSleepPCTool(BaseTool):
    """Put the computer to sleep."""
    
    name = "system.sleep_pc"
    description = "Put the PC to sleep. All open apps and files will be preserved in memory."
    category = "system"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            script = """
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)
            """
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                return ToolResult.ok("PC entering sleep mode")
            else:
                return ToolResult.fail(error=f"Sleep failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error="Sleep command timed out")
        except Exception as e:
            log.error(f"Failed to sleep PC: {e}")
            return ToolResult.fail(error=f"Failed to sleep PC: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.0
    
    def risk_level(self) -> str:
        return "low"


class SystemRestartPCTool(BaseTool):
    """Restart the computer (requires confirmation)."""
    
    name = "system.restart_pc"
    description = "Restart the PC. WARNING: This will close all applications. Unsaved work may be lost."
    category = "system"
    
    parameters = {
        "type": "object",
        "properties": {
            "force": {
                "type": "boolean",
                "description": "Force restart without waiting for apps to close (default: false)",
            },
            "delay_seconds": {
                "type": "integer",
                "description": "Delay before restart in seconds (default: 0, max: 60)",
            },
        },
        "required": []
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        delay = kwargs.get("delay_seconds", 0)
        if not isinstance(delay, int) or delay < 0:
            return False, "delay_seconds must be a non-negative integer"
        if delay > 60:
            return False, "delay_seconds cannot exceed 60 seconds"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        force = kwargs.get("force", False)
        delay = min(kwargs.get("delay_seconds", 0), 60)
        
        try:
            flags = "/r /t " + str(delay)
            if force:
                flags += " /f"
            
            result = subprocess.run(
                ["shutdown", flags],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                if delay > 0:
                    return ToolResult.ok(f"Restart scheduled in {delay} seconds")
                else:
                    return ToolResult.ok("Restarting now")
            else:
                return ToolResult.fail(error=f"Restart failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error="Restart command timed out")
        except Exception as e:
            log.error(f"Failed to restart PC: {e}")
            return ToolResult.fail(error=f"Failed to restart PC: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        delay = kwargs.get("delay_seconds", 0)
        return float(delay) + 2.0
    
    def risk_level(self) -> str:
        return "high"


# =============================================================================
# FILE TOOLS
# =============================================================================

def is_safe_path(path: str) -> tuple[bool, str]:
    """Check if a path is safe to operate on (not system-critical)."""
    try:
        resolved = Path(path).resolve()
        path_str = str(resolved).lower()
        
        blocked_prefixes = [
            r"c:\windows",
            r"c:\program files",
            r"c:\program files (x86)",
            r"c:\users\all users",
            r"c:\programdata",
        ]
        
        for prefix in blocked_prefixes:
            if path_str.startswith(prefix):
                return False, f"Access denied: Cannot modify system path '{prefix}'"
        
        return True, ""
    except Exception as e:
        return False, f"Invalid path: {e}"


class FileReadTool(BaseTool):
    """Read contents of a text file."""
    
    name = "file.read"
    description = "Read the contents of a text file. Returns up to 10KB of content."
    category = "files"
    
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Full path to the file to read",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum lines to read (default: 100)",
            },
        },
        "required": ["path"]
    }
    required_parameters = ["path"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        path = kwargs.get("path")
        if not path:
            return False, "path parameter is required"
        
        is_safe, error = is_safe_path(path)
        if not is_safe:
            return False, error
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        path = kwargs["path"]
        max_lines = kwargs.get("max_lines", 100)
        
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult.fail(error=f"File not found: {path}")
            
            if not file_path.is_file():
                return ToolResult.fail(error=f"Not a file: {path}")
            
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"... ({max_lines} lines shown)")
                        break
                    lines.append(line.rstrip())
            
            content = "\n".join(lines)
            return ToolResult.ok(content[:10000])
            
        except PermissionError:
            return ToolResult.fail(error=f"Permission denied: {path}")
        except Exception as e:
            log.error(f"Failed to read file: {e}")
            return ToolResult.fail(error=f"Failed to read file: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


class FileWriteTool(BaseTool):
    """Create or overwrite a file with content."""
    
    name = "file.write"
    description = "Create a new file or overwrite an existing file with the specified content."
    category = "files"
    
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Full path where to create/write the file",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["path", "content"]
    }
    required_parameters = ["path", "content"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        path = kwargs.get("path")
        content = kwargs.get("content")
        
        if not path:
            return False, "path parameter is required"
        if content is None:
            return False, "content parameter is required"
        
        is_safe, error = is_safe_path(path)
        if not is_safe:
            return False, error
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        path = kwargs["path"]
        content = kwargs["content"]
        
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return ToolResult.ok(f"Created file: {path}")
            
        except PermissionError:
            return ToolResult.fail(error=f"Permission denied: {path}")
        except Exception as e:
            log.error(f"Failed to create file: {e}")
            return ToolResult.fail(error=f"Failed to create file: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "medium"


class FileOpenTool(BaseTool):
    """Open a file with its default application."""
    
    name = "file.open"
    description = "Open a file with its default associated application."
    category = "files"
    
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Full path to the file to open",
            },
        },
        "required": ["path"]
    }
    required_parameters = ["path"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        path = kwargs.get("path")
        if not path:
            return False, "path parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        path = kwargs["path"]
        
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult.fail(error=f"File not found: {path}")
            
            subprocess.Popen(
                ["start", str(file_path)],
                shell=True,
            )
            
            return ToolResult.ok(f"Opening {path}")
            
        except Exception as e:
            log.error(f"Failed to open file: {e}")
            return ToolResult.fail(error=f"Failed to open file: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


# =============================================================================
# APP TOOLS
# =============================================================================

# Valid app names enum - constrains LLM to only valid options
VALID_APP_NAMES = [
    "chrome", "firefox", "edge", "notepad", "calculator", 
    "spotify", "vscode", "explorer", "cmd", "powershell",
    "task_manager", "control_panel", "settings"
]


class AppOpenTool(BaseTool):
    """Open an application by name."""
    
    name = "app.open"
    description = "Open an application by name. Common apps: chrome, notepad, calculator, vscode, spotify."
    category = "apps"
    
    # Uses enum to constrain input - prevents hallucinated app names
    parameters = {
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Name of the application to open",
                "enum": VALID_APP_NAMES,
            },
        },
        "required": ["app_name"]
    }
    required_parameters = ["app_name"]
    
    # Internal mapping from normalized names to executables
    APP_MAPPINGS = {
        "chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "edge": "msedge.exe",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "spotify": "spotify.exe",
        "vscode": "Code.exe",
        "explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "task_manager": "Taskmgr.exe",
        "control_panel": "control.exe",
        "settings": "ms-settings:",
    }
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        app_name = kwargs.get("app_name")
        if not app_name:
            return False, "app_name parameter is required"
        if app_name not in VALID_APP_NAMES:
            return False, f"Invalid app_name. Must be one of: {', '.join(VALID_APP_NAMES)}"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        app_name = kwargs["app_name"]
        executable = self.APP_MAPPINGS.get(app_name, app_name)
        
        try:
            if executable.startswith("shell:") or executable.endswith(":"):
                subprocess.Popen(["start", executable], shell=True)
            else:
                subprocess.Popen([executable])
            
            return ToolResult.ok(f"Opening {app_name}")
            
        except Exception as e:
            log.error(f"Failed to open app: {e}")
            return ToolResult.fail(error=f"Failed to open app: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.0
    
    def risk_level(self) -> str:
        return "low"


class AppCloseTool(BaseTool):
    """Close an application by name."""
    
    name = "app.close"
    description = "Close/terminate an application by name. Force closes the process."
    category = "apps"
    
    parameters = {
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Name of the application to close",
                "enum": VALID_APP_NAMES,
            },
            "force": {
                "type": "boolean",
                "description": "Force close even if unsaved changes (default: true)",
            },
        },
        "required": ["app_name"]
    }
    required_parameters = ["app_name"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        app_name = kwargs.get("app_name")
        if not app_name:
            return False, "app_name parameter is required"
        if app_name not in VALID_APP_NAMES:
            return False, f"Invalid app_name. Must be one of: {', '.join(VALID_APP_NAMES)}"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        app_name = kwargs["app_name"]
        executable = self.APP_MAPPINGS.get(app_name, app_name)
        
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/F", "/IM", executable],
                    capture_output=True,
                    text=True
                )
            else:
                subprocess.run(
                    ["pkill", "-f", executable],
                    capture_output=True,
                    text=True
                )
            
            return ToolResult.ok(f"Closed {app_name}")
            
        except Exception as e:
            log.error(f"Failed to close app: {e}")
            return ToolResult.fail(error=f"Failed to close app: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "medium"  # Can cause data loss if unsaved work


# =============================================================================
# WEB TOOLS
# =============================================================================

class WebSearchTool(BaseTool):
    """Search the web using Google."""
    
    name = "web.search"
    description = "Search the web using Google. Opens search results in the default browser."
    category = "web"
    
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string",
            },
        },
        "required": ["query"]
    }
    required_parameters = ["query"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        query = kwargs.get("query")
        if not query or not isinstance(query, str):
            return False, "query must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        import urllib.parse
        import webbrowser
        
        query = kwargs["query"]
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"https://www.google.com/search?q={encoded_query}"
        
        try:
            webbrowser.open(search_url)
            return ToolResult.ok(f"Searching for: {query}")
        except Exception as e:
            log.error(f"Web search failed: {e}")
            return ToolResult.fail(error=f"Web search failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class WebOpenURLTool(BaseTool):
    """Open a specific URL in the browser."""
    
    name = "web.open_url"
    description = "Open a specific URL in the default web browser."
    category = "web"
    
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to open (including http:// or https://)",
            },
        },
        "required": ["url"]
    }
    required_parameters = ["url"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        url = kwargs.get("url")
        if not url or not isinstance(url, str):
            return False, "url must be a non-empty string"
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "URL must start with http:// or https://"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        import webbrowser
        
        url = kwargs["url"]
        
        try:
            webbrowser.open(url)
            return ToolResult.ok(f"Opening: {url}")
        except Exception as e:
            log.error(f"Failed to open URL: {e}")
            return ToolResult.fail(error=f"Failed to open URL: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


# Export all refactored tool classes
REFACTORED_TOOLS = [
    # System
    SystemLockPCTool,
    SystemSleepPCTool,
    SystemRestartPCTool,
    # Files
    FileReadTool,
    FileWriteTool,
    FileOpenTool,
    # Apps
    AppOpenTool,
    AppCloseTool,
    # Web
    WebSearchTool,
    WebOpenURLTool,
]
