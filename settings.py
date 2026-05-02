"""
JARVIS Settings Module - Single Source of Truth for Configuration

This module provides type-safe access to all configuration values.
No other file should call os.environ.get() directly - everything goes
through this module.

Usage:
    from settings import OLLAMA_API_KEY, TTS_ENGINE, MAX_HISTORY
"""

from pathlib import Path
from typing import Optional
import os

from dotenv import load_dotenv

# ── Load .env file ────────────────────────────────────────


def _find_env_file() -> Optional[Path]:
    """
    Search for .env file in multiple locations:
    1. Same directory as this file
    2. Parent directory
    3. User home directory
    4. JARVIS_ENV_FILE environment variable
    """
    # Check environment variable override first
    env_override = os.environ.get("JARVIS_ENV_FILE")
    if env_override and Path(env_override).exists():
        return Path(env_override)
    
    # Search standard locations
    search_paths = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
        Path.home() / ".jarvis" / ".env",
        Path.cwd() / ".env",
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    return None


_env_file = _find_env_file()
if _env_file:
    load_dotenv(_env_file, override=True)
else:
    # Try loading from current directory as fallback
    load_dotenv(override=True)


# ── Type-safe getters ─────────────────────────────────────

def _get_str(
    key: str,
    default: str = "",
    required: bool = False
) -> str:
    value = os.environ.get(key, default)
    if required and not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Add it to your .env file. "
            f"See .env.example for reference."
        )
    return value


def _get_int(
    key: str,
    default: int = 0,
    required: bool = False
) -> int:
    value = os.environ.get(key)
    if value is None:
        if required:
            raise EnvironmentError(
                f"Required environment variable '{key}' is not set."
            )
        return default
    try:
        return int(value)
    except ValueError:
        print(f"[SETTINGS] {key}={value!r} is not a valid integer. Using default: {default}")
        return default


def _get_float(
    key: str,
    default: float = 0.0,
    required: bool = False
) -> float:
    value = os.environ.get(key)
    if value is None:
        if required:
            raise EnvironmentError(
                f"Required environment variable '{key}' is not set."
            )
        return default
    try:
        return float(value)
    except ValueError:
        print(f"[SETTINGS] {key}={value!r} is not a valid float. Using default: {default}")
        return default


def _get_bool(
    key: str,
    default: bool = False
) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on", "enabled")


def _get_path(
    key: str,
    default: str = "",
    must_exist: bool = False
) -> Optional[Path]:
    value = os.environ.get(key, default)
    if not value:
        return None
    path = Path(value)
    if must_exist and not path.exists():
        print(f"[SETTINGS] {key}={value!r} path does not exist.")
        return None
    return path


# ── LLM Settings ──────────────────────────────────────────

OLLAMA_API_KEY: str = _get_str("OLLAMA_API_KEY", required=False)
if not OLLAMA_API_KEY:
    print("[SETTINGS] OLLAMA_API_KEY is not set. Cloud LLM calls will fail with 401. "
          "Add OLLAMA_API_KEY to your .env file.")

OLLAMA_CLOUD_URL: str = _get_str(
    "OLLAMA_CLOUD_URL",
    default="https://api.ollama.com/api/chat"
)

OLLAMA_LOCAL_URL: str = _get_str(
    "OLLAMA_LOCAL_URL",
    default="http://localhost:11434/api/chat"
)

OLLAMA_MODEL: str = _get_str(
    "OLLAMA_MODEL",
    default="nemotron-3-nano:30b-cloud"
)

OLLAMA_VISION_MODEL: str = _get_str(
    "OLLAMA_VISION_MODEL",
    default="llava:latest"
)

OLLAMA_CODER_MODEL: str = _get_str(
    "OLLAMA_CODER_MODEL",
    default="codellama:latest"
)

OLLAMA_MODE: str = _get_str(
    "OLLAMA_MODE",
    default="auto"
)
if OLLAMA_MODE not in ("cloud", "local", "auto"):
    print(f"[SETTINGS] OLLAMA_MODE={OLLAMA_MODE!r} invalid. Must be cloud/local/auto. Using auto.")
    OLLAMA_MODE = "auto"

OLLAMA_TEMPERATURE: float = _get_float(
    "OLLAMA_TEMPERATURE",
    default=0.7
)

OLLAMA_MAX_TOKENS: int = _get_int(
    "OLLAMA_MAX_TOKENS",
    default=512
)

AGENT_MAX_TOKENS: int = _get_int(
    "AGENT_MAX_TOKENS",
    default=2000
)

