"""
JARVIS Configuration Module

Centralized configuration management with environment overrides.
DEPRECATED: This module is kept for backwards compatibility.
All new code should import directly from settings.py instead.

Usage (OLD - deprecated):
    from jarvis.config.config import get_config
    config = get_config()

Usage (NEW - recommended):
    from settings import OLLAMA_API_KEY, TTS_ENGINE, MAX_HISTORY
"""

# Import all settings for backwards compatibility
from settings import DEFAULT_CONFIG, validate_settings, print_settings_summary

# Re-export all individual settings for backwards compatibility
from settings import (
    OLLAMA_API_KEY,
    OLLAMA_CLOUD_URL,
    OLLAMA_LOCAL_URL,
    OLLAMA_MODEL,
    OLLAMA_VISION_MODEL,
    LLM_MODEL,
    OLLAMA_CODER_MODEL,
    OLLAMA_MODE,
    OLLAMA_TEMPERATURE,
    OLLAMA_MAX_TOKENS,
    AGENT_MAX_TOKENS,
    OLLAMA_TIMEOUT,
    OLLAMA_MAX_RETRIES,
    FALLBACK_TO_LOCAL,
    CONVERSATION_HISTORY_LIMIT,
    TTS_ENGINE,
    TTS_ENABLED,
    KOKORO_VOICE,
    KOKORO_LANG_CODE,
    KOKORO_SPEED,
    PIPER_EXE,
    PIPER_MODEL,
    SAMPLE_RATE,
    SILENCE_THRESHOLD,
    SILENCE_DURATION,
    MAX_RECORD_SECS,
    MIC_DEVICE,
    AUDIO_DEVICE,
    STT_ENGINE,
    STT_LANGUAGE,
    WAKE_WORD,
    WAKE_WORD_THRESHOLD,
    WAKE_WORD_COOLDOWN,
    CONTINUOUS_MODE,
    WAKE_WORD_ENABLED,
    MAX_HISTORY,
    MAX_AGENT_ROUNDS,
    MAX_TOOL_ITERATIONS,
    AGENT_MODE,
    WORKING_MEMORY_MAX_MESSAGES,
    WORKING_MEMORY_MAX_TOKENS,
    MEMORY_RETRIEVAL_LIMIT,
    BATTERY_WARN_THRESHOLD,
    BATTERY_CRITICAL_THRESHOLD,
    CPU_SPIKE_THRESHOLD,
    CPU_SPIKE_DURATION,
    MEMORY_WARN_THRESHOLD,
    DISK_WARN_THRESHOLD,
    IDLE_MINUTES,
    MONITOR_INTERVAL,
    HEALTH_CHECK_INTERVAL,
    AMBIENT_MONITORING,
    LOG_DIR,
    NOTES_DIR,
    REMINDERS_DIR,
    DATA_DIR,
    CONFIG_DIR,
    USER_HOME,
    CONFIRM_DANGEROUS,
    ENABLE_AUDIT_LOG,
    SAFETY_ENABLED,
    LOG_LEVEL,
    WEATHER_API_KEY,
    NEWS_API_KEY,
    HF_TOKEN,
    USER_NAME,
    ENABLE_SKILLS,
    ENABLE_PLANNING,
    ENABLE_REFLECTION,
    VOICE_ENABLED,
    MODE,
)


def get_config(config_path=None):
    """
    Load configuration with environment variable overrides from .env file.
    
    Args:
        config_path: Optional path to config file (not used, kept for API compatibility)
        
    Returns:
        Configuration dict (DEFAULT_CONFIG from settings)
    """
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    return DEFAULT_CONFIG.copy()


def save_config(config, path):
    """
    Save configuration to YAML file.
    
    Args:
        config: Config dict to save
        path: Path to save to
        
    Returns:
        True if successful
    """
    try:
        from pathlib import Path
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        import yaml
        with open(path_obj, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        return True
        
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def get_default_config():
    """
    Get a copy of the default configuration.
    
    Returns:
        Default config dict
    """
    return DEFAULT_CONFIG.copy()
