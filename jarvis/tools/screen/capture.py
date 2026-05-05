"""
tools/screen/capture.py — Screen capture tools

Tools for: screenshot, realtime capture
Uses mss and Pillow for screen capture.
Returns base64 encoded image data in result dict under image_base64 key.
"""

import base64
import io
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..base import BaseTool, ToolResult

log = logging.getLogger("screen_tools")


# Screenshot directory
SCREENSHOT_DIR = Path(__file__).parent.parent.parent.parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


def take_screenshot(filename: Optional[str] = None) -> tuple[bool, str, Optional[str]]:
    """
    Take a screenshot and save it.
    
    Args:
        filename: Optional custom filename (without extension)
        
    Returns:
        Tuple of (success, message, base64_data)
    """
    try:
        import mss
        from PIL import Image
        
        # Generate filename
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}"
        
        filepath = SCREENSHOT_DIR / f"{filename}.png"
        
        # Capture screen
        with mss.mss() as sct:
            # Capture primary monitor
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            # Save to disk
            img.save(filepath, "PNG")
            
            # Also get base64 for vision analysis
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            
            return True, f"Screenshot saved to {filepath}", base64_data
            
    except ImportError:
        return False, "Screenshot library not installed (mss, Pillow)", None
    except Exception as e:
        log.error(f"Screenshot failed: {e}")
        return False, f"Screenshot failed: {e}", None


