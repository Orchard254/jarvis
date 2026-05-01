"""
tools/system/display.py — Display settings tools

Tools for: brightness, dark mode toggle
Uses PowerShell and ctypes for display control.
"""

import logging
import subprocess
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("display_tools")


def get_current_brightness() -> int:
    """Get current brightness level using WMI."""
    try:
        script = """
        Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness | 
        Select-Object -ExpandProperty CurrentBrightness
        """
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except Exception as e:
        log.debug(f"Failed to get brightness: {e}")
    return -1  # Unknown


class SetBrightnessTool(BaseTool):
    """Set screen brightness level."""
    
    name = "set_brightness"
    description = "Set the screen brightness level from 0 to 100 percent."
    parameters = {
        "level": {
            "type": "integer",
            "description": "Brightness level from 0 to 100",
        },
    }
    required_parameters = ["level"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        level = kwargs.get("level")
        if level is None:
            return False, "level parameter is required"
        if not isinstance(level, int) or level < 0 or level > 100:
            return False, "level must be an integer between 0 and 100"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        level = kwargs["level"]
        
        try:
            # Use WMI to set brightness
            script = f"""
            $brightness = {level}
            $wmi = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods
            $wmi.WmiSetBrightness(0, $brightness)
            """
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                return ToolResult.ok(f"Brightness set to {level}%")
            else:
                return ToolResult.fail(error=f"Failed to set brightness: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error="Brightness command timed out")
        except Exception as e:
            log.error(f"Failed to set brightness: {e}")
            return ToolResult.fail(error=f"Failed to set brightness: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class ToggleDarkModeTool(BaseTool):
    """Toggle Windows dark/light mode."""
    
    name = "toggle_dark_mode"
    description = "Toggle between Windows dark mode and light mode. Affects taskbar, start menu, and system apps."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            # First, get current mode
            get_script = """
            $regPath = "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
            $appsUseLight = Get-ItemProperty -Path $regPath -Name AppsUseLightTheme -ErrorAction SilentlyContinue
            $systemUseLight = Get-ItemProperty -Path $regPath -Name SystemUsesLightTheme -ErrorAction SilentlyContinue
            
            if ($appsUseLight.AppsUseLightTheme -eq 1) {
                "light"
            } else {
                "dark"
            }
            """
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", get_script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            current_mode = result.stdout.strip().lower() if result.returncode == 0 else "unknown"
            
            # Determine new mode
            new_mode = "dark" if current_mode == "light" else "light"
            new_value = 0 if new_mode == "dark" else 1
            
            # Set new mode
            set_script = f"""
            $regPath = "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
            Set-ItemProperty -Path $regPath -Name AppsUseLightTheme -Value {new_value}
            Set-ItemProperty -Path $regPath -Name SystemUsesLightTheme -Value {new_value}
            
            # Refresh explorer to apply changes
            Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
            """
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", set_script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                return ToolResult.ok(f"Switched to {new_mode} mode")
            else:
                return ToolResult.fail(error=f"Failed to toggle dark mode: {result.stderr}")
                
        except Exception as e:
            log.error(f"Failed to toggle dark mode: {e}")
            return ToolResult.fail(error=f"Failed to toggle dark mode: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.0  # Explorer restart takes a moment
    
    def risk_level(self) -> str:
        return "medium"  # Restarts explorer which can be disruptive


# Export all tool classes
DISPLAY_TOOLS = [
    SetBrightnessTool,
    ToggleDarkModeTool,
]
