"""
tools/registry.py — Backward compatibility shim

This module re-exports everything from tool_registry.py for backward compatibility.
New code should import directly from tool_registry.py.
"""

# Re-export everything from the consolidated registry
from .tool_registry import (
    ToolRegistry,
    TOOL_HINTS,
    get_registry,
    register_tool,
    get_tool,
    execute_tool,
    tool_exists,
    get_all_schemas,
    filter_tools,
    get_filtered_schemas,
)

# For backward compatibility, also expose the old global _registry variable
from .tool_registry import _registry

__all__ = [
    'ToolRegistry',
    'TOOL_HINTS',
    'get_registry',
    'register_tool',
    'get_tool',
    'execute_tool',
    'tool_exists',
    'get_all_schemas',
    'filter_tools',
    'get_filtered_schemas',
    '_registry',
]