class ScreenshotTool(BaseTool):
    """Take a screenshot of the current screen and save it."""
    
    name = "screenshot"
    description = "Take a screenshot of the current screen. The image is saved to the screenshots folder."
    parameters = {
        "filename": {
            "type": "string",
            "description": "Optional filename (without extension). If not provided, auto-generated timestamp is used.",
            "default": None
        }
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        filename = kwargs.get("filename")
        if filename and not isinstance(filename, str):
            return False, "filename must be a string"
        if filename and any(c in filename for c in '<>:"/\\|?*'):
            return False, "filename contains invalid characters"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        filename = kwargs.get("filename")
        
        # Generate proper filename if provided
        if filename:
            # Ensure no extension is added twice
            base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
            full_filename = f"{base_name}.png"
            success, message, base64_data = take_screenshot(filename=full_filename)
        else:
            success, message, base64_data = take_screenshot()
        
        if success:
            result = ToolResult.ok(message)
            result.output = message
            return result
        else:
            return ToolResult.fail(error=message)
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class AnalyzeScreenTool(BaseTool):
    """Analyze the current screen content using vision LLM."""
    
    name = "analyze_screen"
    description = "Take a screenshot and analyze its contents using AI vision. Returns a structured description of what's visible including open windows, text, UI elements, and any errors shown."
    parameters = {
        "focus": {
            "type": "string",
            "description": "Optional focus area: 'windows', 'text', 'errors', 'all' (default: all)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        focus = kwargs.get("focus", "all")
        if focus not in ["windows", "text", "errors", "all"]:
            return False, "focus must be one of: windows, text, errors, all"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        focus = kwargs.get("focus", "all")
        
        # Take screenshot first
        success, message, base64_data = take_screenshot()
        
        if not success or not base64_data:
            return ToolResult.fail(error=f"Failed to capture screen: {message}")
        
        try:
            # Import vision module for analysis
            from ...perception.vision import get_vision_analyzer
            
            # Get vision analyzer instance
            vision = get_vision_analyzer()
            
            # Analyze screen - returns dict with screen_state object
            analysis = vision.analyze_screen(screenshot_base64=base64_data)
            
            if analysis['success'] and analysis.get('screen_state'):
                screen_state = analysis['screen_state']
                # Return formatted string suitable for LLM reading
                formatted_output = screen_state.to_formatted_string()
                return ToolResult.ok(f"Screen Analysis:\n{formatted_output}")
            else:
                return ToolResult.fail(error="Vision analysis returned no results")
                
        except ImportError as e:
            return ToolResult.fail(error=f"Vision module not available: {e}")
        except Exception as e:
            log.error(f"Screen analysis failed: {e}")
            return ToolResult.fail(error=f"Screen analysis failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 5.0  # Includes LLM call
    
    def risk_level(self) -> str:
        return "low"


class ClickAtTool(BaseTool):
    """Click at specific screen coordinates."""
    
    name = "click_at"
    description = "Click the mouse at specific x,y screen coordinates. Origin (0,0) is top-left corner."
    parameters = {
        "x": {
            "type": "integer",
            "description": "X coordinate (horizontal, from left)",
        },
        "y": {
            "type": "integer",
            "description": "Y coordinate (vertical, from top)",
        },
        "button": {
            "type": "string",
            "enum": ["left", "right", "middle"],
            "description": "Mouse button to click (default: left)",
        },
    }
    required_parameters = ["x", "y"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        x = kwargs.get("x")
        y = kwargs.get("y")
        
        if x is None or y is None:
            return False, "x and y coordinates are required"
        
        if not isinstance(x, int) or not isinstance(y, int):
            return False, "x and y must be integers"
        
        if x < 0 or y < 0:
            return False, "Coordinates cannot be negative"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        x = kwargs["x"]
        y = kwargs["y"]
        button = kwargs.get("button", "left")
        
        try:
            import ctypes
            
            # Map button to constants
            BUTTON_MAP = {
                "left": 0x0002,  # MOUSEEVENTF_LEFTDOWN/UP
                "right": 0x0008,  # MOUSEEVENTF_RIGHTDOWN/UP
                "middle": 0x0020,  # MOUSEEVENTF_MIDDLEDOWN/UP
            }
            
            down_flag = BUTTON_MAP.get(button, 0x0002)
            up_flag = down_flag << 1  # UP flag is always DOWN * 2
            
            # Move mouse to position
            ctypes.windll.user32.SetCursorPos(x, y)
            
            # Small delay
            time.sleep(0.05)
            
            # Click
            ctypes.windll.user32.mouse_event(down_flag, 0, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.mouse_event(up_flag, 0, 0, 0, 0)
            
            return ToolResult.ok(f"Clicked {button} button at ({x}, {y})")
            
        except Exception as e:
            log.error(f"Click failed: {e}")
            return ToolResult.fail(error=f"Click failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "medium"  # Can trigger unintended actions


class FindOnScreenTool(BaseTool):
    """Find an element on screen using vision."""
    
    name = "find_on_screen"
    description = "Find a specific element on screen by description. Uses AI vision to locate buttons, text, icons, or UI elements and returns their coordinates."
    parameters = {
        "description": {
            "type": "string",
            "description": "Description of what to find (e.g., 'the close button', 'Save icon', 'Submit text')",
        },
    }
    required_parameters = ["description"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        description = kwargs.get("description")
        if not description:
            return False, "description is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        description = kwargs["description"]
        
        # Take screenshot
        success, message, base64_data = take_screenshot()
        
        if not success or not base64_data:
            return ToolResult.fail(error=f"Failed to capture screen: {message}")
        
        try:
            from ...perception.vision import get_vision_analyzer
            
            vision = get_vision_analyzer()
            
            # Find element on screen - returns coordinates dict
            result = vision.find_on_screen(description, screenshot_base64=base64_data)
            
            if result.get('success') and result.get('found'):
                coords = result['coordinates']
                x = coords.get('x')
                y = coords.get('y')
                confidence = result.get('confidence', 0.5)
                return ToolResult.ok(f"Found '{description}' at coordinates ({x}, {y}) with {confidence:.0%} confidence")
            else:
                error_msg = result.get('error', f"Could not find '{description}' on screen")
                return ToolResult.fail(error=error_msg)
                
        except ImportError as e:
            return ToolResult.fail(error=f"Vision module not available: {e}")
        except Exception as e:
            log.error(f"Find on screen failed: {e}")
            return ToolResult.fail(error=f"Find on screen failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 5.0  # Includes LLM call
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
SCREEN_TOOLS = [
    ScreenshotTool,
    AnalyzeScreenTool,
    ClickAtTool,
    FindOnScreenTool,
]