OLLAMA_TIMEOUT: int = _get_int(
    "OLLAMA_TIMEOUT",
    default=180
)

OLLAMA_MAX_RETRIES: int = _get_int(
    "OLLAMA_MAX_RETRIES",
    default=3
)

FALLBACK_TO_LOCAL: bool = _get_bool(
    "FALLBACK_TO_LOCAL",
    default=True
)

CONVERSATION_HISTORY_LIMIT: int = _get_int(
    "CONVERSATION_HISTORY_LIMIT",
    default=20
)

# ── Audio Settings ────────────────────────────────────────

TTS_ENGINE: str = _get_str(
    "TTS_ENGINE",
    default="kokoro"
)
if TTS_ENGINE not in ("kokoro", "piper"):
    print(f"[SETTINGS] TTS_ENGINE={TTS_ENGINE!r} invalid. Must be kokoro or piper. Using kokoro.")
    TTS_ENGINE = "kokoro"

TTS_ENABLED: bool = _get_bool(
    "TTS_ENABLED",
    default=True
)

KOKORO_VOICE: str = _get_str(
    "KOKORO_VOICE",
    default="bm_george"
)

KOKORO_LANG_CODE: str = _get_str(
    "KOKORO_LANG_CODE",
    default="a"
)

KOKORO_SPEED: float = _get_float(
    "KOKORO_SPEED",
    default=1.15
)

PIPER_EXE: str = _get_str(
    "PIPER_EXE",
    default="piper_bin/piper/piper"
)

PIPER_MODEL: str = _get_str(
    "PIPER_MODEL",
    default="voices/en_US-lessac-medium.onnx"
)

SAMPLE_RATE: int = _get_int(
    "SAMPLE_RATE",
    default=16000
)

SILENCE_THRESHOLD: int = _get_int(
    "SILENCE_THRESHOLD",
    default=400
)

SILENCE_DURATION: float = _get_float(
    "SILENCE_DURATION",
    default=1.5
)

MAX_RECORD_SECS: int = _get_int(
    "MAX_RECORD_SECS",
    default=30
)

MIC_DEVICE: int = _get_int(
    "MIC_DEVICE",
    default=-1
)

AUDIO_DEVICE: int = _get_int(
    "AUDIO_DEVICE",
    default=-1
)

# STT Settings
STT_ENGINE: str = _get_str(
    "STT_ENGINE",
    default="google"
)

STT_LANGUAGE: str = _get_str(
    "STT_LANGUAGE",
    default="en-US"
)

# ── Wake Word Settings ────────────────────────────────────

WAKE_WORD: str = _get_str(
    "WAKE_WORD",
    default="alexa"
)

WAKE_WORD_THRESHOLD: float = _get_float(
    "WAKE_WORD_THRESHOLD",
    default=0.45
)

WAKE_WORD_COOLDOWN: float = _get_float(
    "WAKE_WORD_COOLDOWN",
    default=3.0
)

CONTINUOUS_MODE: bool = _get_bool(
    "CONTINUOUS_MODE",
    default=True
)

WAKE_WORD_ENABLED: bool = _get_bool(
    "WAKE_WORD_ENABLED",
    default=True
)

# ── Agent Settings ────────────────────────────────────────

MAX_HISTORY: int = _get_int(
    "MAX_HISTORY",
    default=10
)

MAX_AGENT_ROUNDS: int = _get_int(
    "MAX_AGENT_ROUNDS",
    default=8
)

MAX_TOOL_ITERATIONS: int = _get_int(
    "MAX_TOOL_ITERATIONS",
    default=5
)

AGENT_MODE: str = _get_str(
    "AGENT_MODE",
    default="agent"
)

# ── Memory Settings ───────────────────────────────────────

WORKING_MEMORY_MAX_MESSAGES: int = _get_int(
    "WORKING_MEMORY_MAX_MESSAGES",
    default=20
)

WORKING_MEMORY_MAX_TOKENS: int = _get_int(
    "WORKING_MEMORY_MAX_TOKENS",
    default=4000
)

MEMORY_RETRIEVAL_LIMIT: int = _get_int(
    "MEMORY_RETRIEVAL_LIMIT",
    default=5
)

# ── Ambient Monitor Settings ──────────────────────────────

BATTERY_WARN_THRESHOLD: int = _get_int(
    "BATTERY_WARN_THRESHOLD",
    default=20
)

BATTERY_CRITICAL_THRESHOLD: int = _get_int(
    "BATTERY_CRITICAL_THRESHOLD",
    default=10
)

CPU_SPIKE_THRESHOLD: int = _get_int(
    "CPU_SPIKE_THRESHOLD",
    default=90
)

