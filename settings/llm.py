"""LLM, context budget, agent iteration, and thinking configuration."""

from settings._helpers import get_env_str, get_env_int, get_env_float, get_env_bool

LLM_MODEL = get_env_str("OLLAMA_MODEL", "gpt-oss:120b-cloud")
EXECUTOR_MODEL = get_env_str("EXECUTOR_MODEL", "gpt-oss:20b-cloud")
LLM_VISION_MODEL = get_env_str("OLLAMA_VISION_MODEL", "gemma3:27b-cloud")
LLM_BASE_URL = get_env_str("OLLAMA_CLOUD_URL", "https://api.ollama.com/api/chat")
OLLAMA_LOCAL_URL = get_env_str("OLLAMA_LOCAL_URL", "http://localhost:11434")
OLLAMA_LOCAL_MODEL = get_env_str("OLLAMA_LOCAL_MODEL", "llama3")
OLLAMA_CLOUD_URL = get_env_str("OLLAMA_CLOUD_URL", "https://api.ollama.com/api/chat")
OLLAMA_API_KEY = get_env_str("OLLAMA_API_KEY", "")
OLLAMA_MODE = get_env_str("OLLAMA_MODE", "auto")
OLLAMA_TEMPERATURE = get_env_float("OLLAMA_TEMPERATURE", 0.7)
OLLAMA_MAX_TOKENS = get_env_int("OLLAMA_MAX_TOKENS", 8192)
AGENT_MAX_TOKENS = get_env_int("AGENT_MAX_TOKENS", 8192)
LLM_TIMEOUT = get_env_int("OLLAMA_TIMEOUT", 180)
VISION_TIMEOUT = get_env_int("OLLAMA_VISION_TIMEOUT", 60)
OLLAMA_MAX_RETRIES = get_env_int("OLLAMA_MAX_RETRIES", 3)
MAX_CONTEXT_TOKENS = get_env_int("MAX_CONTEXT_TOKENS", 100000)

# gpt-oss 120b Thinking / Reasoning
THINKING_ENABLED = get_env_bool("THINKING_ENABLED", True)
THINKING_BUDGET = get_env_int("THINKING_BUDGET", 8000)
REASONING_EFFORT = get_env_str("REASONING_EFFORT", "medium")
LLM_TOOL_SCHEMA_LIMIT = get_env_int("LLM_TOOL_SCHEMA_LIMIT", 0)
TOOL_LOOP_HISTORY_MESSAGES = get_env_int("TOOL_LOOP_HISTORY_MESSAGES", 24)
MAX_SCREENSHOTS_IN_CONTEXT = get_env_int("MAX_SCREENSHOTS_IN_CONTEXT", 0)
VISION_TO_TEXT_MODE = get_env_bool("VISION_TO_TEXT_MODE", True)

# Iteration & Mode Caps
ITERATION_CAPS = {
    "interactive_cloud": 10,
    "interactive_local": 12,
    "autonomous_cloud": 8,
    "autonomous_local": 10,
}
