"""
JARVIS - Autonomous Windows Desktop AI Agent

A production-grade AI agent that controls Windows through voice commands,
using Ollama cloud LLM for reasoning, Kokoro for TTS, and Google STT.
"""

__version__ = '2.0.0'
__author__ = 'JARVIS Team'

# Import key components for easy access
from jarvis.core.orchestrator import Orchestrator
from jarvis.config.config import get_config

__all__ = ['Orchestrator', 'get_config']
