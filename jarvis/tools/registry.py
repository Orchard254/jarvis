"""
Legacy Tool Registry Compatibility Module

This module provides a ToolRegistry class that wraps the new CapabilityRegistry
for backward compatibility with code that expects the old registry interface.
"""

import logging
from typing import Dict, List, Any, Optional, Callable

from jarvis.capabilities.registry import CapabilityRegistry, get_registry, initialize_registry

logger = logging.getLogger(__name__)


class ToolStatus:
    """Simple status enum replacement to avoid circular imports."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    TIMEOUT = "timeout"


class SimpleToolResult:
    """Simple result class to avoid circular imports."""
    def __init__(self, success: bool, output=None, error=None, metadata=None, status=None):
        self.success = success
        self.output = output
        self.error = error
        self.metadata = metadata or {}
        self.status = status or (ToolStatus.SUCCESS if success else ToolStatus.ERROR)
    
    @classmethod
    def ok(cls, output, metadata=None):
        return cls(success=True, output=output, metadata=metadata)
    
    @classmethod
    def fail(cls, error, output=None):
        return cls(success=False, error=error, output=output)
    
    def to_dict(self):
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
            "status": self.status
        }


class SimpleBaseTool:
    """Minimal base tool class to avoid circular imports."""
    name = "base_tool"
    description = "Base tool class"
    category = "general"
    
    def __init__(self, config=None):
        self.config = config or {}
        self._enabled = True
    
    @property
    def enabled(self):
        return self._enabled
    
    def execute(self, **kwargs):
        raise NotImplementedError("Subclasses must implement execute()")
    
    def get_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        }


class ToolRegistry:
    """
    Legacy-compatible tool registry that wraps CapabilityRegistry.
    
    Provides the same interface as the old ToolRegistry for backward
    compatibility while using the new capability system underneath.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the ToolRegistry.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._capability_registry = CapabilityRegistry(config)
        self._tools: Dict[str, SimpleBaseTool] = {}
        self._initialized = False
        
        logger.info("ToolRegistry initialized (compatibility mode)")
    
    def initialize(self, reasoning_model=None, vision_model=None) -> None:
        """
        Initialize all tools/capabilities.
        
        Args:
            reasoning_model: The reasoning LLM model instance
            vision_model: The vision LLM model instance
        """
        if self._initialized:
            logger.warning("Registry already initialized")
            return
        
        self._capability_registry.initialize(
            reasoning_model=reasoning_model,
            vision_model=vision_model
        )
        self._initialized = True
        
        logger.info(f"ToolRegistry initialized with {len(self.list_tools())} tools")
    
    def register_tool(self, name: str, tool_instance: SimpleBaseTool) -> None:
        """
        Register a tool instance.
        
        Args:
            name: Tool name
            tool_instance: BaseTool subclass instance
        """
        self._tools[name] = tool_instance
        logger.debug(f"Registered tool: {name}")
    
    def unregister_tool(self, name: str) -> None:
        """
        Unregister a tool by name.
        
        Args:
            name: Tool name to remove
        """
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"Unregistered tool: {name}")
    
    def has_tool(self, name: str) -> bool:
        """
        Check if a tool is registered.
        
        Args:
            name: Tool name to check
            
        Returns:
            True if tool exists
        """
        # Check both legacy tools and capabilities
        if name in self._tools:
            return True
        # Check capability registry
        try:
            cap = self._capability_registry.get(name)
            return cap is not None
        except Exception as e:
            logger.warning(f"Error checking capability {name}: {e}")
            return False
    
    def get_tool(self, name: str) -> Optional[SimpleBaseTool]:
        """
        Get a tool instance by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool instance or None
        """
        # First check legacy tools
        if name in self._tools:
            return self._tools[name]
        
        # Try to get from capability registry
        cap = self._capability_registry.get(name)
        if cap:
            # Wrap capability in legacy tool interface
            from jarvis.tools import create_legacy_tool_wrapper
            wrapper = create_legacy_tool_wrapper(name, self._capability_registry)
            self._tools[name] = wrapper
            return wrapper
        
        return None
    
    def get_tool_names(self) -> List[str]:
        """
        Get list of all available tool names.
        
        Returns:
            List of tool names
        """
        # Combine legacy tools and capabilities
        names = set(self._tools.keys())
        
        # Add capability names
        try:
            caps = self._capability_registry.list_capabilities()
            for cap in caps:
                if cap.get("registered"):
                    names.add(cap["name"])
        except Exception as e:
            logger.warning(f"Error listing capabilities: {e}")
        
        return sorted(list(names))
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all registered tools with metadata.
        
        Returns:
            List of tool info dictionaries
        """
        result = []
        
        # Add legacy tools
        for name, tool in self._tools.items():
            result.append({
                "name": name,
                "description": getattr(tool, "description", "No description"),
                "category": getattr(tool, "category", "custom"),
                "enabled": tool.enabled
            })
        
        # Add capabilities not already in legacy tools
        try:
            caps = self._capability_registry.list_capabilities()
            for cap in caps:
                if cap["name"] not in self._tools and cap.get("registered"):
                    result.append({
                        "name": cap["name"],
                        "description": f"Capability: {cap['name']}",
                        "category": cap.get("category", "capability"),
                        "enabled": True
                    })
        except Exception as e:
            logger.warning(f"Error listing capabilities for tool registry: {e}")
        
        return result
    
    def execute_tool(self, name: str, **kwargs) -> SimpleToolResult:
        """
        Execute a tool by name.
        
        Args:
            name: Tool name
            **kwargs: Tool execution parameters
            
        Returns:
            SimpleToolResult instance
        """
        # Try legacy tools first
        if name in self._tools:
            tool = self._tools[name]
            if not tool.enabled:
                return SimpleToolResult.fail(f"Tool {name} is disabled")
            try:
                result = tool.execute(**kwargs)
                if hasattr(result, 'to_dict'):
                    return result
                return SimpleToolResult.ok(result)
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                return SimpleToolResult.fail(str(e))
        
        # Fall back to capability registry
        result = self._capability_registry.execute(name, **kwargs)
        if result.get("success"):
            return SimpleToolResult.ok(result.get("output"), result)
        else:
            return SimpleToolResult.fail(result.get("error", "Unknown error"))
    
    def get_tool_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get the function calling schema for a tool.
        
        Args:
            name: Tool name
            
        Returns:
            OpenAI-style function schema or None
        """
        tool = self.get_tool(name)
        if tool:
            return tool.get_schema()
        return None
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """
        Get schemas for all tools.
        
        Returns:
            List of function schemas
        """
        schemas = []
        for name in self.get_tool_names():
            schema = self.get_tool_schema(name)
            if schema:
                schemas.append(schema)
        return schemas
    
    @property
    def initialized(self) -> bool:
        """Check if registry is initialized."""
        return self._initialized
    
    @classmethod
    def get_instance(cls, config: Optional[Dict] = None) -> 'ToolRegistry':
        """Get or create the global ToolRegistry singleton instance."""
        global _global_registry
        if _global_registry is None:
            _global_registry = cls(config)
        return _global_registry
    
    def load_all_tools(self) -> int:
        """
        Load all tools/capabilities into the registry.
        
        Returns:
            Number of tools loaded
        """
        if not self._capability_registry._initialized:
            # Initialize capability registry if not already done
            self._capability_registry.initialize()
        
        # Refresh our internal tools dict from capabilities
        self._tools.clear()
        
        # Get all capabilities and wrap them
        caps = self._capability_registry.list_capabilities()
        for cap in caps:
            if cap.get("registered"):
                name = cap["name"]
                # Create wrapper for each capability
                from jarvis.tools import create_legacy_tool_wrapper
                try:
                    wrapper = create_legacy_tool_wrapper(name, self._capability_registry)
                    self._tools[name] = wrapper
                except Exception as e:
                    logger.warning(f"Failed to wrap capability {name}: {e}")
        
        # Also add legacy name aliases (pointing to same underlying capability wrappers)
        legacy_aliases = {
            "open_app": "window_manager",
            "close_app": "window_manager",
            "get_time": "system_info",
            "lock_pc": "shutdown_restart_control",
            "take_screenshot": "screen_capture",
            "capture_screen": "screen_capture",
            "search_web": "web_search",
            "google_search": "web_search",
            "read_file": "file_reader",
            "write_file": "file_writer",
            "create_file": "file_writer",
            "delete_file": "file_writer",
            "list_files": "file_search",
            "find_file": "file_search",
        }
        
        for alias_name, real_cap_name in legacy_aliases.items():
            if real_cap_name in self._tools:
                # Create an alias that points to the same wrapper
                self._tools[alias_name] = self._tools[real_cap_name]
        
        logger.info(f"Loaded {len(self._tools)} tools (including {len(legacy_aliases)} legacy aliases)")
        return len(self._tools)
    
    def get_all_tools(self) -> Dict[str, SimpleBaseTool]:
        """
        Get dictionary of all available tools.
        
        Returns:
            Dict mapping tool names to tool instances
        """
        # Ensure tools are loaded
        if not self._tools and self._capability_registry._initialized:
            self.load_all_tools()
        
        return self._tools.copy()
    
    def find_similar_tools(self, query: str, limit: int = 5) -> List[str]:
        """
        Find tools similar to a query string (fuzzy matching).
        
        Args:
            query: Tool name or description to search for
            limit: Maximum number of results
            
        Returns:
            List of similar tool names
        """
        import difflib
        
        all_names = self.get_tool_names()
        
        # Try exact substring match first
        matches = [name for name in all_names if query.lower() in name.lower()]
        
        if not matches:
            # Fuzzy match using difflib
            matches = difflib.get_close_matches(query.lower(), all_names, n=limit, cutoff=0.4)
        
        return matches[:limit]
    
    @property
    def tools(self) -> Dict[str, SimpleBaseTool]:
        """Property accessor for tools dictionary (backward compatibility)."""
        return self.get_all_tools()


# Global registry instance for backward compatibility
_global_registry: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    """Get or create the global ToolRegistry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def create_registry(config: Optional[Dict] = None) -> ToolRegistry:
    """Create a new ToolRegistry instance."""
    return ToolRegistry(config)
