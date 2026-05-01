"""
JARVIS Configuration Module

Centralized configuration management with defaults and environment overrides.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


# Default configuration
DEFAULT_CONFIG = {
    # LLM Settings
    'ollama_cloud_url': 'https://ollama.com/api/chat',
    'ollama_local_url': 'http://localhost:11434/api/chat',
    'model': 'nemotron-3-nano:30b-cloud',
    'fallback_to_local': True,
    'max_retries': 3,
    'llm_timeout': 60,
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
        'C:\\Windows',
        'C:\\Program Files',
        'C:\\Program Files (x86)',
        'C:\\System Volume Information'
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
    Load configuration from file with environment variable overrides.
    
    Args:
        config_path: Optional path to config file. If None, uses default locations.
        
    Returns:
        Configuration dict
    """
    config = DEFAULT_CONFIG.copy()
    
    # Try to load from specified path
    if config_path:
        config_file = Path(config_path)
        if config_file.exists():
            config = _load_yaml_config(config_file, config)
    else:
        # Try default locations
        default_paths = [
            Path('config/config.yaml'),
            Path('jarvis/config/config.yaml'),
            Path.home() / '.jarvis' / 'config.yaml',
            Path(os.environ.get('JARVIS_CONFIG', '')) if os.environ.get('JARVIS_CONFIG') else None
        ]
        
        for path in default_paths:
            if path and path.exists():
                config = _load_yaml_config(path, config)
                break
    
    # Override with environment variables
    config = _apply_env_overrides(config)
    
    # Ensure data directory exists
    data_dir = Path(config.get('data_dir', 'jarvis_data'))
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Ensure log directory exists
    log_dir = Path(config.get('log_dir', 'logs'))
    log_dir.mkdir(parents=True, exist_ok=True)
    
    return config


def _load_yaml_config(path: Path, base_config: Dict) -> Dict:
    """
    Load YAML config file and merge with base config.
    
    Args:
        path: Path to YAML file
        base_config: Base config to merge into
        
    Returns:
        Merged config dict
    """
    try:
        with open(path, 'r') as f:
            file_config = yaml.safe_load(f) or {}
        
        # Deep merge
        return _deep_merge(base_config, file_config)
        
    except Exception as e:
        print(f"Warning: Could not load config from {path}: {e}")
        return base_config


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """
    Deep merge two dicts.
    
    Args:
        base: Base dict
        override: Dict with values to override
        
    Returns:
        Merged dict
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def _apply_env_overrides(config: Dict) -> Dict:
    """
    Apply environment variable overrides to config.
    
    Environment variables should be prefixed with JARVIS_
    e.g., JARVIS_MODEL=nemotron would set config['model'] = 'nemotron'
    
    Args:
        config: Config dict to update
        
    Returns:
        Updated config dict
    """
    env_prefix = 'JARVIS_'
    
    for key in config.keys():
        env_key = f"{env_prefix}{key.upper()}"
        if env_key in os.environ:
            value = os.environ[env_key]
            
            # Try to convert to appropriate type
            if isinstance(config[key], bool):
                config[key] = value.lower() in ('true', '1', 'yes', 'on')
            elif isinstance(config[key], int):
                try:
                    config[key] = int(value)
                except ValueError:
                    pass
            elif isinstance(config[key], float):
                try:
                    config[key] = float(value)
                except ValueError:
                    pass
            else:
                config[key] = value
    
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


# Example config template for documentation
CONFIG_TEMPLATE = """# JARVIS Configuration File
# Save as config/config.yaml or ~/.jarvis/config.yaml

# LLM Settings
model: nemotron-3-nano:30b-cloud
ollama_cloud_url: https://ollama.com/api/chat
ollama_local_url: http://localhost:11434/api/chat
fallback_to_local: true
max_retries: 3
llm_timeout: 60

# TTS Settings
tts_enabled: true
tts_engine: kokoro
tts_voice: bm_george
tts_speed: 1.15

# STT Settings
stt_engine: google
stt_language: en-US

# Wake Word
wake_word_enabled: true
wake_word_model: hey_jarvis
wake_word_threshold: 0.5

# Memory
working_memory_max_messages: 20
working_memory_max_tokens: 4000
memory_retrieval_limit: 5

# Safety
safety_enabled: true
require_confirmation_for:
  - shutdown_computer
  - restart_computer
  - delete_file
  - close_app

# Paths
data_dir: jarvis_data
log_dir: logs

# User
user_name: User

# Features
enable_skills: true
enable_planning: true
enable_reflection: true
"""
