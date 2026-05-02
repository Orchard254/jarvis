"""
Vision - Screen analysis using multimodal LLM.
Analyzes screenshots to understand what's visible on screen.
"""

import base64
import io
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

try:
    from PIL import Image
except ImportError:
    Image = None


@dataclass
class ScreenState:
    """Structured representation of current screen state."""
    open_windows: List[str]
    active_window: Optional[str]
    visible_text: List[str]
    error_messages: List[str]
    ui_elements: List[Dict[str, Any]]
    screen_description: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_formatted_string(self) -> str:
        """Return formatted string suitable for LLM reading."""
        lines = [
            "=== SCREEN STATE ===",
            f"Active Window: {self.active_window or 'Unknown'}",
            "",
            "Open Windows:",
        ]
        for w in self.open_windows:
            lines.append(f"  - {w}")
        
        if self.visible_text:
            lines.extend(["", "Visible Text:"])
            for t in self.visible_text[:10]:  # Limit to top 10
                lines.append(f"  - {t[:100]}")  # Truncate long text
        
        if self.error_messages:
            lines.extend(["", "⚠️ ERROR MESSAGES:"])
            for e in self.error_messages:
                lines.append(f"  - {e}")
        
        if self.ui_elements:
            lines.extend(["", "UI Elements:"])
            for el in self.ui_elements[:15]:  # Limit to 15
                elem_type = el.get('type', 'element')
                elem_text = el.get('text', '')
                lines.append(f"  - [{elem_type}] {elem_text[:50]}")
        
        lines.extend(["", f"Summary: {self.screen_description}"])
        return "\n".join(lines)


class VisionAnalyzer:
    """
    Analyzes screenshots using multimodal LLM capabilities.
    Returns structured descriptions of screen content.
    """
    
    # Cache settings
    CACHE_TTL_SECONDS = 5
    
    def __init__(self, ollama_client=None):
        """
        Initialize the vision analyzer.
        
        Args:
            ollama_client: OllamaClient instance for LLM calls
        """
        self.ollama_client = ollama_client
        self.last_analysis = None
        self.analysis_history = []
        # Cache: (base64_hash, timestamp, result)
        self._cache = None
    
    def set_client(self, client) -> None:
        """Set the Ollama client."""
        self.ollama_client = client
    
    def _get_cache_key(self, base64_str: str) -> str:
        """Generate a simple hash key for caching."""
        # Use first 1000 chars as proxy for full image hash (fast approximation)
        return base64_str[:1000] if len(base64_str) > 1000 else base64_str
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached result is still valid (within TTL)."""
        if self._cache is None:
            return False
        cached_key, cached_time, _ = self._cache
        if cached_key != cache_key:
            return False
        elapsed = time.time() - cached_time
        return elapsed < self.CACHE_TTL_SECONDS
    
    def analyze_screen(self, screenshot_base64: str = None,
                       prompt: str = None) -> Dict[str, Any]:
        """
        Analyze a screenshot and return structured description.
        
        Args:
            screenshot_base64: Base64-encoded screenshot (optional, will capture if not provided)
            prompt: Custom analysis prompt (optional)
            
        Returns:
            Dictionary with ScreenState object and analysis results
        """
        if self.ollama_client is None:
            return {
                'success': False,
                'error': 'No Ollama client configured',
                'output': None,
                'screen_state': None
            }
        
        # Capture screenshot if not provided
        if screenshot_base64 is None:
            capture_result = self._capture_screenshot()
            if not capture_result['success']:
                return capture_result
            screenshot_base64 = capture_result['output']
        
        # Check cache
        cache_key = self._get_cache_key(screenshot_base64)
        if self._is_cache_valid(cache_key):
            _, _, cached_result = self._cache
            return {
                'success': True,
                'output': cached_result.get('screen_description', ''),
                'screen_state': cached_result,
                'from_cache': True,
                'timestamp': datetime.now().isoformat()
            }
        
        # Default analysis prompt - structured for JSON output
        if prompt is None:
            prompt = """Analyze this screenshot and return JSON ONLY with this exact schema:
{
    "open_windows": ["list", "of", "window", "titles"],
    "active_window": "current foreground window title or null",
    "visible_text": ["important", "text", "visible", "on", "screen"],
    "error_messages": ["any", "error", "dialogs", "visible"],
    "ui_elements": [{"type": "button|input|menu|icon", "text": "label", "position": {"x": 0, "y": 0}}],
    "screen_description": "one sentence summary of what's on screen"
}

If the screen is locked, blank, or shows a login screen, set:
- open_windows: []
- active_window: null  
- visible_text: []
- error_messages: []
- ui_elements: []
- screen_description: "Screen is locked/blank/login screen"

