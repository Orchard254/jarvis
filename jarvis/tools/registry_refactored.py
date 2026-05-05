"""
tools/registry.py — Refactored Tool Registry with strict naming and schemas

Features:
- Strict naming convention: <domain>.<verb>_<object>
- Typed JSON schemas for every tool
- TOOL_HINTS for keyword-based filtering
- Deterministic tool selection (3-5 tools max to LLM)
"""

import importlib
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Type, Any

from .base import BaseTool, ToolResult

log = logging.getLogger("tool_registry")

# Thread-safe singleton lock
_registry_lock = threading.Lock()


# =============================================================================
# TOOL HINTS: Keyword mapping for deterministic tool selection
# =============================================================================
# Maps tool names to relevant keywords for filtering.
# Before calling LLM, filter tools by matching user input against these keywords.
# Only pass 3-5 most relevant tools to the LLM.
#
# IMPORTANT: Keywords are now used WITH intent gating (see resilient_router.py)
# to prevent false positives like file.read appearing for "open notepad"

TOOL_HINTS: Dict[str, List[str]] = {
    # System tools
    "system.lock_pc": ["lock", "secure", "screen", "workstation"],
    "system.sleep_pc": ["sleep", "suspend", "rest", "power save"],
    "system.restart_pc": ["restart", "reboot", "refresh"],
    "system.shutdown_pc": ["shutdown", "power off", "turn off", "hibernate"],
    
    # File tools - NOTE: "open" keyword removed from file.read to prevent false positive
    "file.read": ["read", "view", "contents", "text", "file content"],  # Removed "open"
    "file.write": ["write", "create", "save", "store", "file", "content"],
    "file.open": ["open file", "launch file", "start file", "document"],  # More specific
    "file.delete": ["delete", "remove", "erase", "destroy", "file"],
    "file.copy": ["copy", "duplicate", "clone", "file"],
    "file.move": ["move", "rename", "transfer", "file"],
    
    # App tools - "open" keyword stays here for app opening
    "app.open": ["open", "launch", "start", "run", "application", "program", "app", "bring up"],
    "app.close": ["close", "quit", "exit", "terminate", "application", "app"],
    "app.list": ["list", "running", "active", "applications", "processes"],
    
    # Web tools
    "web.search": ["search", "google", "find", "query", "web", "internet"],
    "web.open_url": ["url", "website", "link", "navigate", "browse", "http"],
    "web.close_browser": ["browser", "chrome", "firefox", "edge", "close", "tab"],
    "web.search_site": ["site", "within", "specific", "website", "domain"],
    
    # UI/Input tools
    "ui.type_text": ["type", "input", "keyboard", "text", "enter"],
    "ui.click": ["click", "mouse", "button", "select"],
    "ui.scroll": ["scroll", "page", "up", "down"],
    
    # Time tools
    "time.get_current": ["time", "date", "now", "current", "clock"],
    "time.set_alarm": ["alarm", "reminder", "alert", "notify"],
    
    # Settings tools
    "settings.get_volume": ["volume", "sound", "audio", "level", "speaker"],
    "settings.set_volume": ["volume", "sound", "audio", "mute", "speaker", "level"],
    "settings.get_brightness": ["brightness", "screen", "display", "monitor"],
    "settings.set_brightness": ["brightness", "screen", "display", "dim", "bright"],
}


# =============================================================================
# REFACTORED TOOL REGISTRY
# =============================================================================

