"""
3. Vision & Screen Understanding (3 tools)
Powered by Gemma 3 27B.
"""

from typing import Optional, Any
from dataclasses import dataclass
import logging
import base64

logger = logging.getLogger(__name__)


@dataclass
class ScreenCaptureResult:
    """Result of screen capture."""
    success: bool
    image_path: Optional[str]
    image_data: Optional[bytes]
    dimensions: tuple
    timestamp: float


class ScreenCapture:
    """
    screen_capture: Grab screen or region
    
    Captures screenshots with optional region selection.
    """
    
    def __init__(self, default_format: str = "png"):
        self.default_format = default_format
    
    def execute(self, region: Optional[tuple] = None, 
                monitor: int = 0, save_path: Optional[str] = None,
                return_data: bool = True, **kwargs) -> dict:
        """
        Capture screen or region.
        
        Args:
            region: (x, y, width, height) for specific region, None for full screen
            monitor: Monitor index (0 for primary)
            save_path: Optional path to save image
            return_data: Whether to return image data
            
        Returns:
            Capture result with image data/path
        """
        try:
            import time
            from PIL import ImageGrab
            
            timestamp = time.time()
            
            # Capture screen
            if region:
                screenshot = ImageGrab.grab(bbox=region)
            else:
                screenshot = ImageGrab.grab()
            
            dimensions = screenshot.size
            
            # Save if path provided
            image_path = None
            if save_path:
                screenshot.save(save_path)
                image_path = save_path
            
            # Get image data if requested
            image_data = None
            if return_data:
                from io import BytesIO
                buffer = BytesIO()
                screenshot.save(buffer, format=self.default_format)
                image_data = buffer.getvalue()
            
            return {
                "success": True,
                "output": {
                    "image_path": image_path,
                    "image_data_base64": base64.b64encode(image_data).decode() if image_data else None,
                    "dimensions": dimensions,
                    "timestamp": timestamp,
                    "format": self.default_format
                }
            }
            
        except ImportError:
            return {
                "success": False,
                "error": "PIL/Pillow not installed. Install with: pip install Pillow",
                "output": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }


@dataclass
class OCRResult:
    """Result of OCR extraction."""
    success: bool
    text: str
    confidence: float
    bounding_boxes: list
    language: str


class OCRExtractText:
    """
    ocr_extract_text: Text from images/screen
    
    Extracts text from images using OCR.
    """
    
    def __init__(self, default_language: str = "eng"):
        self.default_language = default_language
    
    def execute(self, image_path: Optional[str] = None,
                image_data: Optional[bytes] = None,
                language: Optional[str] = None,
                return_confidence: bool = True,
                **kwargs) -> dict:
        """
        Extract text from image.
        
        Args:
            image_path: Path to image file
            image_data: Raw image bytes (alternative to path)
            language: OCR language code
            return_confidence: Include confidence scores
            
        Returns:
            OCR result with extracted text
        """
        try:
            import pytesseract
            from PIL import Image
            
            # Load image
            if image_path:
                image = Image.open(image_path)
            elif image_data:
                from io import BytesIO
                image = Image.open(BytesIO(image_data))
            else:
                return {
                    "success": False,
                    "error": "No image provided (path or data required)",
                    "output": None
                }
            
            lang = language or self.default_language
            
            # Perform OCR
            ocr_data = pytesseract.image_to_data(
                image, 
                lang=lang,
                output_type=pytesseract.Output.DICT
            )
            
            # Extract text
            text = pytesseract.image_to_string(image, lang=lang)
            
            # Calculate average confidence
            confidences = [c for c in ocr_data['conf'] if c != -1]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            # Extract bounding boxes
            bounding_boxes = []
            for i, box_text in enumerate(ocr_data['text']):
                if box_text.strip():
                    bounding_boxes.append({
                        "text": box_text,
                        "x": ocr_data['left'][i],
                        "y": ocr_data['top'][i],
                        "width": ocr_data['width'][i],
                        "height": ocr_data['height'][i],
                        "confidence": ocr_data['conf'][i]
                    })
            
            return {
                "success": True,
                "output": {
                    "text": text,
                    "confidence": avg_confidence / 100.0,
                    "bounding_boxes": bounding_boxes if return_confidence else [],
                    "language": lang
                }
            }
            
        except ImportError as e:
            return {
                "success": False,
                "error": f"OCR dependencies not installed: {e}",
                "output": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }


