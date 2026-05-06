"""
JARVIS Unified Capability Registry
Registers and manages the 30 core capabilities.
"""

from typing import Optional, Any
import logging

from jarvis.capabilities import (
    get_capability_category, 
    get_all_capabilities,
    validate_capability
)
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
    get_vision_bridge as get_vision_reasoning_bridge,
    get_tool_evaluator as get_tool_self_evaluator
)

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """
    Central registry for all 30 JARVIS capabilities.
    
    Provides unified access to all tools with consistent interface.
    """
    
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._capabilities = {}
        self._initialized = False
    
    def initialize(self, reasoning_model=None, vision_model=None):
        """Initialize all 30 capabilities."""
        if self._initialized:
            logger.warning("Registry already initialized")
            return
        
        logger.info("Initializing JARVIS 30-tool capability registry...")
        
        # 1. Core Orchestration (4) - Initialize tool_dispatcher first with all tools
        # Get all capabilities that will be registered
        all_capabilities = {}
        
        # System Control (6)
        sandbox_mode = self.config.get("sandbox_mode", True)
        all_capabilities["run_terminal_command"] = get_run_terminal_command(sandbox_mode=sandbox_mode)
        all_capabilities["run_python_code"] = get_run_python_code()
        all_capabilities["window_manager"] = get_window_manager()
        all_capabilities["process_manager"] = get_process_manager()
        all_capabilities["system_info"] = get_system_info()
        all_capabilities["shutdown_restart_control"] = get_shutdown_restart_control()
        
        # Vision & Screen Understanding (3)
        all_capabilities["screen_capture"] = get_screen_capture()
        all_capabilities["ocr_extract_text"] = get_ocr_extract_text()
        all_capabilities["vision_analyzer"] = get_vision_analyzer(vision_model)
        
        # Web & Knowledge (5)
        search_api_key = self.config.get("search_api_key")
        all_capabilities["web_search"] = get_web_search(api_key=search_api_key)
        all_capabilities["web_scraper"] = get_web_scraper()
        all_capabilities["url_reader"] = get_url_reader()
        all_capabilities["summarizer"] = get_summarizer(model=reasoning_model)
        all_capabilities["fact_checker"] = get_fact_checker()
        
        # File & Data System (4)
        all_capabilities["file_reader"] = get_file_reader()
        all_capabilities["file_writer"] = get_file_writer()
        all_capabilities["file_search"] = get_file_search()
        all_capabilities["data_parser"] = get_data_parser()
        
        # Productivity Tools (4)
        all_capabilities["calendar_manager"] = get_calendar_manager()
        all_capabilities["task_scheduler"] = get_task_scheduler()
        all_capabilities["notes_manager"] = get_notes_manager()
        all_capabilities["email_handler"] = get_email_handler()
        
        # Media & Interaction (3)
        all_capabilities["audio_player"] = get_audio_player()
        all_capabilities["voice_synthesizer"] = get_voice_synthesizer()
        all_capabilities["voice_recognizer"] = get_voice_recognizer()
        
        # AI Internal Tools (3)
        all_capabilities["reasoning_engine"] = get_reasoning_engine(model=reasoning_model)
        all_capabilities["vision_reasoning_bridge"] = get_vision_reasoning_bridge(
            vision_model=vision_model,
            reasoning_model=reasoning_model
        )
        all_capabilities["tool_self_evaluator"] = get_tool_self_evaluator()
        
        # Now create tool_dispatcher with all tools registered
        tool_dispatcher = get_tool_dispatcher()
        for name, instance in all_capabilities.items():
            tool_dispatcher.register_tool(name, instance)
        
        self.register("tool_dispatcher", tool_dispatcher)
        self.register("intent_router", get_intent_router(reasoning_model))
        self.register("task_planner", get_task_planner(get_all_capabilities()))
        self.register("memory_manager", get_memory_manager())
        
        # Register all other capabilities
        for name, instance in all_capabilities.items():
            self.register(name, instance)
        
        self._initialized = True
        logger.info(f"Initialized {len(self._capabilities)} capabilities")
    
    def register(self, name: str, instance: Any):
        """Register a capability."""
        self._capabilities[name] = instance
        logger.debug(f"Registered capability: {name}")
    
    def get(self, name: str) -> Optional[Any]:
        """Get a capability by name."""
        return self._capabilities.get(name)
    
    def execute(self, tool_name: str, **kwargs) -> dict:
        """Execute a capability."""
        if not self._initialized:
            return {
                "success": False,
                "error": "Registry not initialized. Call initialize() first."
            }
        
        if not validate_capability(tool_name):
            return {
                "success": False,
                "error": f"Unknown capability: {tool_name}. Valid: {get_all_capabilities()}"
            }
        
        tool = self.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Capability not found: {tool_name}"
            }
        
        try:
            return tool.execute(**kwargs)
        except Exception as e:
            logger.error(f"Execution error in {tool_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_capabilities(self) -> list[dict]:
        """List all registered capabilities with metadata."""
        result = []
        for name in get_all_capabilities():
            category = get_capability_category(name)
            registered = name in self._capabilities
            result.append({
                "name": name,
                "category": category,
                "registered": registered
            })
        return result
    
    def get_summary(self) -> dict:
        """Get registry summary."""
        categories = {}
        for name in get_all_capabilities():
            cat = get_capability_category(name)
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(name)
        
        registered_count = sum(1 for n in get_all_capabilities() if n in self._capabilities)
        
        return {
            "total_capabilities": 30,
            "registered": registered_count,
            "initialized": self._initialized,
            "categories": {k: len(v) for k, v in categories.items()},
            "by_category": categories
        }


# Global registry instance
_registry_instance = None


def get_registry(config: Optional[dict] = None) -> CapabilityRegistry:
    """Get or create the global capability registry."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = CapabilityRegistry(config)
    return _registry_instance


def initialize_registry(reasoning_model=None, vision_model=None, 
                        config: Optional[dict] = None) -> CapabilityRegistry:
    """Initialize the global registry with models."""
    registry = get_registry(config)
    registry.initialize(reasoning_model=reasoning_model, vision_model=vision_model)
    return registry
