"""
intent_router: Classifies user command → tool routing

Uses GPT-OSS 120B to analyze natural language input and determine
which capability should handle the request.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Any
import time

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent: str
    confidence: float
    target_capability: Optional[str] = None
    parameters: dict = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class IntentRouter:
    """
    Routes user commands to appropriate capabilities using intent classification.
    
    This is the entry point for all user interactions. It analyzes natural
    language input and determines which capability should handle the request.
    """
    
    def __init__(self, reasoning_model=None):
        """
        Initialize the IntentRouter.
        
        Args:
            reasoning_model: GPT-OSS 120B model instance for classification
        """
        self.reasoning_model = reasoning_model
        self._intent_map = {}
        self._setup_default_mappings()
    
    def _setup_default_mappings(self):
        """Set up default intent to capability mappings."""
        self._intent_map = {
            "launch_application": "process_manager",
            "close_application": "process_manager",
            "search_information": "web_search",
            "create_content": "file_writer",
            "read_content": "file_reader",
            "execute_command": "run_terminal_command",
            "capture_screen": "screen_capture",
            "analyze_image": "vision_analyzer",
            "extract_text": "ocr_extract_text",
            "manage_window": "window_manager",
            "system_status": "system_info",
            "store_memory": "memory_manager",
            "retrieve_memory": "memory_manager",
        }
    
    def execute(self, user_input: str, context: Optional[dict] = None,
                **kwargs) -> dict:
        """
        Execute intent classification.
        
        Args:
            user_input: The natural language command from user
            context: Optional context about current state
            
        Returns:
            Classification result with intent, confidence, and target capability
        """
        try:
            result = self.classify(user_input, context)
            return {
                "success": True,
                "output": {
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "target_capability": result.target_capability,
                    "parameters": result.parameters
                }
            }
        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return {"success": False, "error": str(e)}
    
    def classify(self, user_input: str, context: Optional[dict] = None) -> IntentResult:
        """
        Classify user input into an intent and route to appropriate capability.
        
        Args:
            user_input: The natural language command from user
            context: Optional context about current state
            
        Returns:
            IntentResult with classified intent and target capability
        """
        logger.info(f"Classifying intent: {user_input[:50]}...")
        
        # Use reasoning model if available
        if self.reasoning_model:
            result = self._classify_with_model(user_input, context)
        else:
            # Fallback to rule-based classification
            result = self._classify_rule_based(user_input, context)
        
        # Map intent to capability
        target_capability = self._intent_map.get(result.intent)
        result.target_capability = target_capability
        
        logger.info(f"Classified as '{result.intent}' → {target_capability}")
        return result
    
    def _classify_with_model(self, user_input: str, context: Optional[dict]) -> IntentResult:
        """
        Classify using GPT-OSS 120B model.
        
        Args:
            user_input: User's natural language input
            context: Optional context information
            
        Returns:
            IntentResult from model inference
        """
        # Construct prompt for the reasoning model
        prompt = self._build_classification_prompt(user_input, context)
        
        # TODO: Replace with actual model call
        # response = self.reasoning_model.generate(prompt)
        # return self._parse_model_response(response)
        
        # Placeholder - will be replaced by actual model inference
        logger.debug("Using model-based classification (placeholder)")
        return IntentResult(
            intent="general_query",
            confidence=0.9,
            parameters={"raw_input": user_input}
        )
    
    def _classify_rule_based(self, user_input: str, context: Optional[dict]) -> IntentResult:
        """
        Fallback rule-based classification.
        
        Args:
            user_input: User's natural language input
            context: Optional context information
            
        Returns:
            IntentResult based on keyword matching
        """
        text_lower = user_input.lower()
        
        # Application control
        if any(word in text_lower for word in ["open", "launch", "start"]):
            if any(word in text_lower for word in ["app", "program", "application"]):
                return IntentResult(intent="launch_application", confidence=0.85)
            return IntentResult(intent="launch_application", confidence=0.75)
        
        if any(word in text_lower for word in ["close", "quit", "exit", "kill"]):
            return IntentResult(intent="close_application", confidence=0.85)
        
        # Search operations
        if any(word in text_lower for word in ["search", "find", "look up", "google"]):
            return IntentResult(intent="search_information", confidence=0.9)
        
        # File operations
        if any(word in text_lower for word in ["write", "create", "save", "store"]):
            return IntentResult(intent="create_content", confidence=0.8)
        
        if any(word in text_lower for word in ["read", "open file", "show me"]):
            return IntentResult(intent="read_content", confidence=0.8)
        
        # Terminal commands
        if any(word in text_lower for word in ["run command", "execute", "terminal", "shell"]):
            return IntentResult(intent="execute_command", confidence=0.9)
        
        # Screen/Vision operations
        if any(word in text_lower for word in ["screenshot", "capture screen", "show screen"]):
            return IntentResult(intent="capture_screen", confidence=0.95)
        
        if any(word in text_lower for word in ["what do you see", "analyze this", "what's on screen"]):
            return IntentResult(intent="analyze_image", confidence=0.85)
        
        if any(word in text_lower for word in ["read text", "extract text", "ocr"]):
            return IntentResult(intent="extract_text", confidence=0.9)
        
        # Window management
        if any(word in text_lower for word in ["minimize", "maximize", "resize", "move window"]):
            return IntentResult(intent="manage_window", confidence=0.85)
        
        # System info
        if any(word in text_lower for word in ["status", "system info", "cpu", "memory", "disk"]):
            return IntentResult(intent="system_status", confidence=0.9)
        
        # Memory operations
        if any(word in text_lower for word in ["remember", "save this", "note this"]):
            return IntentResult(intent="store_memory", confidence=0.85)
        
        if any(word in text_lower for word in ["recall", "what did", "remember when"]):
            return IntentResult(intent="retrieve_memory", confidence=0.85)
        
        # Default
        return IntentResult(intent="general_query", confidence=0.5, parameters={"raw_input": user_input})
    
    def _build_classification_prompt(self, user_input: str, context: Optional[dict]) -> str:
        """Build prompt for GPT-OSS 120B classification."""
        available_capabilities = list(self._intent_map.values())
        
        prompt = f"""You are an intent classifier for JARVIS, a desktop assistant.
