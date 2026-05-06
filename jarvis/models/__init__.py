"""
JARVIS Models - Ollama client, model routing, and adapter layer.
"""

from .ollama_client import OllamaClient, get_ollama_client
from .router import ModelRouter, get_model_router
from .model_adapter import (
    ModelResponse,
    BaseModelAdapter,
    GPTOSSAdapter,
    Gemma3Adapter,
    ModelAdapterFactory,
    get_model_adapter,
    get_reasoning_model,
    get_vision_model,
    initialize_all_adapters,
)

__all__ = [
    'OllamaClient',
    'get_ollama_client',
    'ModelRouter',
    'get_model_router',
    'ModelResponse',
    'BaseModelAdapter',
    'GPTOSSAdapter',
    'Gemma3Adapter',
    'ModelAdapterFactory',
    'get_model_adapter',
    'get_reasoning_model',
    'get_vision_model',
    'initialize_all_adapters',
]