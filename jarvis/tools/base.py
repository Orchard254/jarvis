"""
JARVIS Tools Base - Backward compatibility module.

This module provides backward compatibility for code that imports from jarvis.tools.base.
It re-exports necessary base classes for legacy compatibility.
"""

from dataclasses import dataclass
from typing import Any, Optional, Dict

@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'success': self.success,
            'result': self.result,
            'error': self.error
        }


class BaseTool:
    """Base class for tools (legacy compatibility)."""
    
    name: str = "base_tool"
    description: str = "Base tool class"
    
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool."""
        raise NotImplementedError("Subclasses must implement execute()")


__all__ = [
    'ToolResult',
    'BaseTool'
]
