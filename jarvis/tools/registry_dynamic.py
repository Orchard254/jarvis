"""
Tool Registry with Dynamic Discovery and Loading.
Supports auto-discovery of tools from directories and runtime tool generation.
"""

import importlib
import logging
import os
import pkgutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Type
from dataclasses import dataclass

from jarvis.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """Metadata about a registered tool."""
    name: str
    class_name: str
    module_path: str
    category: str
    description: str
    parameters: Dict[str, Any]
    is_dynamic: bool = False


class ToolRegistry:
    """
    Central registry for all tools with dynamic discovery capabilities.
    
    Features:
    - Auto-discovery of tools from package directories
    - Runtime registration of dynamically generated tools
    - Category-based filtering
    - Lazy loading for performance
    """
    
    _instance: Optional['ToolRegistry'] = None
    
    def __new__(cls):
        """Singleton pattern to ensure single registry instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._tools: Dict[str, Type[BaseTool]] = {}
        self._tool_info: Dict[str, ToolInfo] = {}
        self._categories: Dict[str, List[str]] = {}
        self._dynamic_tools: Dict[str, Type[BaseTool]] = {}
        self._initialized = True
        
        logger.info("ToolRegistry initialized")
    
    def discover_tools(self, package_name: str = "jarvis.tools"):
        """
        Auto-discover all tools in a package directory.
        
        Args:
            package_name: Root package to scan for tools
        """
        try:
            package = importlib.import_module(package_name)
            package_path = Path(package.__path__[0])
            
            logger.info(f"Discovering tools in {package_name} at {package_path}")
            
            # Walk through all subdirectories
            for root, dirs, files in os.walk(package_path):
                # Skip __pycache__ and hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('_') and d != '__pycache__']
                
                for file in files:
                    if file.endswith('.py') and file not in ('__init__.py', 'base.py', 'registry.py', 'registry_dynamic.py', 'executor.py'):
                        file_path = Path(root) / file
                        
                        # Calculate module path - use absolute path approach
                        rel_path = file_path.relative_to(package_path.parent)
                        module_parts = list(rel_path.parts)
                        module_parts[-1] = module_parts[-1][:-3]  # Remove .py
                        module_path = '.'.join(module_parts)
                        
                        try:
                            module = importlib.import_module(module_path)
                            
                            # Find all BaseTool subclasses in module
                            for attr_name in dir(module):
                                attr = getattr(module, attr_name)
                                
                                if (isinstance(attr, type) and 
                                    issubclass(attr, BaseTool) and 
                                    attr != BaseTool and
                                    hasattr(attr, 'name') and
                                    attr.name != 'base_tool'):
                                    
                                    self._register_tool_class(attr, module_path, is_dynamic=False)
                                    logger.debug(f"Discovered tool: {attr.name} from {module_path}")
                                    
                        except Exception as e:
                            logger.warning(f"Failed to load tool from {module_path}: {e}")
                            
        except Exception as e:
            logger.error(f"Tool discovery failed for {package_name}: {e}")
    
    def _register_tool_class(self, tool_class: Type[BaseTool], module_path: str, is_dynamic: bool = False):
        """
        Register a tool class in the registry.
        
        Args:
            tool_class: The tool class to register
            module_path: Path to the module containing the tool
            is_dynamic: Whether this is a dynamically generated tool
        """
        tool_name = tool_class.name
        
        self._tools[tool_name] = tool_class
        self._tool_info[tool_name] = ToolInfo(
            name=tool_name,
            class_name=tool_class.__name__,
            module_path=module_path,
            category=getattr(tool_class, 'category', 'general'),
            description=getattr(tool_class, 'description', ''),
            parameters=getattr(tool_class, 'parameters', {}),
            is_dynamic=is_dynamic
        )
        
        # Index by category
        category = getattr(tool_class, 'category', 'general')
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(tool_name)
        
        if is_dynamic:
            self._dynamic_tools[tool_name] = tool_class
        
        logger.debug(f"Registered tool: {tool_name} (category: {category}, dynamic: {is_dynamic})")
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        Get an instance of a tool by name.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool instance or None if not found
        """
        tool_class = self._tools.get(tool_name)
        if tool_class:
            try:
                return tool_class()
            except Exception as e:
                logger.error(f"Failed to instantiate tool {tool_name}: {e}")
                return None
        return None
    
    def list_tools(self, category: Optional[str] = None) -> List[str]:
        """
        List all registered tools, optionally filtered by category.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of tool names
        """
        if category:
            return self._categories.get(category, [])
        return list(self._tools.keys())
    
    def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """
        Get metadata about a tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            ToolInfo or None if not found
        """
        return self._tool_info.get(tool_name)
    
    def get_categories(self) -> List[str]:
        """Get all available tool categories."""
        return list(self._categories.keys())
    
    def register_dynamic_tool(self, tool_class: Type[BaseTool]):
        """
        Register a dynamically generated tool at runtime.
        
        Args:
            tool_class: The dynamically created tool class
        """
        self._register_tool_class(tool_class, "<dynamic>", is_dynamic=True)
        logger.info(f"Registered dynamic tool: {tool_class.name}")
    
    def create_temporary_tool(
        self,
        name: str,
        description: str,
        execute_fn,
        validate_fn=None,
        category: str = "temporary",
        parameters: Dict[str, Any] = None
    ) -> BaseTool:
        """
        Create and register a temporary tool from functions.
        
        Args:
            name: Tool name
            description: Tool description
            execute_fn: Function to execute (should return ToolResult)
            validate_fn: Optional validation function
            category: Tool category
            parameters: Parameter schema
            
        Returns:
            Created tool instance
        """
        
        # Dynamically create a tool class
        def execute_method(self, **kwargs):
            try:
                result = execute_fn(**kwargs)
                if isinstance(result, ToolResult):
                    return result
                return ToolResult.ok(str(result))
            except Exception as e:
                return ToolResult.fail(str(e))
        
        def validate_method(self, **kwargs):
            if validate_fn:
                try:
                    is_valid, error = validate_fn(**kwargs)
                    return (is_valid, error)
                except Exception as e:
                    return (False, str(e))
            return (True, "")
        
        tool_class = type(
            name.capitalize() + 'Tool',
            (BaseTool,),
            {
                'name': name,
                'description': description,
                'category': category,
                'parameters': parameters or {},
                'execute': execute_method,
                'validate': validate_method,
            }
        )
        
        # Register the dynamic tool
        self.register_dynamic_tool(tool_class)
        
        # Return an instance
        return tool_class()
    
    def unregister_tool(self, tool_name: str) -> bool:
        """
        Unregister a tool (useful for temporary tools).
        
        Args:
            tool_name: Name of the tool to remove
            
        Returns:
            True if removed, False if not found
        """
        if tool_name not in self._tools:
            return False
        
        tool_info = self._tool_info.get(tool_name)
        if tool_info:
            category = tool_info.category
            if category in self._categories and tool_name in self._categories[category]:
                self._categories[category].remove(tool_name)
        
        del self._tools[tool_name]
        del self._tool_info[tool_name]
        
        if tool_name in self._dynamic_tools:
            del self._dynamic_tools[tool_name]
        
        logger.debug(f"Unregistered tool: {tool_name}")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            'total_tools': len(self._tools),
            'dynamic_tools': len(self._dynamic_tools),
            'categories': len(self._categories),
            'tools_by_category': {cat: len(tools) for cat, tools in self._categories.items()}
        }


# Global registry instance
_registry_instance: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
        _registry_instance.discover_tools()
    return _registry_instance


def reload_registry():
    """Force reload of the tool registry."""
    global _registry_instance
    _registry_instance = ToolRegistry()
    _registry_instance.discover_tools()
    return _registry_instance
