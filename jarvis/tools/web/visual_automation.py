"""
jarvis/tools/web/visual_automation.py — Visual-Based Web Automation
Uses computer vision (OpenCV + PyAutoGUI) to interact with websites by recognizing
visual elements on screen, independent of DOM structure or HTML selectors.
Perfect for sites with complex JavaScript, CAPTCHAs, or dynamic content.
"""

import logging
import time
from typing import Any, Optional, List, Dict, Tuple
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..base import BaseTool, ToolResult

# Lazy import pyautogui to avoid issues in headless environments
pyautogui = None

logger = logging.getLogger("visual_automation")


def _get_pyautogui():
    """Lazy load pyautogui with error handling."""
    global pyautogui
    if pyautogui is None:
        try:
            import pyautogui as pag
            pag.FAILSAFE = True  # Move mouse to corner to abort
            pag.PAUSE = 0.5  # Small delay between actions
            pyautogui = pag
            logger.info("PyAutoGUI initialized successfully")
        except Exception as e:
            logger.warning(f"PyAutoGUI not available (headless environment?): {e}")
            raise RuntimeError(f"Visual automation requires a display: {e}")
    return pyautogui


class VisualAutomationEngine:
    """
    Singleton engine for visual-based web automation.
    Uses screenshot analysis and image matching to find and interact with UI elements.
    """
    
    _instance: Optional['VisualAutomationEngine'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.confidence_threshold = 0.8
        self.search_region = None  # Full screen by default
        logger.info("VisualAutomationEngine initialized")
    
    def set_confidence(self, threshold: float):
        """Set the confidence threshold for image matching (0.0 - 1.0)."""
        self.confidence_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Confidence threshold set to {self.confidence_threshold}")
    
    def set_search_region(self, region: Optional[Tuple[int, int, int, int]]):
        """
        Set search region for element detection.
        Region format: (x, y, width, height) or None for full screen.
        """
        self.search_region = region
        if region:
            logger.info(f"Search region set to: {region}")
        else:
            logger.info("Search region set to full screen")
    
    def take_screenshot(self, region: Optional[Tuple] = None) -> np.ndarray:
        """Capture screenshot of screen or specific region."""
        try:
            pag = _get_pyautogui()
            if region:
                screenshot = pag.screenshot(region=region)
            else:
                screenshot = pag.screenshot(region=self.search_region)
            
            # Convert to OpenCV format (BGR)
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            return img
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            raise
    
    def find_image_on_screen(
        self, 
        template_path: str, 
        confidence: Optional[float] = None,
        grayscale: bool = False
    ) -> Optional[Dict]:
        """
        Find an image template on screen using template matching.
        
        Args:
            template_path: Path to template image file
            confidence: Match confidence threshold (default: instance threshold)
            grayscale: Whether to use grayscale matching
            
        Returns:
            Dict with 'location' (x, y), 'dimensions' (w, h), 'confidence' if found
            None if not found
        """
        try:
            template = cv2.imread(template_path)
            if template is None:
                logger.error(f"Could not load template: {template_path}")
                return None
            
            screenshot = self.take_screenshot()
            
            if grayscale:
                template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
                screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                result = cv2.matchTemplate(screenshot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            else:
                result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            
            threshold = confidence if confidence else self.confidence_threshold
            locations = np.where(result >= threshold)
            
            if len(locations[0]) > 0:
                # Get best match
                best_idx = np.argmax(result)
                best_y = locations[0][best_idx]
                best_x = locations[1][best_idx]
                best_confidence = float(result[best_y, best_x])
                
                h, w = template.shape[:2]
                
                logger.info(f"Found template at ({best_x}, {best_y}) with confidence {best_confidence:.2f}")
                return {
                    'location': (best_x, best_y),
                    'dimensions': (w, h),
                    'confidence': best_confidence,
                    'center': (best_x + w // 2, best_y + h // 2)
                }
            
            logger.debug(f"Template not found (threshold: {threshold})")
            return None
            
        except Exception as e:
            logger.error(f"Image matching failed: {e}")
            return None
    
    def find_text_on_screen(
        self, 
        text: str,
        case_sensitive: bool = False
    ) -> Optional[Dict]:
        """
        Find text on screen using OCR (requires pytesseract).
        Falls back to simple pixel matching for common UI elements.
        
        Args:
            text: Text to search for
            case_sensitive: Whether to match case exactly
            
        Returns:
            Dict with location info if found, None otherwise
        """
        try:
            # Try OCR approach first
            try:
                import pytesseract
                
                screenshot = self.take_screenshot()
                screenshot_rgb = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
                
                # Get OCR data with bounding boxes
                data = pytesseract.image_to_data(screenshot_rgb, output_type=pytesseract.Output.DICT)
                
                n_boxes = len(data['text'])
                search_text = text.lower() if not case_sensitive else text
                
                for i in range(n_boxes):
                    box_text = data['text'][i]
                    if not box_text.strip():
                        continue
                    
                    compare_text = box_text.lower() if not case_sensitive else box_text
                    
                    if search_text in compare_text:
                        x = data['left'][i]
                        y = data['top'][i]
                        w = data['width'][i]
                        h = data['height'][i]
                        
                        logger.info(f"Found text '{text}' at ({x}, {y})")
                        return {
                            'location': (x, y),
                            'dimensions': (w, h),
                            'text': box_text,
                            'center': (x + w // 2, y + h // 2)
                        }
                
                logger.debug(f"Text '{text}' not found via OCR")
                
            except ImportError:
                logger.warning("pytesseract not available. OCR disabled.")
            
            # Fallback: Try to find common UI element patterns
            # This is a simplified approach - in production you'd use more sophisticated methods
            return self._find_ui_element_by_description(text)
            
        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return None
    
    def _find_ui_element_by_description(self, description: str) -> Optional[Dict]:
        """
        Attempt to find UI elements based on common visual patterns.
        This is a fallback when OCR is not available.
        """
        # For now, this is a placeholder
        # In a full implementation, you could use ML models or heuristics
        logger.debug(f"No visual pattern matcher for: {description}")
        return None
    
    def click_at_position(self, x: int, y: int, clicks: int = 1, button: str = 'left'):
        """Click at specific screen coordinates."""
        try:
            pag = _get_pyautogui()
            pag.click(x=x, y=y, clicks=clicks, button=button, interval=0.3)
            logger.info(f"Clicked at ({x}, {y})")
        except Exception as e:
            logger.error(f"Click failed: {e}")
            raise
    
    def click_on_image(
        self, 
        template_path: str, 
        confidence: Optional[float] = None,
        clicks: int = 1
    ) -> bool:
        """
        Find an image on screen and click on it.
        
        Returns:
            True if successful, False otherwise
        """
        result = self.find_image_on_screen(template_path, confidence)
        if result:
            center_x, center_y = result['center']
            self.click_at_position(center_x, center_y, clicks)
            return True
        return False
    
    def type_text(self, text: str, interval: float = 0.05):
        """Type text at current cursor position."""
        try:
            pag = _get_pyautogui()
            pag.write(text, interval=interval)
            logger.info(f"Typed: {text[:50]}...")
        except Exception as e:
            logger.error(f"Type failed: {e}")
            raise
    
    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None):
        """Scroll mouse wheel up (positive) or down (negative)."""
        try:
            pag = _get_pyautogui()
            pag.scroll(amount, x=x, y=y)
            logger.info(f"Scrolled {amount} at ({x}, {y})")
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            raise
    
    def move_mouse(self, x: int, y: int, duration: float = 0.5):
        """Move mouse to specific coordinates."""
        try:
            pag = _get_pyautogui()
            pag.moveTo(x, y, duration=duration)
            logger.debug(f"Mouse moved to ({x}, {y})")
        except Exception as e:
            logger.error(f"Mouse move failed: {e}")
            raise
    
    def wait_for_image(
        self, 
        template_path: str, 
        timeout: float = 10.0,
        confidence: Optional[float] = None,
        check_interval: float = 0.5
    ) -> Optional[Dict]:
        """
        Wait for an image to appear on screen.
        
        Returns:
            Match result dict if found within timeout, None otherwise
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            result = self.find_image_on_screen(template_path, confidence)
            if result:
                return result
            time.sleep(check_interval)
        
        logger.debug(f"Image not found within {timeout}s timeout")
        return None
    
    def highlight_region(self, x: int, y: int, w: int, h: int, duration: float = 2.0):
        """Draw a temporary rectangle around a region (for debugging/feedback)."""
        try:
            # Create a semi-transparent overlay
            import tkinter as tk
            
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes('-topmost', True)
            root.attributes('-alpha', 0.5)
            
            canvas = tk.Canvas(root, width=w, height=h, bg='red', highlightthickness=0)
            canvas.pack()
            
            root.geometry(f"{w}x{h}+{x}+{y}")
            
            # Auto-close after duration
            root.after(int(duration * 1000), root.destroy)
            root.mainloop()
            
            logger.debug(f"Highlighted region: ({x}, {y}, {w}, {h})")
        except Exception as e:
            logger.debug(f"Could not highlight region: {e}")


# Global engine instance
_visual_engine: Optional[VisualAutomationEngine] = None

def get_visual_engine() -> VisualAutomationEngine:
    global _visual_engine
    if _visual_engine is None:
        _visual_engine = VisualAutomationEngine()
    return _visual_engine


class FindAndClickTool(BaseTool):
    """Find a visual element on screen and click it."""
    
    name = "visual_click"
    description = "Click on a UI element by finding its image template or text label. Works on any website regardless of HTML structure."
    parameters = {
        "template_path": {
            "type": "string",
            "description": "Path to template image file (PNG/JPG) showing the element to click",
            "default": None
        },
        "text_label": {
            "type": "string", 
            "description": "Alternative: text visible on the element (uses OCR)",
            "default": None
        },
        "confidence": {
            "type": "number",
            "description": "Match confidence threshold (0.0-1.0). Lower = more lenient.",
            "default": 0.8
        },
        "double_click": {
            "type": "boolean",
            "description": "Perform double-click instead of single click",
            "default": False
        }
    }
    required_parameters = []  # Either template_path or text_label required
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        template = kwargs.get("template_path")
        text = kwargs.get("text_label")
        
        if not template and not text:
            return False, "Must provide either template_path or text_label"
        
        if template and not Path(template).exists():
            return False, f"Template file not found: {template}"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        template_path = kwargs.get("template_path")
        text_label = kwargs.get("text_label")
        confidence = kwargs.get("confidence", 0.8)
        double_click = kwargs.get("double_click", False)
        
        try:
            engine = get_visual_engine()
            
            result = None
            if template_path:
                result = engine.find_image_on_screen(template_path, confidence)
            elif text_label:
                result = engine.find_text_on_screen(text_label)
            
            if not result:
                return ToolResult.fail(error="Element not found on screen")
            
            x, y = result['center']
            clicks = 2 if double_click else 1
            engine.click_at_position(x, y, clicks)
            
            return ToolResult.ok(f"Clicked at ({x}, {y}) with confidence {result['confidence']:.2f}")
            
        except Exception as e:
            logger.error(f"Visual click failed: {e}")
            return ToolResult.fail(error=f"Visual click failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.0
    
    def risk_level(self) -> str:
        return "low"


class FindAndTypeTool(BaseTool):
    """Find a field visually and type into it."""
    
    name = "visual_type"
    description = "Find an input field by its visual appearance or nearby label, then type text into it."
    parameters = {
        "field_template": {
            "type": "string",
            "description": "Path to template image of the input field",
            "default": None
        },
        "label_text": {
            "type": "string",
            "description": "Text label near the input field (uses OCR)",
            "default": None
        },
        "text_to_type": {
            "type": "string",
            "description": "Text to type into the field"
        },
        "clear_first": {
            "type": "boolean",
            "description": "Clear existing content before typing",
            "default": True
        }
    }
    required_parameters = ["text_to_type"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        text = kwargs.get("text_to_type")
        if not text:
            return False, "text_to_type is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        field_template = kwargs.get("field_template")
        label_text = kwargs.get("label_text")
        text_to_type = kwargs["text_to_type"]
        clear_first = kwargs.get("clear_first", True)
        
        try:
            engine = get_visual_engine()
            
            # Find the field
            result = None
            if field_template:
                result = engine.find_image_on_screen(field_template)
            elif label_text:
                result = engine.find_text_on_screen(label_text)
            
            if not result:
                return ToolResult.fail(error="Input field not found on screen")
            
            # Click to focus
            x, y = result['center']
            engine.click_at_position(x, y)
            time.sleep(0.3)
            
            # Clear if needed
            if clear_first:
                pag = _get_pyautogui()
                pag.hotkey('ctrl', 'a')
                time.sleep(0.2)
                pag.press('delete')
                time.sleep(0.2)
            
            # Type the text
            engine.type_text(text_to_type)
            
            return ToolResult.ok(f"Typed into field at ({x}, {y})")
            
        except Exception as e:
            logger.error(f"Visual type failed: {e}")
            return ToolResult.fail(error=f"Visual type failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.5
    
    def risk_level(self) -> str:
        return "low"


class ScrollPageTool(BaseTool):
    """Scroll the page visually."""
    
    name = "visual_scroll"
    description = "Scroll the page up or down by a specified amount."
    parameters = {
        "direction": {
            "type": "string",
            "description": "Direction to scroll: 'up' or 'down'",
            "enum": ["up", "down"]
        },
        "amount": {
            "type": "integer",
            "description": "Scroll amount (positive number). Default: 300 pixels",
            "default": 300
        },
        "x": {
            "type": "integer",
            "description": "Optional X coordinate to scroll at",
            "default": None
        },
        "y": {
            "type": "integer",
            "description": "Optional Y coordinate to scroll at",
            "default": None
        }
    }
    required_parameters = ["direction"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        direction = kwargs.get("direction")
        if direction not in ["up", "down"]:
            return False, "direction must be 'up' or 'down'"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        direction = kwargs["direction"]
        amount = kwargs.get("amount", 300)
        x = kwargs.get("x")
        y = kwargs.get("y")
        
        try:
            engine = get_visual_engine()
            
            scroll_amount = amount if direction == "up" else -amount
            engine.scroll(scroll_amount, x, y)
            
            return ToolResult.ok(f"Scrolled {direction} by {amount} pixels")
            
        except Exception as e:
            logger.error(f"Visual scroll failed: {e}")
            return ToolResult.fail(error=f"Visual scroll failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class WaitForVisualElementTool(BaseTool):
    """Wait for a visual element to appear on screen."""
    
    name = "visual_wait"
    description = "Wait for a visual element (image template or text) to appear on screen."
    parameters = {
        "template_path": {
            "type": "string",
            "description": "Path to template image to wait for",
            "default": None
        },
        "text_label": {
            "type": "string",
            "description": "Text to wait for (uses OCR)",
            "default": None
        },
        "timeout": {
            "type": "number",
            "description": "Maximum time to wait in seconds",
            "default": 10.0
        },
        "confidence": {
            "type": "number",
            "description": "Match confidence threshold",
            "default": 0.8
        }
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        template = kwargs.get("template_path")
        text = kwargs.get("text_label")
        
        if not template and not text:
            return False, "Must provide either template_path or text_label"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        template_path = kwargs.get("template_path")
        text_label = kwargs.get("text_label")
        timeout = kwargs.get("timeout", 10.0)
        confidence = kwargs.get("confidence", 0.8)
        
        try:
            engine = get_visual_engine()
            
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                result = None
                if template_path:
                    result = engine.find_image_on_screen(template_path, confidence)
                elif text_label:
                    result = engine.find_text_on_screen(text_label)
                
                if result:
                    return ToolResult.ok(f"Element found at {result['location']} after {time.time() - start_time:.1f}s")
                
                time.sleep(0.5)
            
            return ToolResult.fail(error=f"Element not found within {timeout}s timeout")
            
        except Exception as e:
            logger.error(f"Visual wait failed: {e}")
            return ToolResult.fail(error=f"Visual wait failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return kwargs.get("timeout", 10.0) / 2
    
    def risk_level(self) -> str:
        return "low"


class TakeVisualSnapshotTool(BaseTool):
    """Take a screenshot and save it."""
    
    name = "visual_snapshot"
    description = "Capture a screenshot of the entire screen or a specific region."
    parameters = {
        "filename": {
            "type": "string",
            "description": "Output filename (without extension)",
            "default": None
        },
        "region": {
            "type": "object",
            "description": "Region to capture: {x, y, width, height}",
            "default": None
        },
        "highlight_elements": {
            "type": "boolean",
            "description": "Detect and highlight clickable elements",
            "default": False
        }
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        filename = kwargs.get("filename")
        region = kwargs.get("region")
        
        try:
            from pathlib import Path
            import time
            
            output_dir = Path("jarvis_data/screenshots")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if not filename:
                filename = f"snapshot_{time.strftime('%Y%m%d_%H%M%S')}"
            
            filepath = output_dir / f"{filename}.png"
            
            pag = _get_pyautogui()
            screenshot = pag.screenshot()
            if region:
                screenshot = screenshot.crop((
                    region.get('x', 0),
                    region.get('y', 0),
                    region.get('x', 0) + region.get('width', screenshot.width),
                    region.get('y', 0) + region.get('height', screenshot.height)
                ))
            
            screenshot.save(str(filepath))
            
            return ToolResult.ok(f"Screenshot saved: {filepath}")
            
        except Exception as e:
            logger.error(f"Visual snapshot failed: {e}")
            return ToolResult.fail(error=f"Visual snapshot failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
VISUAL_AUTOMATION_TOOLS = [
    FindAndClickTool,
    FindAndTypeTool,
    ScrollPageTool,
    WaitForVisualElementTool,
    TakeVisualSnapshotTool,
]
