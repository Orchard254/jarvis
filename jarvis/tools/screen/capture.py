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


# Import window functions for auto-focus feature
def find_window_by_title(title: str):
    """Import from window module lazily to avoid circular imports."""
    from ..apps.window import find_window_by_title as f
    return f(title)


def bring_to_foreground(hwnd: int) -> bool:
    """Import from window module lazily to avoid circular imports."""
    from ..apps.window import bring_to_foreground as b
    return b(hwnd)


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
            
            # Build prompt based on focus area
            prompts = {
                "windows": "List all open application windows and their titles.",
                "text": "Read all visible text on the screen.",
                "errors": "Identify any error messages, warnings, or notifications.",
                "all": "Describe everything you see on this screen in detail."
            }
            prompt = prompts.get(focus, prompts["all"])
            
            # Analyze screen with specific prompt
            analysis = vision.analyze_screen(
                screenshot_base64=base64_data,
                prompt=prompt
            )
            
            if analysis['success'] and analysis.get('screen_state'):
                screen_state = analysis['screen_state']
                # Return formatted string suitable for LLM reading
                formatted_output = screen_state.to_formatted_string()
                return ToolResult.ok(f"Screen Analysis:\n{formatted_output}")
            elif not analysis.get('success') and analysis.get('error') == 'No Ollama client configured':
                return ToolResult.fail(error="Vision analyzer not initialized. Please restart JARVIS.")
            else:
                error_msg = analysis.get('error', "Vision analysis returned no results")
                return ToolResult.fail(error=error_msg)
                
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
    """Click at specific screen coordinates.
    
    ⚠️  LOW-LEVEL TOOL - USE AS LAST RESORT
    
    This tool clicks at exact pixel coordinates. It should ONLY be used:
    1. AFTER find_on_screen returns coordinates with HIGH confidence (≥80%)
    2. When NO specialized tool exists for your task
    3. For custom UI elements, games, or non-standard applications
    
    ❌ DO NOT USE for these common tasks (use specialized tools instead):
    - Closing windows → Use close_window(title="...")
    - Closing browser tabs → Use close_tab(query="...")
    - Minimizing windows → Use minimize_window(title="...")
    - Clicking web buttons → Use click_element(selector="...")
    
    Why avoid coordinate clicking?
    - Coordinates may change if windows move
    - Vision might identify wrong element (e.g., Chrome's close button instead of Notepad's)
    - No built-in verification that you're clicking the right target
    
    ✅ BETTER APPROACH for standard operations:
    "close notepad" → close_window(title="Notepad") [100% reliable]
    "close grok tab" → close_tab(query="grok.com") [DOM-level precision]
    "minimize chrome" → minimize_window(title="Chrome") [Windows API]
    """
    
    name = "click_at"
    description = "⚠️ LOW-LEVEL: Click mouse at x,y coordinates. ONLY use after find_on_screen with high confidence. PREFER: close_window for apps, close_tab for browser tabs, minimize_window for minimizing, click_element for web. Origin (0,0) is top-left."
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
    """Find an element on screen using vision.
    
    CRITICAL FOR ACCURACY: This tool uses Gemma4 vision to locate UI elements.
    When searching for window controls (close/minimize/maximize buttons), the vision
    model will identify ALL matching buttons and return coordinates for the MOST LIKELY match.
    
    IMPORTANT TIPS FOR BETTER ACCURACY:
    - Be specific in descriptions: "the red X close button on Notepad window" is better than "close button"
    - Include window context: Mention which window the element belongs to
    - For window controls, consider using close_window or minimize_window tools instead - they're more reliable
    
    Use cases:
    - Finding where a button is located before clicking it
    - Locating UI elements for automation scripts
    - Debugging UI layout
    
    For closing windows, use close_window instead (more reliable).
    For closing browser tabs, use close_tab instead (more reliable).
    For minimizing windows, use minimize_window instead (more reliable).
    """
    
    name = "find_on_screen"
    description = "Find a specific element on screen by description using AI vision. Returns coordinates (x,y). BE SPECIFIC: include window name and element details (e.g., 'close button on Notepad window'). For closing/minimizing, prefer close_window/minimize_window tools instead."
    parameters = {
        "description": {
            "type": "string",
            "description": "Detailed description of what to find. Include window context! Examples: 'the red X close button on the Notepad window', 'minimize button on Chrome title bar', 'Save icon in top toolbar'",
        },
        "window_context": {
            "type": "string",
            "description": "Optional: Name of the window where the element is expected (helps vision focus). E.g., 'Notepad', 'Chrome', 'File Explorer'",
            "default": None
        }
    }
    required_parameters = ["description"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        description = kwargs.get("description")
        if not description:
            return False, "description is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        description = kwargs["description"]
        window_context = kwargs.get("window_context")
        
        # Enhance description with window context if provided
        if window_context:
            enhanced_description = f"{description} in the {window_context} window"
        else:
            enhanced_description = description
        
        # CRITICAL FIX: Auto-focus the target window before taking screenshot
        # This ensures the vision model sees the correct window's elements
        if window_context:
            hwnd = find_window_by_title(window_context)
            if hwnd:
                bring_to_foreground(hwnd)
                time.sleep(0.3)  # Wait for window animation to complete
                log.info(f"Focused window '{window_context}' before searching for '{description}'")
            else:
                log.warning(f"Could not find window '{window_context}' to focus - vision may see wrong window")
        
        # Take screenshot
        success, message, base64_data = take_screenshot()
        
        if not success or not base64_data:
            return ToolResult.fail(error=f"Failed to capture screen: {message}")
        
        try:
            from ...perception.vision import get_vision_analyzer
            
            vision = get_vision_analyzer()
            
            # Find element on screen - returns coordinates dict
            # Use enhanced description for better accuracy
            result = vision.find_on_screen(enhanced_description, screenshot_base64=base64_data)
            
            if result.get('success') and result.get('found'):
                coords = result['coordinates']
                x = coords.get('x')
                y = coords.get('y')
                confidence = result.get('confidence', 0.5)
                
                # Add warning if confidence is low
                if confidence < 0.7:
                    log.warning(f"Low confidence ({confidence:.0%}) for finding '{description}'. Coordinates may be inaccurate.")
                
                return ToolResult.ok(f"Found '{description}' at coordinates ({x}, {y}) with {confidence:.0%} confidence")
            elif not result.get('success') and result.get('error') == 'No Ollama client configured':
                return ToolResult.fail(error="Vision analyzer not initialized. Please restart JARVIS.")
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