CPU_SPIKE_DURATION: int = _get_int(
    "CPU_SPIKE_DURATION",
    default=30
)

MEMORY_WARN_THRESHOLD: int = _get_int(
    "MEMORY_WARN_THRESHOLD",
    default=85
)

DISK_WARN_THRESHOLD: int = _get_int(
    "DISK_WARN_THRESHOLD",
    default=92
)

IDLE_MINUTES: int = _get_int(
    "IDLE_MINUTES",
    default=20
)

MONITOR_INTERVAL: int = _get_int(
    "MONITOR_INTERVAL",
    default=15
)

HEALTH_CHECK_INTERVAL: int = _get_int(
    "HEALTH_CHECK_INTERVAL",
    default=60
)

AMBIENT_MONITORING: bool = _get_bool(
    "AMBIENT_MONITORING",
    default=True
)

# ── Path Settings ─────────────────────────────────────────

_BASE_DIR = Path(__file__).parent

LOG_DIR: Path = _get_path(
    "LOG_DIR",
    default=str(_BASE_DIR / "logs")
) or _BASE_DIR / "logs"

NOTES_DIR: Path = _get_path(
    "NOTES_DIR",
    default=str(_BASE_DIR / "notes")
) or _BASE_DIR / "notes"

REMINDERS_DIR: Path = _get_path(
    "REMINDERS_DIR",
    default=str(_BASE_DIR / "reminders")
) or _BASE_DIR / "reminders"

DATA_DIR: Path = _get_path(
    "DATA_DIR",
    default=str(_BASE_DIR / "jarvis_data")
) or _BASE_DIR / "jarvis_data"

CONFIG_DIR: Path = _get_path(
    "CONFIG_DIR",
    default=str(_BASE_DIR / "config")
) or _BASE_DIR / "config"

USER_HOME: Optional[Path] = _get_path("USER_HOME") or Path.home()

# ── Safety Settings ───────────────────────────────────────

CONFIRM_DANGEROUS: bool = _get_bool(
    "CONFIRM_DANGEROUS",
    default=True
)

ENABLE_AUDIT_LOG: bool = _get_bool(
    "ENABLE_AUDIT_LOG",
    default=True
)

SAFETY_ENABLED: bool = _get_bool(
    "SAFETY_ENABLED",
    default=True
)

# ── Logging Settings ──────────────────────────────────────

LOG_LEVEL: str = _get_str(
    "LOG_LEVEL",
    default="INFO"
)
if LOG_LEVEL.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
    print(f"[SETTINGS] LOG_LEVEL={LOG_LEVEL!r} invalid. Using INFO.")
    LOG_LEVEL = "INFO"

# ── Optional Integration Keys ─────────────────────────────

WEATHER_API_KEY: str = _get_str("WEATHER_API_KEY", default="")
NEWS_API_KEY: str = _get_str("NEWS_API_KEY", default="")
HF_TOKEN: str = _get_str("HF_TOKEN", default="")

# Set HuggingFace token in environment if provided
# so HF libraries pick it up automatically
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN

# ── User Profile Settings ─────────────────────────────────

USER_NAME: str = _get_str(
    "USER_NAME",
    default="User"
)

# ── Advanced Features ─────────────────────────────────────

ENABLE_SKILLS: bool = _get_bool(
    "ENABLE_SKILLS",
    default=True
)

ENABLE_PLANNING: bool = _get_bool(
    "ENABLE_PLANNING",
    default=True
)

ENABLE_REFLECTION: bool = _get_bool(
    "ENABLE_REFLECTION",
    default=True
)

VOICE_ENABLED: bool = _get_bool(
    "VOICE_ENABLED",
    default=False
)

MODE: str = _get_str(
    "MODE",
    default="agent"
)
if MODE not in ("chat", "agent"):
    print(f"[SETTINGS] MODE={MODE!r} invalid. Must be chat or agent. Using agent.")
    MODE = "agent"

# ── Backwards compatibility aliases ───────────────────────
# For code that still references config dict keys