Return ONLY valid JSON, no markdown, no explanations."""
        
        try:
            # Call multimodal LLM
            response = self.ollama_client.chat_with_image(
                image_base64=screenshot_base64,
                prompt=prompt,
                model='llava-llama3-cloud',  # Multimodal model
                response_format='json'
            )
            
            content = response.get('content', '')
            
            # Parse JSON response
            try:
                # Extract JSON from response (handle markdown code blocks)
                json_str = content.strip()
                if json_str.startswith('```'):
                    json_str = json_str.split('```')[1]
                    if json_str.startswith('json'):
                        json_str = json_str[4:]
                json_str = json_str.strip()
                
                parsed_data = json.loads(json_str)
                
                # Create ScreenState object
                screen_state = ScreenState(
                    open_windows=parsed_data.get('open_windows', []),
                    active_window=parsed_data.get('active_window'),
                    visible_text=parsed_data.get('visible_text', []),
                    error_messages=parsed_data.get('error_messages', []),
                    ui_elements=parsed_data.get('ui_elements', []),
                    screen_description=parsed_data.get('screen_description', '')
                )
                
            except (json.JSONDecodeError, KeyError) as e:
                # Fallback: create minimal ScreenState from text response
                screen_state = ScreenState(
                    open_windows=[],
                    active_window=None,
                    visible_text=[],
                    error_messages=[],
                    ui_elements=[],
                    screen_description=content[:200] if content else "Unable to parse screen content"
                )
            
            analysis = {
                'success': True,
                'output': screen_state.screen_description,
                'screen_state': screen_state,
                'timestamp': datetime.now().isoformat(),
                'image_dimensions': self._get_image_dimensions(screenshot_base64),
                'from_cache': False
            }
            
            # Update cache
            self._cache = (cache_key, time.time(), screen_state.to_dict())
            
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
                'output': None,
                'screen_state': None
            }
    
    def find_on_screen(self, description: str, 
                       screenshot_base64: str = None) -> Dict[str, Any]:
        """
        Find something on screen based on description.
        
        Args:
            description: Description of what to find (e.g., "the Save button", "close icon")
            screenshot_base64: Optional existing screenshot
            
        Returns:
            Dictionary with coordinates {x, y, confidence} or null if not found
        """
        if self.ollama_client is None:
            return {
                'success': False,
                'error': 'No Ollama client configured',
                'found': False,
                'coordinates': None
            }
        
        # Capture screenshot if not provided
        if screenshot_base64 is None:
            capture_result = self._capture_screenshot()
            if not capture_result['success']:
                return capture_result
            screenshot_base64 = capture_result['output']
        
        prompt = f"""Look at this screenshot and find: {description}

Return the location as pixel coordinates {{x: int, y: int}} relative to the top-left corner.
Also provide a confidence score from 0.0 to 1.0.

IMPORTANT: Return ONLY valid JSON in this exact format:
{{
    "found": true/false,
    "x": integer_x_coordinate,
    "y": integer_y_coordinate,
    "confidence": float_0_to_1,
    "description": "brief description of what was found"
}}

If you cannot find "{description}", set found=false and x=null, y=null, confidence=0.0.
Do not include markdown formatting or explanations. Only return JSON."""
        
        try:
            response = self.ollama_client.chat_with_image(
                image_base64=screenshot_base64,
                prompt=prompt,
                model='llava-llama3-cloud',
                response_format='json'
            )
            
            content = response.get('content', '')
            
            # Parse JSON response
            try:
                # Extract JSON from response (handle markdown code blocks)
                json_str = content.strip()
                if json_str.startswith('```'):
                    json_str = json_str.split('```')[1]
                    if json_str.startswith('json'):
                        json_str = json_str[4:]
                json_str = json_str.strip()
                
                parsed = json.loads(json_str)
                
                found = parsed.get('found', False)
                
                if found:
                    result = {
                        'success': True,
                        'found': True,
                        'coordinates': {
                            'x': parsed.get('x'),
                            'y': parsed.get('y')
                        },
                        'confidence': parsed.get('confidence', 0.5),
                        'description': parsed.get('description', ''),
                        'timestamp': datetime.now().isoformat()
                    }
                else:
                    result = {
                        'success': True,
                        'found': False,
                        'coordinates': None,
                        'confidence': 0.0,
                        'description': f"Could not find '{description}' on screen",
                        'timestamp': datetime.now().isoformat()
                    }
                    
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                # Fallback: couldn't parse response
                result = {
                    'success': False,
                    'found': False,
                    'coordinates': None,
                    'error': f'Failed to parse vision response: {str(e)}',
                    'raw_response': content
                }
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'found': False,
                'coordinates': None,
                'error': str(e)
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
