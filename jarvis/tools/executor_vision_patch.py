"""
jarvis/tools/executor_vision_patch.py — Vision Tool Execution Patch

This patch updates the executor to:
1. Route all vision.* tool calls through vision_call() gateway
2. Validate structured outputs before passing to next step
3. Implement retry logic for low-confidence results (< 0.7)
"""

import logging
from typing import Dict, Any, Optional
from .base import ToolResult

log = logging.getLogger("vision_executor_patch")


class VisionExecutionHandler:
    """
    Handler for vision tool execution with validation and retry logic.
    """
    
    CONFIDENCE_THRESHOLD = 0.7
    MAX_RETRIES = 1
    
    def __init__(self):
        self._retry_count = 0
    
    def execute_with_validation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        base64_image: Optional[str] = None
    ) -> ToolResult:
        """
        Execute vision tool with output validation and retry logic.
        
        Args:
            tool_name: Vision tool name (vision.detect_elements, etc.)
            arguments: Tool arguments
            base64_image: Optional pre-captured image (for retries)
            
        Returns:
            ToolResult with validated output
        """
        from ..perception.vision import vision_call
        
        # Map tool names to vision tasks
        TASK_MAP = {
            "vision.detect_elements": "detect_elements",
            "vision.read_text": "read_text",
            "vision.describe_scene": "describe_scene"
        }
        
        if tool_name not in TASK_MAP:
            return ToolResult.fail(error=f"Unknown vision tool: {tool_name}")
        
        task = TASK_MAP[tool_name]
        query = arguments.get("query")
        
        try:
            # Capture image if not provided
            if base64_image is None:
                capture_result = self._capture_screen()
                if not capture_result["success"]:
                    return ToolResult.fail(error=capture_result["error"])
                base64_image = capture_result["image_base64"]
            
            # Call vision gateway
            result = vision_call(base64_image, task, query=query)
            
            if not result["success"]:
                return ToolResult.fail(error=result.get("error", "Vision call failed"))
            
            # Validate output structure
            validated = self._validate_output(result["result"], task)
            
            if not validated["valid"]:
                return ToolResult.fail(error=validated["error"])
            
            # Check confidence for detect_elements
            if task == "detect_elements":
                confidence_check = self._check_confidence(validated["data"])
                if not confidence_check["passes"]:
                    # Retry with region capture if available
                    if self._retry_count < self.MAX_RETRIES:
                        self._retry_count += 1
                        log.warning(f"Low confidence ({confidence_check['max_conf']}), retrying...")
                        return self.execute_with_validation(tool_name, arguments, base64_image)
                    
                    # Return with warning instead of failing
                    log.warning(f"Returning low-confidence result: {confidence_check['max_conf']}")
            
            self._retry_count = 0  # Reset on success
            
            return ToolResult.ok(validated["data"])
            
        except Exception as e:
            log.error(f"Vision execution failed: {e}")
            return ToolResult.fail(error=str(e))
    
    def _capture_screen(self) -> Dict[str, Any]:
        """Capture screen and return base64."""
        try:
            import mss
            from PIL import Image
            import io
            import base64
            
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                
                img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
                
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                return {"success": True, "image_base64": img_base64}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _validate_output(self, data: Dict[str, Any], task: str) -> Dict[str, Any]:
        """Validate output matches expected schema."""
        if task == "detect_elements":
            if "elements" not in data:
                return {"valid": False, "error": "Missing 'elements' field"}
            if not isinstance(data["elements"], list):
                return {"valid": False, "error": "'elements' must be a list"}
            for elem in data["elements"]:
                required = ["label", "x", "y", "confidence"]
                if not all(k in elem for k in required):
                    return {"valid": False, "error": f"Element missing required fields: {required}"}
            return {"valid": True, "data": data}
        
        elif task == "read_text":
            if "text" not in data:
                return {"valid": False, "error": "Missing 'text' field"}
            if not isinstance(data["text"], str):
                return {"valid": False, "error": "'text' must be a string"}
            return {"valid": True, "data": data}
        
        elif task == "describe_scene":
            if "summary" not in data:
                return {"valid": False, "error": "Missing 'summary' field"}
            if not isinstance(data["summary"], str):
                return {"valid": False, "error": "'summary' must be a string"}
            return {"valid": True, "data": data}
        
        return {"valid": False, "error": f"Unknown task: {task}"}
    
    def _check_confidence(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check if element detection confidence meets threshold."""
        elements = data.get("elements", [])
        if not elements:
            return {"passes": True, "max_conf": 0.0}
        
        max_conf = max(e.get("confidence", 0) for e in elements)
        passes = max_conf >= self.CONFIDENCE_THRESHOLD
        
        return {"passes": passes, "max_conf": max_conf}


# Singleton instance
_handler: Optional[VisionExecutionHandler] = None


def get_vision_handler() -> VisionExecutionHandler:
    """Get the vision execution handler."""
    global _handler
    if _handler is None:
        _handler = VisionExecutionHandler()
    return _handler


def execute_vision_tool(tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
    """Execute a vision tool with validation."""
    return get_vision_handler().execute_with_validation(tool_name, arguments)
