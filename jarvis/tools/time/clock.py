"""
tools/time/clock.py — Time and date tools

Tools for: get_time, get_date, set_timer, alarm, wait
Uses datetime and threading for time operations.
"""

import logging
import subprocess
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from ..base import BaseTool, ToolResult

log = logging.getLogger("time_tools")


class GetTimeTool(BaseTool):
    """Get the current time."""
    
    name = "get_time"
    description = "Get the current local time."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")  # 12-hour format with AM/PM
        return ToolResult.ok(f"Current time: {time_str}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.1
    
    def risk_level(self) -> str:
        return "low"


class GetDateTool(BaseTool):
    """Get the current date."""
    
    name = "get_date"
    description = "Get the current date including day of week."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")  # Full format
        return ToolResult.ok(f"Today is {date_str}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.1
    
    def risk_level(self) -> str:
        return "low"


class SetTimerTool(BaseTool):
    """Set a timer that will notify when complete."""
    
    name = "set_timer"
    description = "Set a countdown timer. Will notify you when time is up."
    parameters = {
        "minutes": {
            "type": "integer",
            "description": "Minutes for the timer (default: 0)",
        },
        "seconds": {
            "type": "integer",
            "description": "Additional seconds (default: 0)",
        },
        "message": {
            "type": "string",
            "description": "Optional message to display when timer ends",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        minutes = kwargs.get("minutes", 0)
        seconds = kwargs.get("seconds", 0)
        
        if not isinstance(minutes, int) or minutes < 0:
            return False, "minutes must be a non-negative integer"
        if not isinstance(seconds, int) or seconds < 0:
            return False, "seconds must be a non-negative integer"
        
        total_seconds = minutes * 60 + seconds
        if total_seconds <= 0:
            return False, "Timer duration must be greater than 0"
        if total_seconds > 3600:  # Max 1 hour
            return False, "Maximum timer duration is 1 hour"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        minutes = kwargs.get("minutes", 0)
        seconds = kwargs.get("seconds", 0)
        message = kwargs.get("message", "Timer complete!")
        
        total_seconds = minutes * 60 + seconds
        
        def timer_complete():
            try:
                # Show Windows notification
                script = f"""
                [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
                $balloon = New-Object System.Windows.Forms.NotifyIcon
                $balloon.BalloonTipTitle = 'Timer Complete'
                $balloon.BalloonTipText = '{message}'
                $balloon.Icon = [System.Drawing.SystemIcons]::Information
                $balloon.Visible = $true
                $balloon.ShowBalloonTip(5000)
                """
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True,
                    timeout=10,
                )
            except Exception as e:
                log.error(f"Timer notification failed: {e}")
        
        # Start timer in background thread
        thread = threading.Thread(target=lambda: (time.sleep(total_seconds), timer_complete()))
        thread.daemon = True
        thread.start()
        
        duration_str = f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes else ""
        if seconds:
            duration_str += f" and {seconds} second{'s' if seconds != 1 else ''}"
        
        return ToolResult.ok(f"Timer set for {duration_str}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


class WaitTool(BaseTool):
    """Wait for a specified duration before continuing."""
    
    name = "wait"
    description = "Pause execution for a specified number of seconds before continuing with other actions."
    parameters = {
        "seconds": {
            "type": "integer",
            "description": "Number of seconds to wait (1-60)",
        },
    }
    required_parameters = ["seconds"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        seconds = kwargs.get("seconds")
        if seconds is None:
            return False, "seconds parameter is required"
        if not isinstance(seconds, int) or seconds < 1 or seconds > 60:
            return False, "seconds must be between 1 and 60"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        seconds = kwargs["seconds"]
        
        try:
            time.sleep(seconds)
            return ToolResult.ok(f"Waited for {seconds} seconds")
        except Exception as e:
            log.error(f"Wait interrupted: {e}")
            return ToolResult.fail(error=f"Wait interrupted: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return float(kwargs.get("seconds", 0))
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
TIME_TOOLS = [
    GetTimeTool,
    GetDateTool,
    SetTimerTool,
    WaitTool,
]
