"""
jarvis/tools/vision/tools.py — STRICTLY LIMITED VISION TOOLS

These are the ONLY tools that can invoke Gemma3 for perception.
All vision calls go through vision_call() gateway.

Allowed tools:
1. screen.capture - Take a screenshot
2. vision.detect_elements - Find UI elements on screen
3. vision.read_text - Extract text from screen  
4. vision.describe_scene - Get scene summary
"""

import base64
import io
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime

from ..base import BaseTool, ToolResult
from ...perception.vision import vision_call

log = logging.getLogger("vision_tools")

# Try to import mss and PIL for screen capture
try:
    import mss
    from PIL import Image
    SCREEN_CAPTURE_AVAILABLE = True
except ImportError:
    SCREEN_CAPTURE_AVAILABLE = False
    log.warning("Screen capture libraries (mss, Pillow) not available")


def _capture_screen_base64() -> tuple[bool, str, Optional[str]]:
    """Capture screen and return base64."""
    if not SCREEN_CAPTURE_AVAILABLE:
        return False, "Screen capture libraries not installed", None
    
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)
            
            img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
            
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            base64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return True, "Screenshot captured", base64_data
    except Exception as e:
        log.error(f"Screen capture failed: {e}")
        return False, f"Capture failed: {e}", None


class ScreenCaptureTool(BaseTool):
    """
    Capture the current screen.
    
    This is the ONLY tool allowed to capture screenshots.
    Returns base64 image data for use with other vision tools.
    """
    
    name = "screen.capture"
    description = "Capture the current screen. Returns base64-encoded image data."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        success, message, base64_data = _capture_screen_base64()
        
        if success:
            result = ToolResult.ok(message)
            result.output = {"image_base64": base64_data}
            return result
        else:
            return ToolResult.fail(error=message)
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.5
    
    def risk_level(self) -> str:
        return "low"


class VisionDetectElementsTool(BaseTool):
    """
    Detect UI elements on screen matching a query.
    
    Uses Gemma3 perception module via vision_call gateway.
    Returns structured list of detected elements with coordinates.
    """
    
    name = "vision.detect_elements"
    description = "Detect UI elements on screen matching a query. Returns list of elements with labels, coordinates, and confidence scores."
    parameters = {
        "query": {
            "type": "string",
            "description": "Description of elements to find (e.g., 'login button', 'search box')"
        }
    }
    required_parameters = ["query"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        query = kwargs.get("query")
        if not query or not isinstance(query, str):
            return False, "query must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        query = kwargs["query"]
        
        # Capture screen first
        success, message, base64_data = _capture_screen_base64()
        if not success:
            return ToolResult.fail(error=f"Failed to capture screen: {message}")
        
        # Call vision gateway
        try:
            result = vision_call(base64_data, "detect_elements", query=query)
            
            if result["success"]:
                elements = result["result"]["elements"]
                return ToolResult.ok({
                    "elements": elements,
                    "count": len(elements)
                })
            else:
                return ToolResult.fail(error=result.get("error", "Vision call failed"))
                
        except Exception as e:
            log.error(f"Element detection failed: {e}")
            return ToolResult.fail(error=str(e))
    
    def estimate_duration(self, **kwargs) -> float:
        return 5.0  # Includes LLM call
    
    def risk_level(self) -> str:
        return "low"


class VisionReadTextTool(BaseTool):
    """
    Read all visible text from screen.
    
    Uses Gemma3 perception module via vision_call gateway.
    Returns extracted text as a single string.
    """
    
    name = "vision.read_text"
    description = "Read all visible text from the current screen using AI vision."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        # Capture screen first
        success, message, base64_data = _capture_screen_base64()
        if not success:
            return ToolResult.fail(error=f"Failed to capture screen: {message}")
        
        # Call vision gateway
        try:
            result = vision_call(base64_data, "read_text")
            
            if result["success"]:
                return ToolResult.ok(result["result"]["text"])
            else:
                return ToolResult.fail(error=result.get("error", "Vision call failed"))
                
        except Exception as e:
            log.error(f"Text reading failed: {e}")
            return ToolResult.fail(error=str(e))
    
    def estimate_duration(self, **kwargs) -> float:
        return 5.0  # Includes LLM call
    
    def risk_level(self) -> str:
        return "low"


class VisionDescribeSceneTool(BaseTool):
    """
    Get a one-sentence summary of what's on screen.
    
    Uses Gemma3 perception module via vision_call gateway.
    Returns brief scene description.
    """
    
    name = "vision.describe_scene"
    description = "Get a brief one-sentence description of what is shown on the current screen."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        # Capture screen first
        success, message, base64_data = _capture_screen_base64()
        if not success:
            return ToolResult.fail(error=f"Failed to capture screen: {message}")
        
        # Call vision gateway
        try:
            result = vision_call(base64_data, "describe_scene")
            
            if result["success"]:
                return ToolResult.ok(result["result"]["summary"])
            else:
                return ToolResult.fail(error=result.get("error", "Vision call failed"))
                
        except Exception as e:
            log.error(f"Scene description failed: {e}")
            return ToolResult.fail(error=str(e))
    
    def estimate_duration(self, **kwargs) -> float:
        return 5.0  # Includes LLM call
    
    def risk_level(self) -> str:
        return "low"


# Export only these 4 tools - NO OTHER VISION TOOLS ALLOWED
VISION_TOOLS = [
    ScreenCaptureTool,
    VisionDetectElementsTool,
    VisionReadTextTool,
    VisionDescribeSceneTool,
]
