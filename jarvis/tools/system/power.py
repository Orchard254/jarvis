"""
tools/system/power.py — Power management tools

Tools for: lock, sleep, restart, shutdown
All operations use PowerShell subprocess calls.
"""

import logging
import subprocess
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("power_tools")


class LockPCTool(BaseTool):
    """Lock the computer immediately."""
    
    name = "lock_pc"
    description = "Lock the PC immediately using Windows lock screen. Safe operation that doesn't close any apps or files."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            # Use rundll32 to lock workstation
            subprocess.run(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                check=False,  # Don't raise, just check return
            )
            return ToolResult.ok("PC locked successfully")
        except Exception as e:
            log.error(f"Failed to lock PC: {e}")
            return ToolResult.fail(error=f"Failed to lock PC: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class SleepPCTool(BaseTool):
    """Put the computer to sleep."""
    
    name = "sleep_pc"
    description = "Put the PC to sleep. All open apps and files will be preserved in memory. The PC can be woken by pressing a key or moving the mouse."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            # Use PowerShell to put system to sleep
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


class RestartPCTool(BaseTool):
    """Restart the computer (requires confirmation)."""
    
    name = "restart_pc"
    description = "Restart the PC. WARNING: This will close all applications. Unsaved work may be lost. Should only be called after explicit user confirmation."
    parameters = {
        "force": {
            "type": "boolean",
            "description": "Force restart without waiting for apps to close (default: false)",
        },
        "delay_seconds": {
            "type": "integer",
            "description": "Delay before restart in seconds (default: 0, max: 60)",
        },
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
        return "high"  # Can cause data loss if unsaved work exists


class ShutdownPCTool(BaseTool):
    """Shutdown the computer (requires confirmation)."""
    
    name = "shutdown_pc"
    description = "Shutdown the PC completely. WARNING: This will close all applications. Unsaved work may be lost. Should only be called after explicit user confirmation."
    parameters = {
        "force": {
            "type": "boolean",
            "description": "Force shutdown without waiting for apps to close (default: false)",
        },
        "delay_seconds": {
            "type": "integer",
            "description": "Delay before shutdown in seconds (default: 0, max: 60)",
        },
        "hibernate": {
            "type": "boolean",
            "description": "Hibernate instead of full shutdown (default: false)",
        },
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
        hibernate = kwargs.get("hibernate", False)
        
        try:
            if hibernate:
                # Hibernate uses different command
                script = """
                shutdown /h /t """ + str(delay)
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            else:
                flags = "/s /t " + str(delay)
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
                    return ToolResult.ok(f"Shutdown scheduled in {delay} seconds")
                else:
                    return ToolResult.ok("Shutting down now")
            else:
                return ToolResult.fail(error=f"Shutdown failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error="Shutdown command timed out")
        except Exception as e:
            log.error(f"Failed to shutdown PC: {e}")
            return ToolResult.fail(error=f"Failed to shutdown PC: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        delay = kwargs.get("delay_seconds", 0)
        return float(delay) + 2.0
    
    def risk_level(self) -> str:
        return "critical"  # Highest risk - causes complete system shutdown


# Export all tool classes
POWER_TOOLS = [
    LockPCTool,
    SleepPCTool,
    RestartPCTool,
    ShutdownPCTool,
]
