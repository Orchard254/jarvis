"""
JARVIS Perception Module - Speech-to-text, wake word detection, vision, and intent classification.
"""

from .stt import SpeechToText, get_stt, transcribe_speech, STTResult
from .vision import VisionAnalyzer, get_vision_analyzer
from .intent_classifier import IntentClassifier, get_intent_classifier

# Lazy import for wake word to avoid audio hardware dependency at import time
def __getattr__(name):
    if name in ('WakeWordDetection', 'get_wake_word_detection', 'start_wake_word_detection', 'stop_wake_word_detection'):
        from . import wake_word
        return getattr(wake_word, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'SpeechToText',
    'get_stt',
    'transcribe_speech',
    'STTResult',
    'VisionAnalyzer',
    'get_vision_analyzer',
    'IntentClassifier',
    'get_intent_classifier'
]
