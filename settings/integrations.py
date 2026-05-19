"""Optional integrations: messaging, calendar, weather, news, user profile."""

from settings._helpers import get_env_str, get_env_int

WEATHER_API_KEY = get_env_str("WEATHER_API_KEY", "")
NEWS_API_KEY = get_env_str("NEWS_API_KEY", "")
HF_TOKEN = get_env_str("HF_TOKEN", "")
USER_NAME = get_env_str("USER_NAME", "User")

# Outbound messaging (send_message tool)
SMTP_HOST = get_env_str("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = get_env_int("SMTP_PORT", 587)
SMTP_USER = get_env_str("SMTP_USER", "")
SMTP_PASS = get_env_str("SMTP_PASS", "")
SMTP_FROM = get_env_str("SMTP_FROM", "")
TELEGRAM_BOT_TOKEN = get_env_str("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = get_env_str("TELEGRAM_CHAT_ID", "")

# Calendar (time_calendar tool)
CALENDAR_BACKEND = get_env_str("CALENDAR_BACKEND", "outlook")
ICS_CALENDAR_PATH = get_env_str("ICS_CALENDAR_PATH", "")
