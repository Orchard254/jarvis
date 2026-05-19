"""Safety, sandboxing, confidence, and verification settings."""

from settings._helpers import get_env_int, get_env_float, get_env_str, get_env_bool

EXECUTE_CODE_TIMEOUT = get_env_int("EXECUTE_CODE_TIMEOUT", 30)
MAX_RAM_PERCENT = get_env_int("MAX_RAM_PERCENT", 85)
TOOL_RETRY_LIMITS = {
    "execute_code": get_env_int("EXECUTE_CODE_RETRIES", 3),
}

CONFIRM_DANGEROUS = get_env_bool("CONFIRM_DANGEROUS", True)
ENABLE_AUDIT_LOG = get_env_bool("ENABLE_AUDIT_LOG", True)
SAFETY_ENABLED = get_env_bool("SAFETY_ENABLED", True)

CONFIDENCE_THRESHOLD = get_env_float("CONFIDENCE_THRESHOLD", 0.70)
VERIFICATION_MODE = get_env_str("VERIFICATION_MODE", "state_first")
VERIFICATION_TIMEOUT = get_env_int("VERIFICATION_TIMEOUT", 3)
MAX_VERIFICATION_RETRIES = get_env_int("MAX_VERIFICATION_RETRIES", 2)

ALLOWED_IMPORTS = {
    "os", "pathlib", "shutil", "glob", "tools", "pkgutil", "webbrowser",
    "tempfile", "json", "csv", "re", "datetime", "time", "collections",
    "itertools", "functools", "copy", "psutil", "win32gui", "win32con",
    "win32api", "win32process", "pyautogui", "PIL", "requests", "pytesseract",
    "sqlite3", "hashlib", "base64", "uuid", "logging", "math", "string",
    "textwrap", "difflib", "sys", "winreg", "threading", "socket", "urllib",
    "http", "io", "struct", "platform", "signal", "queue", "traceback",
    "pyperclip", "win32clipboard", "win32ui", "win32pdh", "comtypes",
    "pythoncom", "mss", "cv2", "numpy", "imagegrab", "selenium", "webdriver",
    "bs4", "lxml", "pycaw", "pycaw.pycaw", "docx", "xlsxwriter", "openpyxl",
    "pdf2image", "PyPDF2", "wave", "audioop", "pyaudio", "speech_recognition",
    "yaml", "toml", "xml", "html", "zipfile", "tarfile", "gzip", "bz2",
    "ftplib", "poplib", "imaplib", "smtplib", "email", "asyncio", "aiohttp",
    "inspect", "ast", "concurrent", "contextlib", "skills", "icalendar",
    "win32com", "zoneinfo", "tzlocal", "pygetwindow", "reportlab", "exchangelib",
    "playwright", "spacy", "nltk", "tqdm", "rich", "colorama", "dotenv",
    "python_pptx", "fitz", "scipy", "matplotlib", "skimage", "sounddevice",
    "soundfile", "pandas", "sqlalchemy", "chardet", "dateutil", "shlex",
    "warnings", "unittest", "typing", "dataclasses", "enum", "abc", "weakref",
    "types", "pprint", "random", "statistics", "decimal", "fractions", "array",
    "bisect", "heapq", "configparser", "mimetypes", "binascii", "hmac",
    "secrets", "unicodedata", "codecs", "fnmatch", "linecache", "locale",
    "gettext", "getpass", "numbers", "win32event", "win32service", "win32file", "win32pipe",
    "win32security", "win32net", "win32print",
}

BLOCKED_PATHS = [
    "C:/Windows/System32",
    "C:/Windows/SysWOW64",
    "C:/Windows/Boot",
]
