"""
JARVIS Tools Compatibility Layer

This module provides backward compatibility for legacy code that imports
from jarvis.tools. It redirects all imports to the new capability-based
system in jarvis.capabilities.
"""

import logging
from typing import Optional, Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Re-export from capabilities registry for backward compatibility
from jarvis.capabilities.registry import (
    CapabilityRegistry,
    get_registry,
    initialize_registry
)

# Import ToolRegistry from local module
from jarvis.tools.registry import ToolRegistry

# Re-export capability functions for direct tool access
from jarvis.capabilities.orchestration import (
    get_intent_router,
    get_task_planner,
    get_tool_dispatcher,
    get_memory_manager
)
from jarvis.capabilities.system_control import (
    get_run_terminal_command,
    get_run_python_code,
    get_window_manager,
    get_process_manager,
    get_system_info,
    get_shutdown_restart_control
)
from jarvis.capabilities.vision import (
    get_screen_capture,
    get_ocr_extract_text,
    get_vision_analyzer
)
from jarvis.capabilities.web_knowledge import (
    get_web_search,
    get_web_scraper,
    get_url_reader,
    get_summarizer,
    get_fact_checker
)
from jarvis.capabilities.file_data import (
    get_file_reader,
    get_file_writer,
    get_file_search,
    get_data_parser
)
from jarvis.capabilities.productivity import (
    get_calendar_manager,
    get_task_scheduler,
    get_notes_manager,
    get_email_handler
)
from jarvis.capabilities.media_interaction import (
    get_audio_player,
    get_voice_synthesizer,
    get_voice_recognizer
)
from jarvis.capabilities.ai_internal import (
    get_reasoning_engine,
    get_vision_bridge,
    get_tool_evaluator as get_tool_self_evaluator
)


class ToolStatus(Enum):
    """Status of a tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    TIMEOUT = "timeout"


@dataclass
class ToolResult:
    """
    Standardized result from tool execution.
    
    Attributes:
        success: Whether the tool executed successfully
        output: The tool's output data
        error: Error message if execution failed
        metadata: Additional metadata about execution
        status: Execution status enum
    """
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: ToolStatus = ToolStatus.SUCCESS
    
    @classmethod
    def ok(cls, output: Any, metadata: Optional[Dict] = None) -> 'ToolResult':
        """Create a successful result."""
        return cls(
            success=True,
            output=output,
            metadata=metadata or {},
            status=ToolStatus.SUCCESS
        )
    
    @classmethod
    def fail(cls, error: str, output: Any = None) -> 'ToolResult':
        """Create a failed result."""
        return cls(
            success=False,
            output=output,
            error=error,
            status=ToolStatus.ERROR
        )
    
    @classmethod
    def timeout(cls, error: str = "Execution timed out") -> 'ToolResult':
        """Create a timeout result."""
        return cls(
            success=False,
            error=error,
            status=ToolStatus.TIMEOUT
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
            "status": self.status.value
        }


class BaseTool:
    """
    Abstract base class for all JARVIS tools.
    
    Provides common functionality and interface for tool implementation.
    Legacy compatibility wrapper around the new capability system.
    """
    
    name: str = "base_tool"
    description: str = "Base tool class"
    category: str = "general"
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._enabled = True
    
    @property
    def enabled(self) -> bool:
        """Check if tool is enabled."""
        return self._enabled
    
    def enable(self) -> None:
        """Enable the tool."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable the tool."""
        self._enabled = False
    
    def validate_input(self, **kwargs) -> bool:
        """
        Validate input parameters before execution.
        
        Override in subclasses for custom validation.
        """
        return True
    
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given parameters.
        
        Override in subclasses with actual implementation.
        """
        raise NotImplementedError("Subclasses must implement execute()")
    
    def get_schema(self) -> Dict[str, Any]:
        """
        Get the tool's parameter schema for function calling.
        
        Override in subclasses to provide OpenAI-style schema.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    
    def __call__(self, **kwargs) -> ToolResult:
        """Allow calling the tool instance directly."""
        if not self._enabled:
            return ToolResult.fail(f"Tool {self.name} is disabled")
        return self.execute(**kwargs)


