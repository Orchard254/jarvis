"""Logging configuration."""

from settings._helpers import get_env_str
from settings.paths import LOGS_DIR

LOG_FILE = LOGS_DIR / "jarvis.log"
LOG_LEVEL = get_env_str("LOG_LEVEL", "INFO")
