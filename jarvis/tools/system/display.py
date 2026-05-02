"""
tools/system/display.py — Display settings tools

Tools for: brightness, dark mode toggle
Uses PowerShell and ctypes for display control.
Attempts WMI first and falls back to PowerShell WmiSetBrightness method.
Honest failure reporting if both methods fail.
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
        
        # Method 1: Try WMI direct approach first
        wmi_success = False
        wmi_error = None
        
        try:
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
            
            if result.returncode == 0 and not result.stderr.strip():
                wmi_success = True
            else:
                wmi_error = result.stderr.strip() or result.stdout.strip()
                
        except subprocess.TimeoutExpired:
            wmi_error = "WMI command timed out"
        except Exception as e:
            wmi_error = str(e)
        
        if wmi_success:
            # Verify the brightness was actually set
            actual = get_current_brightness()
            if actual == level or (actual != -1 and abs(actual - level) <= 5):
                return ToolResult.ok(f"Brightness set to {level}%")
            else:
                # WMI reported success but verification failed - be honest
                return ToolResult.fail(error=f"WMI reported success but brightness is {actual}%, not {level}%")
        
        # Method 2: Fallback to alternative PowerShell WmiSetBrightness method
        ps_success = False
        ps_error = None
        
        try:
            # Alternative approach using different WMI invocation
            script = f"""
            try {{
                $wmi = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods
                Invoke-CimMethod -InputObject $wmi -MethodName WmiSetBrightness -Arguments @{{Timeout = 0; CurrentBrightness = {level}}}
                "SUCCESS"
            }} catch {{
                "ERROR: " + $_.Exception.Message
            }}
            """
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0 and "SUCCESS" in result.stdout:
                ps_success = True
            else:
                ps_error = result.stderr.strip() or result.stdout.strip()
                
        except subprocess.TimeoutExpired:
            ps_error = "PowerShell fallback command timed out"
        except Exception as e:
            ps_error = str(e)
        
        if ps_success:
            actual = get_current_brightness()
            if actual == level or (actual != -1 and abs(actual - level) <= 5):
                return ToolResult.ok(f"Brightness set to {level}% (via fallback method)")
            else:
                return ToolResult.fail(error=f"Fallback reported success but brightness is {actual}%, not {level}%")
        
        # Both methods failed - honestly report failure
        error_msg = f"Failed to set brightness to {level}%. "
        error_msg += f"WMI method failed: {wmi_error}. "
        error_msg += f"PowerShell fallback failed: {ps_error}."
        
        log.error(error_msg)
        return ToolResult.fail(error=error_msg)
    
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
