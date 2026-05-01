"""
Vision - Screen analysis using multimodal LLM.
Analyzes screenshots to understand what's visible on screen.
"""

import base64
import io
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None


class VisionAnalyzer:
    """
    Analyzes screenshots using multimodal LLM capabilities.
    Returns structured descriptions of screen content.
    """
    
    def __init__(self, ollama_client=None):
        """
        Initialize the vision analyzer.
        
        Args:
            ollama_client: OllamaClient instance for LLM calls
        """
        self.ollama_client = ollama_client
        self.last_analysis = None
        self.analysis_history = []
    
    def set_client(self, client) -> None:
        """Set the Ollama client."""
        self.ollama_client = client
    
    def analyze_screen(self, screenshot_base64: str = None,
                       prompt: str = None) -> Dict[str, Any]:
        """
        Analyze a screenshot and return structured description.
        
        Args:
            screenshot_base64: Base64-encoded screenshot (optional, will capture if not provided)
            prompt: Custom analysis prompt (optional)
            
        Returns:
            Dictionary with analysis results
        """
        if self.ollama_client is None:
            return {
                'success': False,
                'error': 'No Ollama client configured',
                'output': None
            }
        
        # Capture screenshot if not provided
        if screenshot_base64 is None:
            capture_result = self._capture_screenshot()
            if not capture_result['success']:
                return capture_result
            screenshot_base64 = capture_result['output']
        
        # Default analysis prompt
        if prompt is None:
            prompt = """Analyze this screenshot and provide a structured description including:
1. What application(s) are visible
2. Window titles and their positions
3. Visible text content (headings, buttons, labels)
4. UI elements present (menus, toolbars, dialogs)
5. Any error messages or notifications
6. Current user task context (what appears to be happening)
7. Interactive elements that could be clicked

Respond in a structured format with clear sections."""
        
        try:
            # Call multimodal LLM
            response = self.ollama_client.chat_with_image(
                image_base64=screenshot_base64,
                prompt=prompt,
                model='llava-llama3-cloud'  # Multimodal model
            )
            
            analysis = {
                'success': True,
                'output': response.get('content', ''),
                'timestamp': datetime.now().isoformat(),
                'image_dimensions': self._get_image_dimensions(screenshot_base64)
            }
            
            # Store in history
            self.last_analysis = analysis
            self.analysis_history.append(analysis)
            
            # Keep history bounded
            if len(self.analysis_history) > 10:
                self.analysis_history = self.analysis_history[-10:]
            
            return analysis
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': None
            }
    
    def find_on_screen(self, description: str, 
                       screenshot_base64: str = None) -> Dict[str, Any]:
        """
        Find something on screen based on description.
        
        Args:
            description: Description of what to find (e.g., "the Save button", "close icon")
            screenshot_base64: Optional existing screenshot
            
        Returns:
            Dictionary with coordinates and confidence
        """
        if self.ollama_client is None:
            return {
                'success': False,
                'error': 'No Ollama client configured',
                'output': None
            }
        
        # Capture screenshot if not provided
        if screenshot_base64 is None:
            capture_result = self._capture_screenshot()
            if not capture_result['success']:
                return capture_result
            screenshot_base64 = capture_result['output']
        
        prompt = f"""Look at this screenshot and find: {description}

Return the location as coordinates [x, y] relative to the top-left corner.
Also provide:
- Confidence level (high/medium/low)
- Bounding box if it's an element with size: [x1, y1, x2, y2]
- Brief description of what you found

Respond in JSON format:
{{
    "found": true/false,
    "coordinates": [x, y],
    "bounding_box": [x1, y1, x2, y2] or null,
    "confidence": "high/medium/low",
    "description": "what was found"
}}"""
        
        try:
            response = self.ollama_client.chat_with_image(
                image_base64=screenshot_base64,
                prompt=prompt,
                model='llava-llama3-cloud',
                response_format='json'
            )
            
            result = {
                'success': True,
                'output': response.get('content', ''),
                'timestamp': datetime.now().isoformat()
            }
            
            # Try to parse JSON response
            import json
            try:
                parsed = json.loads(response.get('content', '{}'))
                result['parsed'] = parsed
            except:
                result['parsed'] = None
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': None
            }
    
    def _capture_screenshot(self) -> Dict[str, Any]:
        """Capture a screenshot and return as base64."""
        try:
            import mss
            import base64
            from io import BytesIO
            
            with mss.mss() as sct:
                # Capture primary monitor
                monitor = sct.monitors[1]  # Primary monitor
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                if Image is None:
                    return {
                        'success': False,
                        'error': 'PIL not available',
                        'output': None
                    }
                
                img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
                
                # Convert to base64
                buffer = BytesIO()
                img.save(buffer, format='PNG')
                img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                return {
                    'success': True,
                    'output': img_base64,
                    'dimensions': screenshot.size
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': None
            }
    
    def _get_image_dimensions(self, base64_str: str) -> Optional[Tuple[int, int]]:
        """Get dimensions of a base64-encoded image."""
        try:
            if Image is None:
                return None
            
            import base64
            from io import BytesIO
            
            img_data = base64.b64decode(base64_str)
            img = Image.open(BytesIO(img_data))
            return img.size
        except:
            return None
    
    def get_realtime_capture(self) -> Dict[str, Any]:
        """
        Get current screen state for realtime monitoring.
        Similar to screenshot but optimized for frequent calls.
        
        Returns:
            Dictionary with screenshot and basic analysis
        """
        capture_result = self._capture_screenshot()
        
        if not capture_result['success']:
            return capture_result
        
        # Quick analysis
        analysis = {
            'success': True,
            'screenshot': capture_result['output'],
            'dimensions': capture_result.get('dimensions'),
            'timestamp': datetime.now().isoformat()
        }
        
        return analysis
    
    def compare_screenshots(self, before_base64: str, 
                           after_base64: str) -> Dict[str, Any]:
        """
        Compare two screenshots and describe differences.
        
        Args:
            before_base64: First screenshot
            after_base64: Second screenshot
            
        Returns:
            Dictionary describing changes
        """
        if self.ollama_client is None:
            return {
                'success': False,
                'error': 'No Ollama client configured',
                'output': None
            }
        
        prompt = """Compare these two screenshots (before and after).
Describe what changed between them:
- What appeared?
- What disappeared?
- What moved or changed position?
- What content was modified?

Be specific about the differences."""
        
        try:
            # Note: This would require a model that can handle multiple images
            # For now, we'll analyze them separately and compare
            before_analysis = self.analyze_screen(before_base64, "Describe what is visible in this screenshot.")
            after_analysis = self.analyze_screen(after_base64, "Describe what is visible in this screenshot.")
            
            comparison_prompt = f"""Compare these two analyses and describe the differences:

BEFORE:
{before_analysis.get('output', 'No analysis available')}

AFTER:
{after_analysis.get('output', 'No analysis available')}

What changed?"""
            
            # Simple text-based comparison
            response = self.ollama_client.chat(
                messages=[{'role': 'user', 'content': comparison_prompt}]
            )
            
            return {
                'success': True,
                'output': response.get('content', ''),
                'before_analysis': before_analysis,
                'after_analysis': after_analysis
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': None
            }
    
    def get_analysis_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent analysis history."""
        return self.analysis_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear analysis history."""
        self.analysis_history = []
        self.last_analysis = None


# Singleton instance
_vision_instance = None

def get_vision_analyzer(ollama_client=None) -> VisionAnalyzer:
    """Get the singleton VisionAnalyzer instance."""
    global _vision_instance
    if _vision_instance is None:
        _vision_instance = VisionAnalyzer(ollama_client)
    elif ollama_client is not None:
        _vision_instance.set_client(ollama_client)
    return _vision_instance
