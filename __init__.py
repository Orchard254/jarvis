"""
JARVIS - Autonomous Windows Desktop AI Agent

A production-grade AI agent that controls Windows through voice commands,
using Ollama cloud LLM for reasoning, Kokoro for TTS, and Google STT.
"""

__version__ = '2.0.0'
__author__ = 'JARVIS Team'

# Lazy imports to avoid circular dependencies
def __getattr__(name):
    if name == 'Orchestrator':
        from core.orchestrator import Orchestrator
        return Orchestrator
    elif name == 'get_config':
        from config.config import get_config
        return get_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ['Orchestrator', 'get_config']
