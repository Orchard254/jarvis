"""
Speech-to-Text: Google STT primary, local fallback.
Respects IS_SPEAKING mute flag to prevent acoustic feedback.
"""

import logging
import time

import settings
from settings import STT_LANGUAGE, STT_SAMPLE_RATE

logger = logging.getLogger(__name__)

try:
    import speech_recognition as sr

    _recognizer = sr.Recognizer()
    _stt_available = True
except ImportError:
    _stt_available = False
    logger.warning("SpeechRecognition not installed — STT disabled")

try:
    import whisper as _whisper_lib

    _whisper_available = True
except ImportError:
    _whisper_available = False


def listen(timeout: float = 5.0) -> str:
    """
    Listen for speech and return transcribed text.
    Returns empty string if no speech detected or if IS_SPEAKING is True.
    """
    if settings.IS_SPEAKING.is_set():
        logger.debug("STT muted — system is speaking")
        return ""
    if not _stt_available:
        return ""
    try:
        with sr.Microphone(
            sample_rate=STT_SAMPLE_RATE,
            device_index=settings.MIC_DEVICE if settings.MIC_DEVICE != -1 else None,
        ) as source:
            # Shorten adjustment time to be more responsive
            _recognizer.adjust_for_ambient_noise(source, duration=0.2)
            # Increase sensitivity slightly if needed, but adjust_for_ambient_noise 
            # usually handles it. We can also manually set dynamic_energy_threshold.
            _recognizer.dynamic_energy_threshold = True
            
            audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
            text = _recognizer.recognize_google(audio, language=STT_LANGUAGE)
            logger.info(f"STT: '{text}'")
            return text.strip()
    except sr.WaitTimeoutError:
        logger.debug("STT: no speech detected")
    except sr.UnknownValueError:
        logger.warning("STT: could not understand audio")
    except sr.RequestError as e:
        logger.error(f"STT: Google API error — {e}. Trying local Whisper fallback...")
        return _whisper_fallback(audio)
    except Exception as e:
        logger.error(f"STT: unexpected error — {e}")
    return ""


def _whisper_fallback(audio) -> str:
    """
    Transcribe audio using local OpenAI Whisper model.
    Uses the 'tiny' model for speed. Requires: pip install openai-whisper
    """
    if not _whisper_available:
        logger.debug("STT: Whisper not installed — skipping fallback")
        return ""
    import os
    import tempfile

    tmp_path = None
    try:
        wav_bytes = audio.get_wav_data()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name
        model = _whisper_lib.load_model("tiny")
        result = model.transcribe(tmp_path, language=None, fp16=False)
        text = (result.get("text") or "").strip()
        if text:
            logger.info(f"STT(whisper): '{text}'")
        return text
    except Exception as exc:
        logger.error(f"STT: Whisper fallback failed — {exc}")
        return ""
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def transcribe_once(timeout: float = 10.0) -> str:
    """
    Single-shot capture: record one utterance and return the transcribed text.

    Unlike `listen()`, this function is intended for use by the `listen` tool
    which takes STT_EXCLUSIVE control of the mic.  It does NOT check IS_SPEAKING
    (the caller is responsible for mic arbitration) but it does honour the
    _stt_available guard.

    Returns empty string on failure / silence.
    """
    if not _stt_available:
        logger.warning("transcribe_once: SpeechRecognition not available")
        return ""
    try:
        with sr.Microphone(
            sample_rate=STT_SAMPLE_RATE,
            device_index=settings.MIC_DEVICE if settings.MIC_DEVICE != -1 else None,
        ) as source:
            _recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=15)

        # Try Google first
        try:
            text = _recognizer.recognize_google(audio, language=STT_LANGUAGE)
            logger.info(f"transcribe_once (google): '{text}'")
            return text.strip()
        except sr.RequestError:
            logger.warning("transcribe_once: Google API error — trying Whisper fallback")
            return _whisper_fallback(audio)
        except sr.UnknownValueError:
            logger.debug("transcribe_once: unintelligible audio")
            return ""
    except sr.WaitTimeoutError:
        logger.debug("transcribe_once: timeout — no speech detected")
        return ""
    except Exception as exc:
        logger.error(f"transcribe_once: unexpected error — {exc}")
        return ""
