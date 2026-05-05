"""
tools/scripts/runner.py — Script execution tools

Tools for: run_powershell, run_command, run_python
Executes scripts and commands safely with output capture.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from ..base import BaseTool, ToolResult

log = logging.getLogger("script_tools")


class RunPowerShellTool(BaseTool):
    """Run a PowerShell command or script."""
    
    name = "run_powershell"
    description = "Execute a PowerShell command or script. Returns stdout/stderr output."
    parameters = {
        "command": {
            "type": "string",
            "description": "PowerShell command to execute",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default: 30, max: 120)",
        },
    }
    required_parameters = ["command"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        command = kwargs.get("command")
        if not command:
            return False, "command parameter is required"
        
        timeout = kwargs.get("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 120:
            return False, "timeout must be between 1 and 120 seconds"
        
        # Safety check - block dangerous commands
        dangerous_patterns = [
            "remove-item -recurse",
            "format-volume",
            "clear-disk",
            "stop-computer",
            "restart-computer",
        ]
        
        cmd_lower = command.lower()
        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                return False, f"Dangerous command blocked: {pattern}"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        command = kwargs["command"]
        timeout = min(kwargs.get("timeout", 30), 120)
        
        # Check if the script contains Stop-Process and route to _close_app_gracefully
        if "Stop-Process" in command:
            return self._close_app_gracefully(command)
        
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            if result.returncode == 0:
                return ToolResult.ok(output[:5000] if output else "Command executed successfully")
            else:
                return ToolResult.fail(error=error[:1000] if error else f"Exit code: {result.returncode}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error=f"Command timed out after {timeout} seconds")
        except Exception as e:
            log.error(f"PowerShell execution failed: {e}")
            return ToolResult.fail(error=f"PowerShell execution failed: {e}")
    
    def _close_app_gracefully(self, command: str) -> ToolResult:
        """
        Handle Stop-Process commands by routing to graceful app close.
        
        Parses the Stop-Process command to extract the process name or ID
        and closes the app gracefully.
        """
        import re
        
        # Try to extract process name from Stop-Process -Name <name>
        name_match = re.search(r'Stop-Process\s+-Name\s+[\'"]?(\w+)[\'"]?', command, re.IGNORECASE)
        # Or from Stop-Process <name>
        if not name_match:
            name_match = re.search(r'Stop-Process\s+(\w+)', command, re.IGNORECASE)
        
        # Try to extract process ID from Stop-Process -Id <id>
        id_match = re.search(r'Stop-Process\s+-Id\s+(\d+)', command, re.IGNORECASE)
        
        try:
            if name_match:
                app_name = name_match.group(1).lower()
                # Import and use CloseAppTool
                from ..apps.launcher import CloseAppTool
                close_tool = CloseAppTool()
                return close_tool.execute(app_name=app_name, force=False)
            elif id_match:
                pid = int(id_match.group(1))
                # Kill by PID using psutil
                import psutil
                try:
                    proc = psutil.Process(pid)
                    proc.terminate()  # Graceful termination
                    return ToolResult.ok(f"Gracefully terminated process {pid} ({proc.name()})")
                except psutil.NoSuchProcess:
                    return ToolResult.ok(f"Process {pid} was not running")
                except psutil.AccessDenied:
                    return ToolResult.fail(error=f"Access denied to terminate process {pid}")
            else:
                # Can't parse the command, execute it anyway but warn
                log.warning(f"Could not parse Stop-Process command: {command}")
                return self._execute_powershell(command, 30)
        except Exception as e:
            log.error(f"Failed to close app gracefully: {e}")
            return ToolResult.fail(error=f"Failed to close app gracefully: {e}")
    
    def _execute_powershell(self, command: str, timeout: int) -> ToolResult:
        """Execute PowerShell command directly."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            if result.returncode == 0:
                return ToolResult.ok(output[:5000] if output else "Command executed successfully")
            else:
                return ToolResult.fail(error=error[:1000] if error else f"Exit code: {result.returncode}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error=f"Command timed out after {timeout} seconds")
        except Exception as e:
            log.error(f"PowerShell execution failed: {e}")
            return ToolResult.fail(error=f"PowerShell execution failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return min(kwargs.get("timeout", 30), 30) * 0.5
    
    def risk_level(self) -> str:
        return "medium"


class RunCommandTool(BaseTool):
    """Run a Windows command prompt command."""
    
    name = "run_command"
    description = "Execute a Windows command prompt (cmd.exe) command. Returns stdout/stderr output."
    parameters = {
        "command": {
            "type": "string",
            "description": "Command to execute in cmd.exe",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default: 30, max: 120)",
        },
    }
    required_parameters = ["command"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        command = kwargs.get("command")
        if not command:
            return False, "command parameter is required"
        
        timeout = kwargs.get("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 120:
            return False, "timeout must be between 1 and 120 seconds"
        
        # Safety check
        dangerous_patterns = [
            "format ",
            "del /s /q",
            "rd /s /q",
            "shutdown /s",
            "shutdown /r",
        ]
        
        cmd_lower = command.lower()
        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                return False, f"Dangerous command blocked: {pattern}"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        command = kwargs["command"]
        timeout = min(kwargs.get("timeout", 30), 120)
        
        try:
            result = subprocess.run(
                ["cmd", "/c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            if result.returncode == 0:
                return ToolResult.ok(output[:5000] if output else "Command executed successfully")
            else:
                return ToolResult.fail(error=error[:1000] if error else f"Exit code: {result.returncode}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error=f"Command timed out after {timeout} seconds")
        except Exception as e:
            log.error(f"Command execution failed: {e}")
            return ToolResult.fail(error=f"Command execution failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return min(kwargs.get("timeout", 30), 30) * 0.5
    
    def risk_level(self) -> str:
        return "medium"


class RunPythonTool(BaseTool):
    """Run a Python script string."""
    
    name = "run_python"
    description = "Execute a Python code string in a subprocess. Returns stdout/stderr output."
    parameters = {
        "code": {
            "type": "string",
            "description": "Python code to execute",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default: 30, max: 120)",
        },
    }
    required_parameters = ["code"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        code = kwargs.get("code")
        if not code:
            return False, "code parameter is required"
        
        timeout = kwargs.get("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 120:
            return False, "timeout must be between 1 and 120 seconds"
        
        # Safety check - block only truly destructive operations
        # subprocess isolation already provides safety boundary
        actually_dangerous = [
            "shutil.rmtree('C:\\\\Windows')",
            "shutil.rmtree('C:\\\\Program Files')", 
            "os.remove('C:\\\\Windows')",
            "format c:",
            "rd /s /q c:\\\\",
            "__import__('os').system('format",
        ]
        
        for pattern in actually_dangerous:
            if pattern in code:
                return False, f"Dangerous code pattern blocked: {pattern}"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        code = kwargs["code"]
        timeout = min(kwargs.get("timeout", 30), 120)
        
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            if result.returncode == 0:
                return ToolResult.ok(output[:5000] if output else "Python code executed successfully")
            else:
                return ToolResult.fail(error=error[:1000] if error else f"Exit code: {result.returncode}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error=f"Python execution timed out after {timeout} seconds")
        except Exception as e:
            log.error(f"Python execution failed: {e}")
            return ToolResult.fail(error=f"Python execution failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return min(kwargs.get("timeout", 30), 30) * 0.5
    
    def risk_level(self) -> str:
        return "medium"


# Export all tool classes
SCRIPT_TOOLS = [
    RunPowerShellTool,
    RunCommandTool,
    RunPythonTool,
]
