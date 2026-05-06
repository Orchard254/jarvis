"""
JARVIS Model Adapter Layer

Provides unified interface for connecting different LLM backends:
- GPT-OSS 120B (reasoning/planning tasks)
- Gemma 3 27B (vision/intent classification tasks)

This adapter layer replaces placeholder calls with actual model inference.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import json

from jarvis.models.ollama_client import OllamaClient
from jarvis.models.router import get_model_router, ModelRouter

logger = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    """Standardized response from any model."""
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "tool_calls": self.tool_calls or [],
            "confidence": self.confidence,
            "metadata": self.metadata
        }


class BaseModelAdapter(ABC):
    """Abstract base class for model adapters."""
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> ModelResponse:
        """Generate response from model."""
        pass
    
    @abstractmethod
    def generate_json(self, prompt: str, **kwargs) -> dict:
        """Generate JSON response from model."""
        pass


class GPTOSSAdapter(BaseModelAdapter):
    """
    Adapter for GPT-OSS 120B model.
    
    Optimized for:
    - Complex reasoning
    - Task planning
    - Multi-step decomposition
    - Code generation
    """
    
    def __init__(self, client: Optional[OllamaClient] = None, model_name: str = None):
        """
        Initialize GPT-OSS 120B adapter.
        
        Args:
            client: Pre-configured OllamaClient instance
            model_name: Model identifier (defaults to settings.LLM_MODEL)
        """
        from settings import LLM_MODEL, OLLAMA_CLOUD_URL, OLLAMA_LOCAL_URL, OLLAMA_API_KEY
        
        self.model_name = model_name or LLM_MODEL
        self.client = client or OllamaClient(
            cloud_url=OLLAMA_CLOUD_URL,
            local_url=OLLAMA_LOCAL_URL,
            api_key=OLLAMA_API_KEY,
            model=self.model_name,
            timeout=300,  # Longer timeout for complex reasoning
            max_retries=3,
        )
        self.model_router = get_model_router()
        
        logger.info(f"Initialized GPT-OSS 120B adapter with model: {self.model_name}")
    
    def generate(self, prompt: str, temperature: float = 0.7, 
                 max_tokens: int = 4000, **kwargs) -> ModelResponse:
        """
        Generate response using GPT-OSS 120B.
        
        Args:
            prompt: Input prompt text
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            ModelResponse with generated content
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            
            # Use planning config for complex tasks
            task_type = kwargs.get("task_type", "reasoning")
            result = self.client.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            return ModelResponse(
                content=result.get("content", ""),
                tool_calls=result.get("tool_calls"),
                metadata={
                    "model": self.model_name,
                    "endpoint": result.get("endpoint"),
                    "done": result.get("done", True)
                }
            )
        except Exception as e:
            logger.error(f"GPT-OSS 120B generation failed: {e}")
            raise
    
    def generate_json(self, prompt: str, **kwargs) -> dict:
        """
        Generate JSON response using GPT-OSS 120B.
        
        Args:
            prompt: Input prompt requesting JSON output
            
        Returns:
            Parsed JSON dictionary
        """
        # Add instruction to output JSON
        enhanced_prompt = f"{prompt}\n\nRespond with valid JSON only."
        response = self.generate(enhanced_prompt, **kwargs)
        
        # Parse JSON from response
        return self._parse_json_response(response.content)
    
    def _parse_json_response(self, content: str) -> dict:
        """Extract and parse JSON from model response."""
        try:
            # Try direct parsing first
            return json.loads(content.strip())
        except json.JSONDecodeError:
            # Extract JSON block from response
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                return json.loads(json_str)
            raise ValueError("No valid JSON found in response")


