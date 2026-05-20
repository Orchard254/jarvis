"""Voice I/O, TTS, STT, and wake-word configuration."""

import threading
from settings._helpers import get_env_str, get_env_float, get_env_int, get_env_bool

WAKE_WORD = get_env_str("WAKE_WORD", "hey_jarvis")
WAKE_WORD_THRESHOLD = get_env_float("WAKE_WORD_THRESHOLD", 0.45)
WAKE_WORD_COOLDOWN = get_env_float("WAKE_WORD_COOLDOWN", 3.0)
WAKE_WORD_POST_TTS_DRAIN = get_env_float("WAKE_WORD_POST_TTS_DRAIN", 1.0)
WAKE_WORD_ENABLED = get_env_bool("WAKE_WORD_ENABLED", True)
CONTINUOUS_MODE = get_env_bool("CONTINUOUS_MODE", False)

TTS_ENGINE = get_env_str("TTS_ENGINE", "edge")
TTS_ENABLED = get_env_bool("TTS_ENABLED", True)
VOICE_ENABLED = get_env_bool("VOICE_ENABLED", False)
DESKTOP_TOAST_ENABLED = get_env_bool("DESKTOP_TOAST_ENABLED", False)

# Edge TTS
EDGE_TTS_VOICE = get_env_str("EDGE_TTS_VOICE", "en-US-JennyNeural")
EDGE_TTS_RATE = get_env_str("EDGE_TTS_RATE", "+0%")
EDGE_TTS_VOLUME = get_env_str("EDGE_TTS_VOLUME", "+0%")
EDGE_TTS_PITCH = get_env_str("EDGE_TTS_PITCH", "+0Hz")
EDGE_TTS_TIMEOUT = get_env_int("EDGE_TTS_TIMEOUT", 15)

# Piper TTS
PIPER_BINARY = get_env_str("PIPER_EXE", "piper.exe")
PIPER_MODEL = get_env_str("PIPER_MODEL", "en_US-lessac-medium.onnx")
PIPER_MODEL_JSON = get_env_str("PIPER_MODEL_JSON", "en_US-lessac-medium.onnx.json")

# Kokoro TTS
KOKORO_VOICE = get_env_str("KOKORO_VOICE", "bm_george")
KOKORO_LANG_CODE = get_env_str("KOKORO_LANG_CODE", "a")
KOKORO_SPEED = get_env_float("KOKORO_SPEED", 1.15)

# STT
STT_ENGINE = get_env_str("STT_ENGINE", "google")
STT_LANGUAGE = get_env_str("STT_LANGUAGE", "en-US")
STT_SAMPLE_RATE = get_env_int("SAMPLE_RATE", 16000)
MIC_DEVICE = get_env_int("MIC_DEVICE", -1)
AUDIO_DEVICE = get_env_int("AUDIO_DEVICE", -1)
SILENCE_THRESHOLD = get_env_int("SILENCE_THRESHOLD", 400)
SILENCE_DURATION = get_env_float("SILENCE_DURATION", 1.5)
MAX_RECORD_SECS = get_env_int("MAX_RECORD_SECS", 30)

IS_SPEAKING = threading.Event()
STT_EXCLUSIVE = threading.Event()
