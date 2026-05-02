"""
JARVIS Configuration Module

Centralized configuration management with environment overrides.
Loads from .env file using python-dotenv for compatibility with existing setup.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, will use system env vars


# Default configuration
DEFAULT_CONFIG = {
    # LLM Settings - loaded from .env
    'ollama_cloud_url': os.environ.get('OLLAMA_CLOUD_URL', 'https://api.ollama.com/api/chat'),
    'ollama_local_url': 'http://localhost:11434/api/chat',
    'model': os.environ.get('OLLAMA_MODEL', 'nemotron-3-nano:30b-cloud'),
    'ollama_api_key': os.environ.get('OLLAMA_API_KEY', ''),
    'fallback_to_local': True,
    'max_retries': 3,
    'llm_timeout': int(os.environ.get('OLLAMA_TIMEOUT', '120')),
    'conversation_history_limit': 20,
    
    # TTS Settings
    'tts_enabled': True,
    'tts_engine': 'kokoro',
    'tts_voice': 'bm_george',
    'tts_speed': 1.15,
    
    # STT Settings
    'stt_engine': 'google',
    'stt_language': 'en-US',
    
    # Wake Word Settings
    'wake_word_enabled': True,
    'wake_word_model': 'hey_jarvis',
    'wake_word_threshold': 0.5,
    
    # Memory Settings
    'working_memory_max_messages': 20,
    'working_memory_max_tokens': 4000,
    'memory_retrieval_limit': 5,
    
    # Safety Settings
    'safety_enabled': True,
    'require_confirmation_for': [
        'shutdown_computer',
        'restart_computer',
        'delete_file',
        'close_app'
    ],
    'blocked_paths': [
        'C:\\\\Windows',
        'C:\\\\Program Files',
        'C:\\\\Program Files (x86)',
        'C:\\\\System Volume Information'
    ],
    
    # Paths
    'data_dir': 'jarvis_data',
    'log_dir': 'logs',
    'config_dir': 'config',
    
    # Logging
    'log_level': 'INFO',
    
    # User Profile
    'user_name': 'User',
    'user_preferences': {},
    'user_routines': [],
    
    # Modes
    'mode': 'agent',
    'voice_enabled': False,
    
    # Monitoring
    'ambient_monitoring': True,
    'health_check_interval': 60,
    
    # Advanced
    'enable_skills': True,
    'enable_planning': True,
    'enable_reflection': True,
    'max_tool_iterations': 5
}


def get_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration with environment variable overrides from .env file.
    
    Args:
        config_path: Optional path to config file (not used, kept for API compatibility)
        
    Returns:
        Configuration dict
    """
    config = DEFAULT_CONFIG.copy()
    
    # Ensure data directory exists
    data_dir = Path(config.get('data_dir', 'jarvis_data'))
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Ensure log directory exists
    log_dir = Path(config.get('log_dir', 'logs'))
    log_dir.mkdir(parents=True, exist_ok=True)
    
    return config


def save_config(config: Dict, path: str) -> bool:
    """
    Save configuration to YAML file.
    
    Args:
        config: Config dict to save
        path: Path to save to
        
    Returns:
        True if successful
    """
    try:
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        import yaml
        with open(path_obj, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        return True
        
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def get_default_config() -> Dict[str, Any]:
    """
    Get a copy of the default configuration.
    
    Returns:
        Default config dict
    """
    return DEFAULT_CONFIG.copy()