class Gemma3Adapter(BaseModelAdapter):
    """
    Adapter for Gemma 3 27B model.
    
    Optimized for:
    - Intent classification
    - Vision tasks
    - Quick responses
    - Classification tasks
    """
    
    def __init__(self, client: Optional[OllamaClient] = None, model_name: str = None):
        """
        Initialize Gemma 3 27B adapter.
        
        Args:
            client: Pre-configured OllamaClient instance
            model_name: Model identifier (defaults to settings.OLLAMA_VISION_MODEL)
        """
        from settings import OLLAMA_VISION_MODEL, OLLAMA_CLOUD_URL, OLLAMA_LOCAL_URL, OLLAMA_API_KEY
        
        self.model_name = model_name or OLLAMA_VISION_MODEL
        self.client = client or OllamaClient(
            cloud_url=OLLAMA_CLOUD_URL,
            local_url=OLLAMA_LOCAL_URL,
            api_key=OLLAMA_API_KEY,
            model=self.model_name,
            timeout=180,
            max_retries=3,
        )
        self.model_router = get_model_router()
        
        logger.info(f"Initialized Gemma 3 27B adapter with model: {self.model_name}")
    
    def generate(self, prompt: str, temperature: float = 0.5,
                 max_tokens: int = 2000, **kwargs) -> ModelResponse:
        """
        Generate response using Gemma 3 27B.
        
        Args:
            prompt: Input prompt text
            temperature: Sampling temperature (lower for classification)
            max_tokens: Maximum tokens to generate
            
        Returns:
            ModelResponse with generated content
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            
            # Use fast config for quick responses
            task_type = kwargs.get("task_type", "fast")
            result = self.client.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            return ModelResponse(
                content=result.get("content", ""),
                tool_calls=result.get("tool_calls"),
                metadata={
                    "model": self.model_name,
                    "endpoint": result.get("endpoint"),
                    "done": result.get("done", True)
                }
            )
        except Exception as e:
            logger.error(f"Gemma 3 27B generation failed: {e}")
            raise
    
    def generate_json(self, prompt: str, **kwargs) -> dict:
        """
        Generate JSON response using Gemma 3 27B.
        
        Ideal for intent classification and structured outputs.
        
        Args:
            prompt: Input prompt requesting JSON output
            
        Returns:
            Parsed JSON dictionary
        """
        enhanced_prompt = f"{prompt}\n\nRespond with valid JSON only."
        response = self.generate(enhanced_prompt, temperature=0.3, **kwargs)
        return self._parse_json_response(response.content)
    
    def classify(self, prompt: str, categories: List[str], **kwargs) -> tuple[str, float]:
        """
        Perform classification using Gemma 3 27B.
        
        Args:
            prompt: Input to classify
            categories: List of possible categories/intents
            
        Returns:
            Tuple of (category, confidence_score)
        """
        classification_prompt = f"""Classify the following input into one of these categories: {', '.join(categories)}

Input: {prompt}

Respond with JSON: {{"category": "<category_name>", "confidence": <0-1>}}"""
        
        result = self.generate_json(classification_prompt, **kwargs)
        return (
            result.get("category", categories[0]),
            result.get("confidence", 0.5)
        )
    
    def _parse_json_response(self, content: str) -> dict:
        """Extract and parse JSON from model response."""
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                return json.loads(json_str)
            raise ValueError("No valid JSON found in response")


class ModelAdapterFactory:
    """
    Factory for creating and managing model adapters.
    
    Provides centralized access to all model instances with proper configuration.
    """
    
    _instance = None
    _adapters: Dict[str, BaseModelAdapter] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_adapter(self, model_type: str) -> BaseModelAdapter:
        """
        Get or create adapter for specified model type.
        
        Args:
            model_type: One of 'gpt_oss_120b', 'gemma3_27b'
            
        Returns:
            Configured model adapter instance
        """
        if model_type not in self._adapters:
            if model_type == "gpt_oss_120b":
                self._adapters[model_type] = GPTOSSAdapter()
            elif model_type == "gemma3_27b":
                self._adapters[model_type] = Gemma3Adapter()
            else:
                raise ValueError(f"Unknown model type: {model_type}")
        
        return self._adapters[model_type]
    
    def get_reasoning_adapter(self) -> GPTOSSAdapter:
        """Get GPT-OSS 120B adapter for reasoning tasks."""
        return self.get_adapter("gpt_oss_120b")
    
    def get_vision_adapter(self) -> Gemma3Adapter:
        """Get Gemma 3 27B adapter for vision/classification tasks."""
        return self.get_adapter("gemma3_27b")
    
    def list_adapters(self) -> List[str]:
        """List available model types."""
        return ["gpt_oss_120b", "gemma3_27b"]


# Global factory instance
_adapter_factory: Optional[ModelAdapterFactory] = None


def get_model_adapter(model_type: str = "gpt_oss_120b") -> BaseModelAdapter:
    """
    Get model adapter for specified type.
    
    Args:
        model_type: One of 'gpt_oss_120b', 'gemma3_27b'
        
    Returns:
        Configured model adapter
    """
    global _adapter_factory
    if _adapter_factory is None:
        _adapter_factory = ModelAdapterFactory()
    return _adapter_factory.get_adapter(model_type)


def get_reasoning_model() -> GPTOSSAdapter:
    """Get GPT-OSS 120B adapter for reasoning/planning."""
    return get_model_adapter("gpt_oss_120b")


def get_vision_model() -> Gemma3Adapter:
    """Get Gemma 3 27B adapter for vision/classification."""
    return get_model_adapter("gemma3_27b")


def initialize_all_adapters() -> Dict[str, BaseModelAdapter]:
    """
    Initialize all model adapters.
    
    Returns:
        Dictionary of initialized adapters
    """
    factory = ModelAdapterFactory()
    adapters = {}
    for model_type in factory.list_adapters():
        adapters[model_type] = factory.get_adapter(model_type)
    logger.info(f"Initialized {len(adapters)} model adapters")
    return adapters