DEFAULT_CONFIG = {
    'ollama_cloud_url': OLLAMA_CLOUD_URL,
    'ollama_local_url': OLLAMA_LOCAL_URL,
    'model': OLLAMA_MODEL,
    'ollama_api_key': OLLAMA_API_KEY,
    'fallback_to_local': FALLBACK_TO_LOCAL,
    'max_retries': OLLAMA_MAX_RETRIES,
    'llm_timeout': OLLAMA_TIMEOUT,
    'conversation_history_limit': CONVERSATION_HISTORY_LIMIT,
    'tts_enabled': TTS_ENABLED,
    'tts_engine': TTS_ENGINE,
    'tts_voice': KOKORO_VOICE,
    'tts_speed': KOKORO_SPEED,
    'stt_engine': STT_ENGINE,
    'stt_language': STT_LANGUAGE,
    'wake_word_enabled': WAKE_WORD_ENABLED,
    'wake_word_model': WAKE_WORD,
    'wake_word_threshold': WAKE_WORD_THRESHOLD,
    'working_memory_max_messages': WORKING_MEMORY_MAX_MESSAGES,
    'working_memory_max_tokens': WORKING_MEMORY_MAX_TOKENS,
    'memory_retrieval_limit': MEMORY_RETRIEVAL_LIMIT,
    'safety_enabled': SAFETY_ENABLED,
    'require_confirmation_for': ['shutdown_computer', 'restart_computer', 'delete_file', 'close_app'] if CONFIRM_DANGEROUS else [],
    'blocked_paths': ['C:\\\\Windows', 'C:\\\\Program Files', 'C:\\\\Program Files (x86)'],
    'data_dir': str(DATA_DIR),
    'log_dir': str(LOG_DIR),
    'config_dir': str(CONFIG_DIR),
    'log_level': LOG_LEVEL,
    'user_name': USER_NAME,
    'user_preferences': {},
    'user_routines': [],
    'mode': MODE,
    'voice_enabled': VOICE_ENABLED,
    'ambient_monitoring': AMBIENT_MONITORING,
    'health_check_interval': HEALTH_CHECK_INTERVAL,
    'enable_skills': ENABLE_SKILLS,
    'enable_planning': ENABLE_PLANNING,
    'enable_reflection': ENABLE_REFLECTION,
    'max_tool_iterations': MAX_TOOL_ITERATIONS,
}


# ── Startup Validation ────────────────────────────────────

def validate_settings() -> list:
    """
    Run at startup to catch configuration problems early.
    Returns list of warning messages.
    Raises EnvironmentError for critical missing config.
    """
    warnings = []
    
    # Critical — system cannot function without these
    if not OLLAMA_API_KEY and OLLAMA_MODE in ("cloud", "auto"):
        warnings.append(
            "OLLAMA_API_KEY not set — cloud LLM unavailable"
        )
    
    # TTS checks
    if TTS_ENGINE == "piper":
        if not Path(PIPER_EXE).exists() and not Path(PIPER_EXE + ".exe").exists():
            warnings.append(
                f"PIPER_EXE not found at {PIPER_EXE} — TTS will fail"
            )
        if not Path(PIPER_MODEL).exists():
            warnings.append(
                f"PIPER_MODEL not found at {PIPER_MODEL} — TTS will fail"
            )
    
    # Create directories that should exist
    for directory in [LOG_DIR, NOTES_DIR, REMINDERS_DIR, DATA_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    
    # Warn about optional missing keys
    if not WEATHER_API_KEY:
        warnings.append(
            "WEATHER_API_KEY not set — weather tool unavailable"
        )
    
    if not NEWS_API_KEY:
        warnings.append(
            "NEWS_API_KEY not set — news briefing skill unavailable"
        )
    
    return warnings


def print_settings_summary():
    """Print current settings at startup for verification."""
    print("─" * 50)
    print("JARVIS SETTINGS SUMMARY")
    print("─" * 50)
    print(f"LLM Mode:        {OLLAMA_MODE}")
    print(f"LLM Model:       {OLLAMA_MODEL}")
    print(f"Cloud URL:       {OLLAMA_CLOUD_URL}")
    print(f"Local URL:       {OLLAMA_LOCAL_URL}")
    print(f"API Key:         {'SET' if OLLAMA_API_KEY else 'NOT SET ⚠'}")
    print(f"TTS Engine:      {TTS_ENGINE}")
    print(f"TTS Voice:       {KOKORO_VOICE}")
    print(f"Wake Word:       {WAKE_WORD}")
    print(f"Continuous Mode: {CONTINUOUS_MODE}")
    print(f"Max History:     {MAX_HISTORY}")
    print(f"Max Rounds:      {MAX_AGENT_ROUNDS}")
    print(f"Audit Log:       {ENABLE_AUDIT_LOG}")
    print(f"Confirm Danger:  {CONFIRM_DANGEROUS}")
    print(f"Weather Key:     {'SET' if WEATHER_API_KEY else 'not set'}")
    print(f"News Key:        {'SET' if NEWS_API_KEY else 'not set'}")
    print("─" * 50)
