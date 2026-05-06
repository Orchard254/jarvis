"""
JARVIS Core Capabilities - 30-Tool Schema
Organized around capabilities, not random tools.
Powered by GPT-OSS 120B (Reasoning) + Gemma 3 27B (Vision).
"""

__all__ = [
    # 1. Core Orchestration
    "intent_router",
    "task_planner", 
    "tool_dispatcher",
    "memory_manager",
    
    # 2. System Control
    "run_terminal_command",
    "run_python_code",
    "window_manager",
    "process_manager",
    "system_info",
    "shutdown_restart_control",
    
    # 3. Vision & Screen Understanding
    "screen_capture",
    "ocr_extract_text",
    "vision_analyzer",
    
    # 4. Web & Knowledge
    "web_search",
    "web_scraper",
    "url_reader",
    "summarizer",
    "fact_checker",
    
    # 5. File & Data System
    "file_reader",
    "file_writer",
    "file_search",
    "data_parser",
    
    # 6. Productivity Tools
    "calendar_manager",
    "task_scheduler",
    "notes_manager",
    "email_handler",
    
    # 7. Media & Interaction
    "audio_player",
    "voice_synthesizer",
    "voice_recognizer",
    
    # 8. AI Internal Tools
    "reasoning_engine",
    "vision_reasoning_bridge",
    "tool_self_evaluator",
]

# Capability categories for routing
CAPABILITY_CATEGORIES = {
    "orchestration": ["intent_router", "task_planner", "tool_dispatcher", "memory_manager"],
    "system_control": ["run_terminal_command", "run_python_code", "window_manager", "process_manager", "system_info", "shutdown_restart_control"],
    "vision": ["screen_capture", "ocr_extract_text", "vision_analyzer"],
    "web_knowledge": ["web_search", "web_scraper", "url_reader", "summarizer", "fact_checker"],
    "file_data": ["file_reader", "file_writer", "file_search", "data_parser"],
    "productivity": ["calendar_manager", "task_scheduler", "notes_manager", "email_handler"],
    "media_interaction": ["audio_player", "voice_synthesizer", "voice_recognizer"],
    "ai_internal": ["reasoning_engine", "vision_reasoning_bridge", "tool_self_evaluator"],
}

def get_capability_category(tool_name: str) -> str | None:
    """Get the category for a given tool name."""
    for category, tools in CAPABILITY_CATEGORIES.items():
        if tool_name in tools:
            return category
    return None

def get_all_capabilities() -> list[str]:
    """Get all 30 core capability names."""
    return __all__.copy()

def validate_capability(tool_name: str) -> bool:
    """Validate if a tool name is part of the core 30."""
    return tool_name in __all__
