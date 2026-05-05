"""
jarvis/tools/ui/actions.py — UI ACTION TOOLS

These tools perform actual UI actions (click, type, etc.).
They DO NOT use Gemma3 directly - they receive coordinates/text from planner decisions.

Separation of concerns:
- Vision tools (vision.*) = perception only (Gemma3)
- UI tools (ui.*) = actions only (deterministic)
"""

import logging
import time
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("ui_actions")


class ClickTool(BaseTool):
    """Click at specific screen coordinates."""
    
    name = "ui.click"
    description = "Click the mouse at specific x,y screen coordinates. Origin (0,0) is top-left corner."
    parameters = {
        "x": {"type": "integer", "description": "X coordinate (horizontal, from left)"},
        "y": {"type": "integer", "description": "Y coordinate (vertical, from top)"},
        "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button (default: left)"}
    }
    required_parameters = ["x", "y"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        x, y = kwargs.get("x"), kwargs.get("y")
        if x is None or y is None:
            return False, "x and y coordinates are required"
        if not isinstance(x, int) or not isinstance(y, int):
            return False, "x and y must be integers"
        if x < 0 or y < 0:
            return False, "Coordinates cannot be negative"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        x, y = kwargs["x"], kwargs["y"]
        button = kwargs.get("button", "left")
        
        try:
            import ctypes
            BUTTON_MAP = {"left": 0x0002, "right": 0x0008, "middle": 0x0020}
            down_flag = BUTTON_MAP.get(button, 0x0002)
            
            ctypes.windll.user32.SetCursorPos(x, y)
            time.sleep(0.05)
            ctypes.windll.user32.mouse_event(down_flag, 0, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.mouse_event(down_flag << 1, 0, 0, 0, 0)
            
            return ToolResult.ok(f"Clicked {button} button at ({x}, {y})")
        except Exception as e:
            log.error(f"Click failed: {e}")
            return ToolResult.fail(error=str(e))
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "medium"


class TypeTextTool(BaseTool):
    """Type text at current cursor position."""
    
    name = "ui.type_text"
    description = "Type text at the current cursor position."
    parameters = {
        "text": {"type": "string", "description": "Text to type"}
    }
    required_parameters = ["text"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        text = kwargs.get("text")
        if not text or not isinstance(text, str):
            return False, "text must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        text = kwargs["text"]
        
        try:
            import ctypes
            for char in text:
                ctypes.windll.user32.keybd_event(ord(char.upper()), 0, 0, 0)
                ctypes.windll.user32.keybd_event(ord(char.upper()), 0, 2, 0)
                time.sleep(0.02)
            
            return ToolResult.ok(f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}")
        except Exception as e:
            log.error(f"Type failed: {e}")
            return ToolResult.fail(error=str(e))
    
    def estimate_duration(self, **kwargs) -> float:
        return len(kwargs.get("text", "")) * 0.05
    
    def risk_level(self) -> str:
        return "low"


class PressKeyTool(BaseTool):
    """Press a keyboard key."""
    
    name = "ui.press_key"
    description = "Press a keyboard key (e.g., Enter, Tab, Escape)."
    parameters = {
        "key": {"type": "string", "description": "Key to press (e.g., 'enter', 'tab', 'escape')"}
    }
    required_parameters = ["key"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        key = kwargs.get("key")
        if not key or not isinstance(key, str):
            return False, "key must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        key = kwargs["key"].lower()
        
        try:
            import ctypes
            KEY_MAP = {
                "enter": 0x0D, "tab": 0x09, "escape": 0x1B,
                "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
                "space": 0x20, "backspace": 0x08, "delete": 0x2E
            }
            vk_code = KEY_MAP.get(key, ord(key[0].upper()))
            
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
            
            return ToolResult.ok(f"Pressed key: {key}")
        except Exception as e:
            log.error(f"Key press failed: {e}")
            return ToolResult.fail(error=str(e))
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.1
    
    def risk_level(self) -> str:
        return "low"


class FocusWindowTool(BaseTool):
    """Focus/activate a window by name."""
    
    name = "ui.focus_window"
    description = "Bring a window to focus by its title/name."
    parameters = {
        "name": {"type": "string", "description": "Window title or partial name to find"}
    }
    required_parameters = ["name"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        name = kwargs.get("name")
        if not name or not isinstance(name, str):
            return False, "name must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        name = kwargs["name"]
        
        try:
            import ctypes
            
            hwnd = ctypes.windll.user32.FindWindowW(None, name)
            if hwnd == 0:
                def callback(hwnd, _):
                    buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                    if name.lower() in buf.value.lower():
                        callback.found = hwnd
                        return False
                    return True
                
                callback.found = None
                ctypes.windll.user32.EnumWindows(callback, 0)
                hwnd = callback.found
            
            if hwnd:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                return ToolResult.ok(f"Focused window: {name}")
            else:
                return ToolResult.fail(error=f"Window not found: {name}")
                
        except Exception as e:
            log.error(f"Focus failed: {e}")
            return ToolResult.fail(error=str(e))
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "low"


UI_TOOLS = [ClickTool, TypeTextTool, PressKeyTool, FocusWindowTool]
