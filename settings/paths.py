"""File-system path configuration."""

from pathlib import Path
from settings._helpers import BASE_DIR, get_env_str

DATA_DIR = BASE_DIR / get_env_str("DATA_DIR", "data")
LOGS_DIR = BASE_DIR / get_env_str("LOG_DIR", "logs")
SKILLS_DB = BASE_DIR / "skills" / "db" / "skills.db"
SKILLS_CHROMA = BASE_DIR / "skills" / "db" / "chroma"
PC_INDEX_DB = BASE_DIR / "indexer" / "db" / "pc_index.db"
MEMORY_DB = BASE_DIR / "memory" / "db" / "memory.db"
NOTES_DIR = BASE_DIR / get_env_str("NOTES_DIR", "notes")
REMINDERS_DIR = BASE_DIR / get_env_str("REMINDERS_DIR", "reminders")
CONFIG_DIR = BASE_DIR / get_env_str("CONFIG_DIR", "config")