class ToolRegistry:
    """
    Central registry for all JARVIS tools with strict naming and schemas.
    
    Features:
    - Single source of truth for available tools
    - Automatic tool discovery from module structure
    - Validation of tool names before execution
    - Schema generation for LLM function calling
    - TOOL_HINTS based filtering for deterministic selection
    """
    
    _instance: Optional["ToolRegistry"] = None
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._loaded_modules: set = set()
    
    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """Get singleton instance (thread-safe with double-checked locking)."""
        if cls._instance is None:
            with _registry_lock:
                if cls._instance is None:
                    cls._instance = ToolRegistry()
        return cls._instance
    
    def register(self, tool: BaseTool) -> None:
        """
        Register a tool instance with strict naming validation.
        
        Args:
            tool: Tool instance to register
            
        Raises:
            ValueError: If tool name doesn't follow <domain>.<verb>_<object> convention
            
        Note: During migration period, legacy names are auto-converted to new format.
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Expected BaseTool instance, got {type(tool)}")
        
        # Auto-migrate legacy names during transition period
        original_name = tool.name
        if not self._validate_tool_name_format(tool.name):
            # Try to auto-convert legacy name to new format
            new_name = self._migrate_tool_name(tool.name, tool.category)
            if new_name:
                log.info(f"Migrating legacy tool name '{tool.name}' → '{new_name}'")
                tool.name = new_name
            else:
                # Can't migrate automatically - log warning and skip strict validation for now
                log.warning(
                    f"Tool '{tool.name}' doesn't follow naming convention. "
                    f"Consider renaming to <domain>.<verb>_<object> format."
                )
                # For backward compatibility, allow registration but log warning
                # In production, you may want to raise ValueError here
        
        self._tools[tool.name] = tool
        log.debug(f"Registered tool: {tool.name}")
    
    def _migrate_tool_name(self, old_name: str, category: str) -> Optional[str]:
        """
        Attempt to migrate a legacy tool name to new format.
        
        Maps common legacy patterns to new format:
        - lock_pc → system.lock_pc
        - open_app → app.open
        - read_file → file.read
        
        Args:
            old_name: Legacy tool name
            category: Tool category (fallback for domain)
            
        Returns:
            New formatted name, or None if can't migrate
        """
        # Common legacy name mappings
        MIGRATION_MAP = {
            # System tools
            'lock_pc': 'system.lock_pc',
            'sleep_pc': 'system.sleep_pc',
            'restart_pc': 'system.restart_pc',
            'shutdown_pc': 'system.shutdown_pc',
            'set_brightness': 'settings.set_brightness',
            'get_brightness': 'settings.get_brightness',
            'battery_status': 'system.get_battery',
            
            # App tools  
            'open_app': 'app.open',
            'close_app': 'app.close',
            'focus_window': 'app.focus_window',
            
            # File tools
            'read_file': 'file.read',
            'create_file': 'file.write',
            'open_file': 'file.open',
            'delete_file': 'file.delete',
            
            # Web tools
            'search_web': 'web.search',
            'open_url': 'web.open_url',
            'close_browser': 'web.close_browser',
            'search_in_site': 'web.search_site',
            
            # Settings/Audio tools
            'get_volume': 'settings.get_volume',
            'set_volume': 'settings.set_volume',
            
            # Time tools
            'get_time': 'time.get_current',
            'get_date': 'time.get_current',
            
            # Input/UI tools
            'type_text': 'ui.type_text',
            'clear_text': 'ui.clear_text',
            
            # Network tools
            'get_ip': 'network.get_ip',
            
            # Screen tools
            'analyze_screen': 'screen.analyze',
            'capture_screen': 'screen.capture',
            
            # Script/Command tools
            'run_command': 'system.run_command',
            
            # Task tools
            'task_check': 'tasks.check',
            
            # Data tools
            'create_note': 'data.create_note',
            'add_todo': 'data.add_todo',
            'calculate': 'data.calculate',
        }
        
        return MIGRATION_MAP.get(old_name)
    
    def _validate_tool_name_format(self, name: str) -> bool:
        """Validate tool name follows <domain>.<verb>_<object> format."""
        if "." not in name:
            return False
        parts = name.split(".")
        if len(parts) != 2:
            return False
        domain, action = parts
        if "_" not in action:
            return False
        return True
    
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
        """Get a tool by name."""
        return self._tools.get(name)
    
    def has_tool(self, name: str) -> bool:
        """Check if a tool exists in the registry."""
        return name in self._tools
    
    def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with validation."""
        tool = self.get(name)
        
        if tool is None:
            raise Exception(f"Unknown tool: '{name}'. Available tools: {', '.join(sorted(self._tools.keys()))}")
        
        # Validate parameters first
        is_valid, error_msg = tool.validate(**kwargs)
        if not is_valid:
            raise Exception(error_msg)
        
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
        """Get Ollama function calling schemas for all tools (alias)."""
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
        """Auto-discover and register tools from a module."""
        if module_path in self._loaded_modules:
            log.debug(f"Module already loaded: {module_path}")
            return 0
        
        try:
            module = importlib.import_module(module_path)
            count = 0
            
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                
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
        """Auto-discover and load all tools from the tools directory structure."""
        if base_dir is None:
            base_dir = Path(__file__).parent
        
        total = 0
        
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
        """Validate that a tool name exists in the registry."""
        if name in self._tools:
            return True, ""
        
        available = sorted(self._tools.keys())
        error = f"Unknown tool: '{name}'"
        
        if available:
            similar = [t for t in available if name.lower() in t.lower() or t.lower() in name.lower()]
            if similar:
                error += f". Did you mean: {', '.join(similar[:3])}?"
            error += f". Available tools: {', '.join(available[:10])}"
            if len(available) > 10:
                error += f"... ({len(available)} total)"
        
        return False, error
    
    # ==========================================================================
    # NEW: TOOL HINT FILTERING FOR DETERMINISTIC SELECTION
    # ==========================================================================
    
    def filter_tools_by_hints(self, user_input: str, max_tools: int = 5) -> Dict[str, BaseTool]:
        """
        Filter tools based on keyword matching with user input.
        
        This ensures only relevant tools (3-5 max) are passed to the LLM,
        reducing hallucination and incorrect tool selection.
        
        Args:
            user_input: User's natural language request
            max_tools: Maximum number of tools to return (default: 5)
            
        Returns:
            Dict of filtered tool_name -> tool_instance
        """
        user_input_lower = user_input.lower()
        scored_tools: List[tuple[str, BaseTool, int]] = []
        
        for tool_name, keywords in TOOL_HINTS.items():
            if tool_name not in self._tools:
                continue
            
            # Count keyword matches
            match_count = sum(1 for kw in keywords if kw in user_input_lower)
            
            if match_count > 0:
                scored_tools.append((tool_name, self._tools[tool_name], match_count))
        
        # Sort by match count (descending)
        scored_tools.sort(key=lambda x: x[2], reverse=True)
        
        # Return top N tools
        result = {}
        for tool_name, tool, _ in scored_tools[:max_tools]:
            result[tool_name] = tool
        
        return result
    
    def get_filtered_schemas(self, user_input: str, max_tools: int = 5) -> List[dict]:
        """
        Get schemas for filtered tools based on user input hints.
        
        Args:
            user_input: User's natural language request
            max_tools: Maximum number of tools to return
            
        Returns:
            List of tool schemas for LLM function calling
        """
        filtered_tools = self.filter_tools_by_hints(user_input, max_tools)
        return [tool.get_schema() for tool in filtered_tools.values()]


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry.get_instance()
        _registry.load_all_tools()
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


def filter_tools(user_input: str, max_tools: int = 5) -> Dict[str, BaseTool]:
    """Filter tools by hints for deterministic selection."""
    return get_registry().filter_tools_by_hints(user_input, max_tools)


def get_filtered_schemas(user_input: str, max_tools: int = 5) -> List[dict]:
    """Get filtered tool schemas based on user input."""
    return get_registry().get_filtered_schemas(user_input, max_tools)
