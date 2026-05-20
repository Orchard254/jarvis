"""Autonomous mode, ambient monitoring, indexing, skills, and task queue settings."""

from settings._helpers import get_env_str, get_env_float, get_env_int, get_env_bool

AUTONOMOUS_CONFIDENCE_THRESHOLD = get_env_float("AUTONOMOUS_CONFIDENCE_THRESHOLD", 0.90)
AUTONOMOUS_TIMEOUT_SECONDS = get_env_int("AUTONOMOUS_TIMEOUT_SECONDS", 86400)
AUTONOMOUS_CLEANUP_DAYS = get_env_int("AUTONOMOUS_CLEANUP_DAYS", 7)

AUTONOMOUS_REQUIRE_APPROVAL = {
    "delete", "format", "shutdown", "restart", "uninstall",
    "send_email", "make_purchase",
}

# Ambient monitoring
BATTERY_WARN_THRESHOLD = get_env_int("BATTERY_WARN_THRESHOLD", 20)
BATTERY_CRITICAL_THRESHOLD = get_env_int("BATTERY_CRITICAL_THRESHOLD", 10)
CPU_SPIKE_THRESHOLD = get_env_int("CPU_SPIKE_THRESHOLD", 90)
CPU_SPIKE_DURATION = get_env_int("CPU_SPIKE_DURATION", 30)
MEMORY_WARN_THRESHOLD = get_env_int("MEMORY_WARN_THRESHOLD", 85)
DISK_WARN_THRESHOLD = get_env_int("DISK_WARN_THRESHOLD", 92)
IDLE_MINUTES = get_env_int("IDLE_MINUTES", 20)
MONITOR_INTERVAL = get_env_int("MONITOR_INTERVAL", 15)
HEALTH_CHECK_INTERVAL = get_env_int("HEALTH_CHECK_INTERVAL", 60)
AMBIENT_MONITORING = get_env_bool("AMBIENT_MONITORING", True)

# PC indexer
INDEX_REFRESH_APPS = get_env_int("INDEX_REFRESH_APPS", 14400)
INDEX_REFRESH_FILES = get_env_int("INDEX_REFRESH_FILES", 7200)
STATE_MONITOR_INTERVAL = get_env_int("STATE_MONITOR_INTERVAL", 10)
DB_WAL_MODE = get_env_bool("DB_WAL_MODE", True)
DB_BUSY_TIMEOUT = get_env_int("DB_BUSY_TIMEOUT", 5000)
INDEX_FILE_DIRS = ["~/Documents", "~/Downloads", "~/Desktop", "~/Pictures", "~/Videos"]
REGISTRY_UNINSTALL_PATHS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
]

# Skill store
SKILL_MATCH_THRESHOLD = get_env_float("SKILL_MATCH_THRESHOLD", 0.75)
SKILL_CANDIDATE_CAP = get_env_int("SKILL_CANDIDATE_CAP", 50)
ENABLE_SKILLS = get_env_bool("ENABLE_SKILLS", True)

# Agent config
MAX_HISTORY = get_env_int("MAX_HISTORY", 10)
MAX_AGENT_ROUNDS = get_env_int("MAX_AGENT_ROUNDS", 12)
MAX_TOOL_ITERATIONS = get_env_int("MAX_TOOL_ITERATIONS", 5)
AGENT_MODE = get_env_str("AGENT_MODE", "agent")
MODE = get_env_str("MODE", "agent")
FALLBACK_TO_LOCAL = get_env_bool("FALLBACK_TO_LOCAL", True)
CONVERSATION_HISTORY_LIMIT = get_env_int("CONVERSATION_HISTORY_LIMIT", 20)
CONVERSATION_MESSAGE_MAX_CHARS = get_env_int("CONVERSATION_MESSAGE_MAX_CHARS", 4000)
LOAD_CONVERSATION_HISTORY = get_env_bool("LOAD_CONVERSATION_HISTORY", True)
JARVIS_ATTACH_TOOL_SCHEMAS = get_env_bool("JARVIS_ATTACH_TOOL_SCHEMAS", False)

# Memory
WORKING_MEMORY_MAX_MESSAGES = get_env_int("WORKING_MEMORY_MAX_MESSAGES", 20)
WORKING_MEMORY_MAX_TOKENS = get_env_int("WORKING_MEMORY_MAX_TOKENS", 4000)
MEMORY_RETRIEVAL_LIMIT = get_env_int("MEMORY_RETRIEVAL_LIMIT", 5)

# Auto-learner
ENABLE_AUTO_LEARNER = get_env_bool("ENABLE_AUTO_LEARNER", True)
AUTO_LEARNER_IDLE_MINUTES = get_env_int("AUTO_LEARNER_IDLE_MINUTES", 5)
AUTO_LEARNER_INTERVAL_MINUTES = get_env_int("AUTO_LEARNER_INTERVAL_MINUTES", 15)

# Tool stage
TOOL_STAGE = get_env_int("TOOL_STAGE", 4)
