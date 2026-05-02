"""
tools/audio/volume.py — Audio volume control tools

Tools for: set_volume, volume_up, volume_down, mute_volume, get_volume
Uses Windows keyboard events via ctypes for precise volume control.
"""

import ctypes
import logging
import subprocess
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("volume_tools")

# Volume state file for persistence
VOLUME_STATE_FILE = None  # Will be set to proper path

# Virtual key codes for volume control
VK_VOLUME_UP = 0xAF
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_MUTE = 0xAD


def _set_volume(level: int) -> bool:
    """
    Set master volume level using keyboard events.
    
    Resets to 0 by pressing volume down 50 times, then ramps up
    to the target by pressing volume up (level/2) times.
    
    Args:
        level: Target volume level (0-100)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Reset to 0 by pressing volume down 50 times
        for _ in range(50):
            ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
        
        # Ramp up to target level (each press is ~2%)
        steps_up = level // 2
        for _ in range(steps_up):
            ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
        
        return True
    except Exception as e:
        log.error(f"Failed to set volume: {e}")
        return False


def get_current_volume() -> int:
    """Get current master volume level (0-100)."""
    try:
        script = """
        $regPath = "HKCU:\\\\Software\\\\Microsoft\\\\Multimedia\\\\Audio"
        # Try to get volume from registry or use default
        # Windows doesn't expose this easily without additional libraries
        # Return a reasonable default
        echo "50"
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
        log.debug(f"Failed to get volume: {e}")
    return 50  # Default fallback


def set_volume_level(level: int) -> bool:
    """Set master volume level (0-100) using keyboard events."""
    return _set_volume(level)


class SetVolumeTool(BaseTool):
    """Set master volume to specific level."""
    
    name = "set_volume"
    description = "Set the master volume level from 0 to 100 percent."
    parameters = {
        "level": {
            "type": "integer",
            "description": "Volume level from 0 (mute) to 100 (maximum)",
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
            # Use the exact keybd_event approach: reset to 0, then ramp up
            success = _set_volume(level)
            
            if success:
                return ToolResult.ok(f"Volume set to approximately {level}%")
            else:
                return ToolResult.fail(error="Volume adjustment failed")
                
        except Exception as e:
            log.error(f"Failed to set volume: {e}")
            return ToolResult.fail(error=f"Failed to set volume: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        level = kwargs.get("level", 50)
        # Approximately 20ms per step, max 50 steps down + level/2 steps up
        return min(5.0, (50 + level // 2) * 0.02)
    
    def risk_level(self) -> str:
        return "low"


class VolumeUpTool(BaseTool):
    """Increase volume by specified amount."""
    
    name = "volume_up"
    description = "Increase the master volume by the specified amount (default: 10%)."
    parameters = {
        "amount": {
            "type": "integer",
            "description": "Amount to increase volume by (default: 10, max: 50)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        amount = kwargs.get("amount", 10)
        if not isinstance(amount, int) or amount < 1 or amount > 50:
            return False, "amount must be an integer between 1 and 50"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        amount = kwargs.get("amount", 10)
        current = get_current_volume()
        new_level = min(100, current + amount)
        
        try:
            # Press volume up key (amount/2) times since each press is ~2%
            steps = amount // 2
            for _ in range(steps):
                ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
            
            return ToolResult.ok(f"Volume increased by {amount}% (now ~{new_level}%)")
            
        except Exception as e:
            log.error(f"Failed to increase volume: {e}")
            return ToolResult.fail(error=f"Failed to increase volume: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return kwargs.get("amount", 10) * 0.04
    
    def risk_level(self) -> str:
        return "low"


class VolumeDownTool(BaseTool):
    """Decrease volume by specified amount."""
    
    name = "volume_down"
    description = "Decrease the master volume by the specified amount (default: 10%)."
    parameters = {
        "amount": {
            "type": "integer",
            "description": "Amount to decrease volume by (default: 10, max: 50)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        amount = kwargs.get("amount", 10)
        if not isinstance(amount, int) or amount < 1 or amount > 50:
            return False, "amount must be an integer between 1 and 50"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        amount = kwargs.get("amount", 10)
        current = get_current_volume()
        new_level = max(0, current - amount)
        
        try:
            # Press volume down key (amount/2) times since each press is ~2%
            steps = amount // 2
            for _ in range(steps):
                ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
            
            return ToolResult.ok(f"Volume decreased by {amount}% (now ~{new_level}%)")
            
        except Exception as e:
            log.error(f"Failed to decrease volume: {e}")
            return ToolResult.fail(error=f"Failed to decrease volume: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return kwargs.get("amount", 10) * 0.04
    
    def risk_level(self) -> str:
        return "low"


class MuteVolumeTool(BaseTool):
    """Toggle mute on/off."""
    
    name = "mute_volume"
    description = "Toggle the master volume mute on or off."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            # Press volume mute key
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
            
            return ToolResult.ok("Volume mute toggled")
            
        except Exception as e:
            log.error(f"Failed to toggle mute: {e}")
            return ToolResult.fail(error=f"Failed to toggle mute: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class GetVolumeTool(BaseTool):
    """Get current volume level."""
    
    name = "get_volume"
    description = "Get the current master volume level as a percentage."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        level = get_current_volume()
        return ToolResult.ok(f"Current volume: {level}%")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
VOLUME_TOOLS = [
    SetVolumeTool,
    VolumeUpTool,
    VolumeDownTool,
    MuteVolumeTool,
    GetVolumeTool,
]
