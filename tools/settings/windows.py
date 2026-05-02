"""
tools/settings/windows.py — Windows settings tools

Tools for: open settings, control panel, recycle bin
Uses subprocess and shell commands.
"""

import logging
import subprocess
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("settings_tools")


class OpenSettingsTool(BaseTool):
    """Open Windows Settings app."""
    
    name = "open_settings"
    description = "Open the Windows Settings app. Optionally specify a specific settings page."
    parameters = {
        "page": {
            "type": "string",
            "description": "Optional specific settings page (e.g., 'bluetooth', 'wifi', 'display', 'sound')",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        page = kwargs.get("page", "")
        
        try:
            if page:
                # Map common page names to settings URIs
                page_map = {
                    "bluetooth": "ms-settings:bluetooth",
                    "wifi": "ms-settings:network-wifi",
                    "network": "ms-settings:network-status",
                    "display": "ms-settings:display",
                    "sound": "ms-settings:sound",
                    "audio": "ms-settings:sound",
                    "volume": "ms-settings:sound",
                    "battery": "ms-settings:battery",
                    "power": "ms-settings:powersleep",
                    "storage": "ms-settings:storagesense",
                    "apps": "ms-settings:appsfeatures",
                    "update": "ms-settings:windowsupdate",
                    "privacy": "ms-settings:privacy",
                    "accounts": "ms-settings:emailandaccounts",
                    "time": "ms-settings:dateandtime",
                    "language": "ms-settings:regionlanguage",
                    "keyboard": "ms-settings:keyboard",
                    "mouse": "ms-settings:mouse",
                    "touchpad": "ms-settings:devices-touchpad",
                    "camera": "ms-settings:privacy-camera",
                    "microphone": "ms-settings:privacy-microphone",
                    "notifications": "ms-settings:notifications",
                    "theme": "ms-settings:personalization-background",
                    "background": "ms-settings:personalization-background",
                    "lockscreen": "ms-settings:lockscreen",
                    "colors": "ms-settings:colors",
                    "taskbar": "ms-settings:taskbar",
                    "start": "ms-settings:start",
                }
                
                uri = page_map.get(page.lower(), "ms-settings:")
            else:
                uri = "ms-settings:"
            
            subprocess.Popen(["start", uri], shell=True)
            
            return ToolResult.ok(f"Opening Windows Settings{' - ' + page if page else ''}")
            
        except Exception as e:
            log.error(f"Failed to open settings: {e}")
            return ToolResult.fail(error=f"Failed to open settings: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class OpenControlPanelTool(BaseTool):
    """Open Windows Control Panel."""
    
    name = "open_control_panel"
    description = "Open the classic Windows Control Panel."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            subprocess.Popen(["control"], shell=True)
            return ToolResult.ok("Opening Control Panel")
        except Exception as e:
            log.error(f"Failed to open Control Panel: {e}")
            return ToolResult.fail(error=f"Failed to open Control Panel: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class OpenRecycleBinTool(BaseTool):
    """Open the Recycle Bin."""
    
    name = "open_recycle_bin"
    description = "Open the Windows Recycle Bin to view deleted files."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            # Open Recycle Bin using its shell folder GUID
            subprocess.Popen(
                ["explorer.exe", "shell:::{645FF040-5081-101B-9F08-00AA002F954E}"],
                shell=False,
            )
            return ToolResult.ok("Opening Recycle Bin")
        except Exception as e:
            log.error(f"Failed to open Recycle Bin: {e}")
            return ToolResult.fail(error=f"Failed to open Recycle Bin: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
SETTINGS_TOOLS = [
    OpenSettingsTool,
    OpenControlPanelTool,
    OpenRecycleBinTool,
]
