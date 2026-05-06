"""
JARVIS Tools Registry - Backward compatibility module.

This module provides backward compatibility for code that imports from jarvis.tools.registry.
It re-exports the CapabilityRegistry as ToolRegistry for legacy compatibility.
"""

from jarvis.capabilities.registry import (
    CapabilityRegistry as ToolRegistry,
    get_registry,
    initialize_registry
)

# Also provide get_instance method for backward compatibility
def get_tool_registry():
    """Get the global tool registry instance."""
    return get_registry()

__all__ = [
    'ToolRegistry',
    'get_registry', 
    'initialize_registry',
    'get_tool_registry'
]