# Map old tool names to new capability getters
TOOL_NAME_MAP = {
    # Orchestration
    "intent_router": ("intent_router", get_intent_router),
    "task_planner": ("task_planner", get_task_planner),
    "tool_dispatcher": ("tool_dispatcher", get_tool_dispatcher),
    "memory_manager": ("memory_manager", get_memory_manager),
    
    # System Control
    "run_terminal_command": ("run_terminal_command", get_run_terminal_command),
    "run_python_code": ("run_python_code", get_run_python_code),
    "window_manager": ("window_manager", get_window_manager),
    "process_manager": ("process_manager", get_process_manager),
    "system_info": ("system_info", get_system_info),
    "shutdown_restart_control": ("shutdown_restart_control", get_shutdown_restart_control),
    
    # Vision
    "screen_capture": ("screen_capture", get_screen_capture),
    "ocr_extract_text": ("ocr_extract_text", get_ocr_extract_text),
    "vision_analyzer": ("vision_analyzer", get_vision_analyzer),
    
    # Web & Knowledge
    "web_search": ("web_search", get_web_search),
    "web_scraper": ("web_scraper", get_web_scraper),
    "url_reader": ("url_reader", get_url_reader),
    "summarizer": ("summarizer", get_summarizer),
    "fact_checker": ("fact_checker", get_fact_checker),
    
    # File & Data
    "file_reader": ("file_reader", get_file_reader),
    "file_writer": ("file_writer", get_file_writer),
    "file_search": ("file_search", get_file_search),
    "data_parser": ("data_parser", get_data_parser),
    
    # Productivity
    "calendar_manager": ("calendar_manager", get_calendar_manager),
    "task_scheduler": ("task_scheduler", get_task_scheduler),
    "notes_manager": ("notes_manager", get_notes_manager),
    "email_handler": ("email_handler", get_email_handler),
    
    # Media & Interaction
    "audio_player": ("audio_player", get_audio_player),
    "voice_synthesizer": ("voice_synthesizer", get_voice_synthesizer),
    "voice_recognizer": ("voice_recognizer", get_voice_recognizer),
    
    # AI Internal
    "reasoning_engine": ("reasoning_engine", get_reasoning_engine),
    "vision_reasoning_bridge": ("vision_reasoning_bridge", get_vision_bridge),
    "tool_self_evaluator": ("tool_self_evaluator", get_tool_self_evaluator),
}


def get_tool(tool_name: str, config: Optional[Dict] = None) -> Optional[Any]:
    """
    Get a tool instance by name (legacy compatibility).
    
    Args:
        tool_name: Name of the tool to retrieve
        config: Optional configuration dict
        
    Returns:
        Tool instance or None if not found
    """
    if tool_name not in TOOL_NAME_MAP:
        logger.warning(f"Unknown tool: {tool_name}")
        return None
    
    cap_name, getter_func = TOOL_NAME_MAP[tool_name]
    
    try:
        # Some getters require model arguments
        if tool_name in ["vision_analyzer", "summarizer", "reasoning_engine", 
                         "vision_reasoning_bridge", "task_planner"]:
            # Return wrapper that will be initialized later with models
            return lambda model=None: getter_func(model)
        elif tool_name == "intent_router":
            return lambda model=None: getter_func(model)
        elif tool_name == "web_search":
            api_key = config.get("search_api_key") if config else None
            return getter_func(api_key=api_key)
        else:
            return getter_func()
    except Exception as e:
        logger.error(f"Failed to get tool {tool_name}: {e}")
        return None


def list_available_tools() -> List[str]:
    """List all available tool names."""
    return list(TOOL_NAME_MAP.keys())


def create_legacy_tool_wrapper(capability_name: str, registry: CapabilityRegistry):
    """
    Create a legacy-style tool wrapper around a capability.
    
    Args:
        capability_name: Name of the capability
        registry: CapabilityRegistry instance
        
    Returns:
        BaseTool-compatible wrapper
    """
    class LegacyToolWrapper(BaseTool):
        def __init__(self, name: str, registry: CapabilityRegistry):
            super().__init__()
            self.name = name
            self._registry = registry
            self.description = f"Legacy wrapper for {name}"
        
        def execute(self, **kwargs) -> ToolResult:
            result = self._registry.execute(self.name, **kwargs)
            if result.get("success"):
                return ToolResult.ok(result.get("output"), result)
            else:
                return ToolResult.fail(result.get("error", "Unknown error"))
    
    return LegacyToolWrapper(capability_name, registry)


__all__ = [
    # Classes
    "BaseTool",
    "ToolResult",
    "ToolStatus",
    "CapabilityRegistry",
    "ToolRegistry",
    
    # Functions
    "get_tool",
    "list_available_tools",
    "get_registry",
    "initialize_registry",
    "create_legacy_tool_wrapper",
    
    # Capability getters (re-exported)
    "get_intent_router",
    "get_task_planner",
    "get_tool_dispatcher",
    "get_memory_manager",
    "get_run_terminal_command",
    "get_run_python_code",
    "get_window_manager",
    "get_process_manager",
    "get_system_info",
    "get_shutdown_restart_control",
    "get_screen_capture",
    "get_ocr_extract_text",
    "get_vision_analyzer",
    "get_web_search",
    "get_web_scraper",
    "get_url_reader",
    "get_summarizer",
    "get_fact_checker",
    "get_file_reader",
    "get_file_writer",
    "get_file_search",
    "get_data_parser",
    "get_calendar_manager",
    "get_task_scheduler",
    "get_notes_manager",
    "get_email_handler",
    "get_audio_player",
    "get_voice_synthesizer",
    "get_voice_recognizer",
    "get_reasoning_engine",
    "get_vision_bridge",
    "get_tool_self_evaluator",
]