Available capabilities: {', '.join(available_capabilities)}

Classify the following user input into one of these intents:
- launch_application: Open/start an application
- close_application: Close/quit an application  
- search_information: Search for information online
- create_content: Write/create/save content
- read_content: Read/open files
- execute_command: Run terminal/shell commands
- capture_screen: Take screenshots
- analyze_image: Analyze visual content
- extract_text: Extract text from images (OCR)
- manage_window: Control window states
- system_status: Get system information
- store_memory: Save information to memory
- retrieve_memory: Recall information from memory
- general_query: Other queries

User input: "{user_input}"
{"Context: " + str(context) if context else ""}

Respond with JSON: {{"intent": "<intent_name>", "confidence": <0-1>, "parameters": {{}}}}"""
        
        return prompt
    
    def _parse_model_response(self, response: str) -> IntentResult:
        """Parse model response into IntentResult."""
        import json
        try:
            # Extract JSON from response
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return IntentResult(
                    intent=data.get('intent', 'general_query'),
                    confidence=data.get('confidence', 0.5),
                    parameters=data.get('parameters', {})
                )
        except Exception as e:
            logger.warning(f"Failed to parse model response: {e}")
        
        return IntentResult(intent="general_query", confidence=0.5)
    
    def register_intent_mapping(self, intent: str, capability: str):
        """Register mapping between intent and capability."""
        self._intent_map[intent] = capability
        logger.debug(f"Registered mapping: {intent} → {capability}")
    
    def get_intent_map(self) -> dict:
        """Get current intent to capability mappings."""
        return self._intent_map.copy()


# Singleton instance
_intent_router_instance = None


def get_intent_router(reasoning_model=None) -> IntentRouter:
    """Get or create IntentRouter singleton."""
    global _intent_router_instance
    if _intent_router_instance is None:
        _intent_router_instance = IntentRouter(reasoning_model)
    return _intent_router_instance
