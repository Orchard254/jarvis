"""
JARVIS Tools Module - Backward compatibility layer.

This module provides backward compatibility for code that imports from jarvis.tools.
It re-exports the CapabilityRegistry as ToolRegistry for legacy compatibility.
"""

from jarvis.capabilities.registry import (
    CapabilityRegistry as ToolRegistry,
    get_registry,
    initialize_registry
)

__all__ = [
    'ToolRegistry',
    'get_registry', 
    'initialize_registry'
]
