"""
tools/registry.py — Tool registry and loader

Single source of truth for all available tools.
Provides validation that tool names exist before execution.
"""

import importlib
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Type

from .base import BaseTool, ToolResult

log = logging.getLogger("tool_registry")


class ToolRegistry:
    """
    Central registry for all JARVIS tools.
    
    Features:
    - Single source of truth for available tools
    - Automatic tool discovery from module structure
    - Validation of tool names before execution
    - Schema generation for LLM function calling
    """
    
    _instance: Optional["ToolRegistry"] = None
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._loaded_modules: set = set()
    
    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance
    
    def register(self, tool: BaseTool) -> None:
        """
        Register a tool instance.
        
        Args:
            tool: Tool instance to register
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Expected BaseTool instance, got {type(tool)}")
        
        self._tools[tool.name] = tool
        log.debug(f"Registered tool: {tool.name}")
    
    def register_class(self, tool_class: Type[BaseTool]) -> None:
        """
        Register a tool class (instantiates it).
        
        Args:
            tool_class: Tool class to instantiate and register
        """
        if not issubclass(tool_class, BaseTool):
            raise TypeError(f"Expected BaseTool subclass, got {tool_class}")
        
        tool = tool_class()
        self.register(tool)
    
    def get(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)
    
    def has_tool(self, name: str) -> bool:
        """Check if a tool exists in the registry."""
        return name in self._tools
    
    def execute(self, name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name.
        
        Args:
            name: Tool name
            **kwargs: Tool parameters
            
        Returns:
            ToolResult from execution
        """
        tool = self.get(name)
        
        if tool is None:
            return ToolResult.fail(
                error=f"Unknown tool: '{name}'. Available tools: {', '.join(sorted(self._tools.keys()))}",
                exit_code=-2,
            )
        
        # Validate parameters first
        is_valid, error_msg = tool.validate(**kwargs)
        if not is_valid:
            return ToolResult.fail(error=error_msg, exit_code=-1)
        
        # Execute the tool
        result = tool.execute(**kwargs)
        result.tool_name = name
        result.parameters = kwargs
        
        return result
    
    def get_all_tools(self) -> Dict[str, BaseTool]:
        """Get all registered tools."""
        return dict(self._tools)
    
    def get_tool_names(self) -> List[str]:
        """Get list of all tool names."""
        return list(self._tools.keys())
    
    def get_schemas(self) -> List[dict]:
        """Get Ollama function calling schemas for all tools."""
        return [tool.get_schema() for tool in self._tools.values()]
    
    def get_all_schemas(self) -> List[dict]:
        """Get Ollama function calling schemas for all tools (alias for get_schemas)."""
        return self.get_schemas()
    
    def get_schema_for_tool(self, name: str) -> Optional[dict]:
        """Get schema for a specific tool."""
        tool = self.get(name)
        return tool.get_schema() if tool else None
    
    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self._loaded_modules.clear()
    
    def load_from_module(self, module_path: str) -> int:
        """
        Auto-discover and register tools from a module.
        
        Looks for classes ending with 'Tool' that inherit from BaseTool.
        
        Args:
            module_path: Python module path (e.g., 'tools.system.power')
            
        Returns:
            Number of tools registered
        """
        if module_path in self._loaded_modules:
            log.debug(f"Module already loaded: {module_path}")
            return 0
        
        try:
            module = importlib.import_module(module_path)
            count = 0
            
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                
                # Check if it's a class ending with 'Tool' and subclass of BaseTool
                if (isinstance(attr, type) and 
                    attr_name.endswith('Tool') and 
                    issubclass(attr, BaseTool) and
                    attr != BaseTool):
                    
                    self.register_class(attr)
                    count += 1
            
            self._loaded_modules.add(module_path)
            log.info(f"Loaded {count} tools from {module_path}")
            return count
            
        except Exception as e:
            log.error(f"Failed to load module {module_path}: {e}")
            return 0
    
    def load_all_tools(self, base_dir: Optional[str] = None) -> int:
        """
        Auto-discover and load all tools from the tools directory structure.
        
        Args:
            base_dir: Base directory to search (defaults to this file's parent)
            
        Returns:
            Total number of tools registered
        """
        if base_dir is None:
            base_dir = Path(__file__).parent
        
        total = 0
        
        # Map of category folders to module prefixes - use jarvis.tools prefix for proper imports
        categories = {
            "system": "jarvis.tools.system",
            "apps": "jarvis.tools.apps",
            "audio": "jarvis.tools.audio",
            "files": "jarvis.tools.files",
            "network": "jarvis.tools.network",
            "screen": "jarvis.tools.screen",
            "input": "jarvis.tools.input",
            "web": "jarvis.tools.web",
            "time": "jarvis.tools.time",
            "settings": "jarvis.tools.settings",
            "tasks": "jarvis.tools.tasks",
            "scripts": "jarvis.tools.scripts",
            "data": "jarvis.tools.data",
        }
        
        for category, prefix in categories.items():
            category_dir = base_dir / category
            if not category_dir.exists():
                continue
            
            for file in category_dir.glob("*.py"):
                if file.name.startswith("_"):
                    continue
                
                module_name = file.stem
                module_path = f"{prefix}.{module_name}"
                total += self.load_from_module(module_path)
        
        log.info(f"Total tools loaded: {total}")
        return total
    
    def validate_tool_name(self, name: str) -> tuple[bool, str]:
        """
        Validate that a tool name exists in the registry.
        
        Args:
            name: Tool name to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if name in self._tools:
            return True, ""
        
        # Provide helpful error message with similar tool names
        available = sorted(self._tools.keys())
        error = f"Unknown tool: '{name}'"
        
        if available:
            # Suggest similar names using simple string matching
            similar = [t for t in available if name.lower() in t.lower() or t.lower() in name.lower()]
            if similar:
                error += f". Did you mean: {', '.join(similar[:3])}?"
            error += f". Available tools: {', '.join(available[:10])}"
            if len(available) > 10:
                error += f"... ({len(available)} total)"
        
        return False, error


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry.get_instance()
    return _registry


def register_tool(tool: BaseTool) -> None:
    """Register a tool in the global registry."""
    get_registry().register(tool)


def get_tool(name: str) -> Optional[BaseTool]:
    """Get a tool from the global registry."""
    return get_registry().get(name)


def execute_tool(name: str, **kwargs) -> ToolResult:
    """Execute a tool from the global registry."""
    return get_registry().execute(name, **kwargs)


def tool_exists(name: str) -> bool:
    """Check if a tool exists in the global registry."""
    return get_registry().has_tool(name)


def get_all_schemas() -> List[dict]:
    """Get all tool schemas for LLM function calling."""
    return get_registry().get_schemas()