@dataclass
class VisionAnalysisResult:
    """Result of vision analysis."""
    success: bool
    description: str
    objects: list
    ui_elements: list
    confidence: float


class VisionAnalyzer:
    """
    vision_analyzer: Interpret UI, detect buttons, objects
    
    Uses Gemma 3 27B to analyze screen content and identify UI elements.
    """
    
    def __init__(self, vision_model=None):
        self.vision_model = vision_model
        self._object_classes = [
            "button", "input", "checkbox", "dropdown", "menu",
            "icon", "image", "text_block", "link", "table",
            "form", "dialog", "notification", "progress_bar"
        ]
    
    def execute(self, image_path: Optional[str] = None,
                image_data: Optional[bytes] = None,
                analysis_type: str = "ui_elements",
                prompt: Optional[str] = None,
                **kwargs) -> dict:
        """
        Analyze image/screen content.
        
        Args:
            image_path: Path to image
            image_data: Raw image bytes
            analysis_type: One of 'ui_elements', 'objects', 'scene_description'
            prompt: Custom analysis prompt
            
        Returns:
            Analysis results
        """
        try:
            # Load image
            image_source = None
            if image_path:
                image_source = image_path
            elif image_data:
                image_source = base64.b64encode(image_data).decode()
            else:
                return {
                    "success": False,
                    "error": "No image provided",
                    "output": None
                }
            
            # Default prompts by analysis type
            if prompt is None:
                prompts = {
                    "ui_elements": "Identify all UI elements (buttons, inputs, menus, etc.) in this screenshot. For each element, describe its type, location, and apparent function.",
                    "objects": "Detect and describe all objects visible in this image.",
                    "scene_description": "Provide a detailed description of what is shown in this screenshot."
                }
                prompt = prompts.get(analysis_type, prompts["scene_description"])
            
            # Use vision model if available
            if self.vision_model:
                return self._analyze_with_model(image_source, prompt)
            else:
                # Fallback heuristic analysis
                return self._heuristic_analysis(image_source, analysis_type)
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _analyze_with_model(self, image: str, prompt: str) -> dict:
        """Analyze using Gemma 3 27B vision model."""
        # TODO: Integrate with actual Gemma 3 27B vision model
        logger.info("Analyzing with vision model...")
        
        # Placeholder response
        return {
            "success": True,
            "output": {
                "description": "Vision model analysis would be performed here",
                "objects": [],
                "ui_elements": [],
                "confidence": 0.95,
                "model": "gemma_3_27b_vision"
            }
        }
    
    def _heuristic_analysis(self, image: str, analysis_type: str) -> dict:
        """Fallback heuristic analysis without model."""
        # This would use OpenCV or similar for basic detection
        logger.warning("Using heuristic analysis (no vision model available)")
        
        return {
            "success": True,
            "output": {
                "description": f"Heuristic {analysis_type} analysis - requires vision model for detailed results",
                "objects": [],
                "ui_elements": [],
                "confidence": 0.5,
                "note": "Install and configure Gemma 3 27B for accurate analysis"
            }
        }


# Factory functions for capability registry
def get_screen_capture(default_format: str = "png") -> ScreenCapture:
    return ScreenCapture(default_format=default_format)


def get_ocr_extract_text(default_language: str = "eng") -> OCRExtractText:
    return OCRExtractText(default_language=default_language)


def get_vision_analyzer(vision_model=None) -> VisionAnalyzer:
    return VisionAnalyzer(vision_model=vision_model)
