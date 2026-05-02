"""
jarvis/core/vision.py
Visual Perception Engine for JARVIS.
Allows the agent to "see" the screen state, verify actions, and read UI elements.
"""

import os
import time
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

try:
    import mss
    import mss.tools
    from PIL import Image
    import pytesseract
    VISION_AVAILABLE = True
except ImportError as e:
    VISION_AVAILABLE = False
    logging.warning(f"Vision dependencies missing: {e}. Screen perception disabled.")

logger = logging.getLogger(__name__)

class ScreenPerceptor:
    """
    Handles screen capture, OCR, and visual state analysis.
    Used to verify if actions (like opening apps or searching) actually succeeded.
    """
    
    def __init__(self, output_dir: str = "jarvis_data/vision_cache"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure Tesseract path for Windows if necessary
        # Uncomment and adjust if Tesseract isn't in your PATH
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        
        if not VISION_AVAILABLE:
            raise RuntimeError("Vision modules (mss, PIL, pytesseract) not installed.")

    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> str:
        """
        Captures the screen (or a specific region) and saves it to a temporary file.
        Returns the file path to be sent to a Vision-capable LLM or processed via OCR.
        
        Args:
            region: (left, top, right, bottom) coordinates. If None, captures full screen.
            
        Returns:
            Path to the saved screenshot.
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"screen_{timestamp}.png"
        filepath = self.output_dir / filename
        
        try:
            with mss.mss() as sct:
                if region:
                    monitor = {
                        "left": region[0], 
                        "top": region[1], 
                        "width": region[2] - region[0], 
                        "height": region[3] - region[1]
                    }
                else:
                    # Capture primary monitor
                    monitor = sct.monitors[1] 
                
                screenshot = sct.grab(monitor)
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filepath))
                
            logger.debug(f"Screen captured: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            raise

    def read_screen_text(self, region: Optional[Tuple[int, int, int, int]] = None) -> str:
        """
        Performs OCR on the screen to extract visible text.
        Useful for verifying search results, error messages, or button labels.
        """
        try:
            img_path = self.capture_screen(region)
            image = Image.open(img_path)
            
            # Perform OCR
            text = pytesseract.image_to_string(image)
            
            # Clean up cache (optional, keep last 5 for debugging)
            self._cleanup_cache(keep=5)
            
            return text
            
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""

    def verify_element_visible(self, keyword: str, timeout: int = 5) -> bool:
        """
        Polls the screen for a specific text keyword (e.g., "Search", "Cars", "Error").
        Returns True if found within timeout.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            text_content = self.read_screen_text()
            if keyword.lower() in text_content.lower():
                logger.info(f"Verified element '{keyword}' is visible on screen.")
                return True
            time.sleep(0.5)
            
        logger.warning(f"Element '{keyword}' not found on screen after {timeout}s.")
        return False

    def _cleanup_cache(self, keep: int = 5):
        """Keeps only the most recent screenshots to save disk space."""
        files = sorted(self.output_dir.glob("screen_*.png"), key=os.path.getmtime, reverse=True)
        for old_file in files[keep:]:
            try:
                old_file.unlink()
            except Exception:
                pass

    def get_visual_context_summary(self) -> Dict:
        """
        Returns a summary of the current visual state for the LLM context.
        In a full vision-model setup, this would include the image embedding.
        For now, it provides OCR text and status.
        """
        try:
            text = self.read_screen_text()
            # Truncate text to avoid flooding context window
            truncated_text = text[:2000] if len(text) > 2000 else text
            
            return {
                "status": "success",
                "visible_text_sample": truncated_text,
                "text_length": len(text),
                "message": "Screen content extracted via OCR."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

# Singleton instance for easy import
_perceptor: Optional[ScreenPerceptor] = None

def get_perceptor() -> ScreenPerceptor:
    global _perceptor
    if _perceptor is None:
        try:
            _perceptor = ScreenPerceptor()
        except RuntimeError:
            logger.warning("ScreenPerceptor unavailable. Running in blind mode.")
            raise
    return _perceptor
