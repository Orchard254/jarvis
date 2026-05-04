"""
models/router.py — Routes tasks to appropriate model configuration

Determines which model, temperature, and token limits to use based on task type.
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .ollama_client import OllamaClient


@dataclass
class ModelConfig:
    """Configuration for a specific model endpoint."""
    
    model: str
    temperature: float
    max_tokens: int
    timeout: int
    cloud_url: str
    local_url: str
    api_key: str = ""


# Predefined model configurations
CONFIGS = {
    "default": ModelConfig(
        model="nemotron-3-nano:30b-cloud",
        temperature=0.7,
        max_tokens=2000,
        timeout=180,
        cloud_url="https://api.ollama.com/api/chat",
        local_url="http://localhost:11434/api/chat",
    ),
    
    "fast": ModelConfig(
        model="nemotron-3-nano:30b-cloud",
        temperature=0.5,
        max_tokens=512,
        timeout=60,
        cloud_url="https://api.ollama.com/api/chat",
        local_url="http://localhost:11434/api/chat",
    ),
    
    "reasoning": ModelConfig(
        model="nemotron-3-nano:30b-cloud",
        temperature=0.7,
        max_tokens=4000,
        timeout=300,
        cloud_url="https://api.ollama.com/api/chat",
        local_url="http://localhost:11434/api/chat",
    ),
    
    "vision": ModelConfig(
        model="nemotron-3-nano:30b-cloud",
        temperature=0.5,
        max_tokens=2000,
        timeout=180,
        cloud_url="https://api.ollama.com/api/chat",
        local_url="http://localhost:11434/api/chat",
    ),
    
    "streaming": ModelConfig(
        model="nemotron-3-nano:30b-cloud",
        temperature=0.7,
        max_tokens=512,
        timeout=120,
        cloud_url="https://api.ollama.com/api/chat",
        local_url="http://localhost:11434/api/chat",
    ),
    
    "planning": ModelConfig(
        model="nemotron-3-nano:30b-cloud",
        temperature=0.6,
        max_tokens=3000,
        timeout=240,
        cloud_url="https://api.ollama.com/api/chat",
        local_url="http://localhost:11434/api/chat",
    ),
    
    "critic": ModelConfig(
        model="nemotron-3-nano:30b-cloud",
        temperature=0.4,
        max_tokens=2000,
        timeout=120,
        cloud_url="https://api.ollama.com/api/chat",
        local_url="http://localhost:11434/api/chat",
    ),
    
    "reflection": ModelConfig(
        model="nemotron-3-nano:30b-cloud",
        temperature=0.6,
        max_tokens=2500,
        timeout=180,
        cloud_url="https://api.ollama.com/api/chat",
        local_url="http://localhost:11434/api/chat",
    ),
}


def get_config(task_type: str = "default") -> ModelConfig:
    """
    Get model configuration for a task type.
    
    Args:
        task_type: One of 'default', 'fast', 'reasoning', 'vision', 
                   'streaming', 'planning', 'critic', 'reflection'
    
    Returns:
        ModelConfig for the specified task type
    """
    return CONFIGS.get(task_type, CONFIGS["default"])


def route_task(task_description: str) -> tuple[str, ModelConfig]:
    """
    Automatically route a task to the appropriate model config.
    
    Args:
        task_description: Description of what needs to be done
        
    Returns:
        Tuple of (task_type, ModelConfig)
    """
    task_lower = task_description.lower()
    
    # Vision tasks
    if any(word in task_lower for word in ["screenshot", "image", "picture", "see", "visual", "screen"]):
        return "vision", CONFIGS["vision"]
    
    # Planning tasks
    if any(word in task_lower for word in ["plan", "strategy", "steps", "decompose", "break down"]):
        return "planning", CONFIGS["planning"]
    
    # Critique/review tasks
    if any(word in task_lower for word in ["review", "critique", "validate", "check", "verify"]):
        return "critic", CONFIGS["critic"]
    
    # Reflection tasks
    if any(word in task_lower for word in ["reflect", "analyze outcome", "learn from", "improve"]):
        return "reflection", CONFIGS["reflection"]
    
    # Simple queries
    if any(word in task_lower for word in ["time", "date", "weather", "quick", "simple"]):
        return "fast", CONFIGS["fast"]
    
    # Complex reasoning
    if any(word in task_lower for word in ["complex", "difficult", "multi-step", "analyze"]):
        return "reasoning", CONFIGS["reasoning"]
    
    # Default
    return "default", CONFIGS["default"]


def create_client_for_task(task_type: str = "default"):
    """
    Create an OllamaClient configured for a specific task type.
    
    Args:
        task_type: Task type string
        
    Returns:
        Configured OllamaClient instance
    """
    from .ollama_client import OllamaClient
    
    config = get_config(task_type)
    
    return OllamaClient(
        cloud_url=config.cloud_url,
        local_url=config.local_url,
        api_key=config.api_key,
        model=config.model,
        timeout=config.timeout,
    )


class ModelRouter:
    """Routes tasks to appropriate model configurations and creates clients."""
    
    def __init__(self):
        self._client_cache: dict[str, "OllamaClient"] = {}
    
    def get_config(self, task_type: str = "default") -> ModelConfig:
        """Get model configuration for a task type."""
        return get_config(task_type)
    
    def route_task(self, task_description: str) -> tuple[str, ModelConfig]:
        """Automatically route a task to the appropriate model config."""
        return route_task(task_description)
    
    def get_client(self, task_type: str = "default") -> "OllamaClient":
        """Get or create a cached OllamaClient for a task type."""
        if task_type not in self._client_cache:
            self._client_cache[task_type] = create_client_for_task(task_type)
        return self._client_cache[task_type]
    
    def chat(self, messages: list, task_type: str = "default", **kwargs):
        """Send chat request using client configured for task type."""
        client = self.get_client(task_type)
        return client.chat(messages, **kwargs)
    
    def stream_chat(self, messages: list, task_type: str = "streaming", **kwargs):
        """Stream chat response using client configured for task type."""
        client = self.get_client(task_type)
        return client.stream_chat(messages, **kwargs)


# Global router instance
_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create global ModelRouter instance."""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
