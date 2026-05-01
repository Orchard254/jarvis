# tts.py — TTS wrapper with Edge-TTS (Azure Neural) support

# Suppress warnings before any imports
import os

os.environ.setdefault("HF_TOKEN", "dummy")  # Suppress HF Hub unauthenticated warning

import warnings as _warnings

_warnings.filterwarnings("ignore", category=UserWarning)
_warnings.filterwarnings("ignore", category=FutureWarning)
_warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")
_warnings.filterwarnings("ignore", message=".*Defaulting repo_id.*")
_warnings.filterwarnings("ignore", message=".*words count mismatch.*")

import logging as _logging

_logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
_logging.getLogger("torch").setLevel(_logging.ERROR)
_logging.getLogger("phonemizer").setLevel(_logging.ERROR)

import asyncio
import queue
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave

import numpy as np
import sounddevice as sd

import config
from logger import get_logger

log = get_logger("tts")

# Edge-TTS state
_edge_tts_available = False
try:
    import edge_tts
    _edge_tts_available = True
    log.info("Edge-TTS library loaded successfully")
except ImportError:
    log.warning("edge-tts not installed. Run: pip install edge-tts")

# Edge-TTS Configuration
EDGE_TTS_VOICE = "en-US-ChristopherNeural"  # Male voice (clear, professional)
# Alternative voices:
# Female: "en-US-JennyNeural", "en-US-AriaNeural"
# Male: "en-US-GuyNeural", "en-US-DavisNeural"
EDGE_TTS_RATE = "+0%"  # Speech rate (+/- percentage)
EDGE_TTS_VOLUME = "+0%"  # Volume (+/- percentage)
EDGE_TTS_PITCH = "+0Hz"  # Pitch shift (+/- Hz)

PAUSE_SHORT = 0.08  # 80ms between short sentences
PAUSE_MEDIUM = 0.15  # 150ms between medium
PAUSE_LONG = 0.25  # 250ms between paragraphs
MAX_TTS_LENGTH = 300  # Maximum characters for any single TTS chunk


def play_chime():
    """Play a short double-beep to confirm wake word detection."""
    rate = 22050
    for freq in (880, 1108):
        t = np.linspace(0, 0.18, int(rate * 0.18), False)
        wave_data = (np.sin(2 * np.pi * freq * t) * 0.9 * 32767).astype(np.int16)
        sd.play(wave_data, samplerate=rate, device=config.AUDIO_DEVICE)
        sd.wait()


def play_think_chime():
    """Soft chime to indicate thinking - not too jarring."""
    rate = 22050
    freqs = [440, 554, 659]  # A4, C#5, E5 - gentle major chord
    for i, freq in enumerate(freqs):
        t = np.linspace(0, 0.08, int(rate * 0.08), False)
        wave_data = (np.sin(2 * np.pi * freq * t) * 0.3 * 32767).astype(np.int16)
        sd.play(wave_data, samplerate=rate, device=config.AUDIO_DEVICE)
        sd.wait()
        time.sleep(0.05)


def _get_piper_exe():
    """Return platform-appropriate Piper executable path."""
    if sys.platform == "win32" and not config.PIPER_EXE.endswith(".exe"):
        return config.PIPER_EXE + ".exe"
    return config.PIPER_EXE


async def _synthesize_edge_tts_to_mp3(text: str) -> str:
    """Synthesize text using Edge-TTS. Returns MP3 file path."""
    if not _edge_tts_available:
        log.error("Edge-TTS not available")
        return None
    
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    
    try:
        communicate = edge_tts.Communicate(
            text, 
            voice=EDGE_TTS_VOICE,
            rate=EDGE_TTS_RATE,
            volume=EDGE_TTS_VOLUME,
            pitch=EDGE_TTS_PITCH
        )
        await communicate.save(tmp.name)
        
        # Verify file was created and has content
        if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 0:
            return tmp.name
        else:
            log.error("Edge-TTS generated empty file")
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            return None
    except Exception as e:
        log.error(f"Edge-TTS synthesis error: {e}")
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return None


def _synthesize_to_wav(text: str) -> str:
    """Synthesize text to audio file using configured TTS engine. Returns file path."""
    if _edge_tts_available:
        # Use Edge-TTS (async)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mp3_path = loop.run_until_complete(_synthesize_edge_tts_to_mp3(text))
            if mp3_path:
                # Convert MP3 to WAV for playback compatibility
                wav_path = mp3_path.replace('.mp3', '.wav')
                try:
                    # Try to use pydub for conversion if available
                    from pydub import AudioSegment
                    sound = AudioSegment.from_mp3(mp3_path)
                    sound.export(wav_path, format="wav")
                    os.unlink(mp3_path)  # Remove MP3
                    return wav_path
                except ImportError:
                    # If pydub not available, just rename MP3 to WAV (won't work perfectly but avoids crash)
                    # Better: use subprocess with ffmpeg if available
                    try:
                        subprocess.run(
                            ['ffmpeg', '-i', mp3_path, wav_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=True
                        )
                        os.unlink(mp3_path)
                        return wav_path
                    except:
                        # Last resort: return MP3 path, _play_wav will try to handle it
                        log.warning("Returning MP3 directly (install pydub or ffmpeg for WAV conversion)")
                        return mp3_path
        finally:
            loop.close()
        return None
    else:
        # Fallback to Piper if Edge-TTS not available
        return _synthesize_piper_to_wav(text)


def _synthesize_piper_to_wav(text: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    try:
        subprocess.run(
            [
                _get_piper_exe(),
                "--model",
                config.PIPER_MODEL,
                "--output_file",
                tmp.name,
            ],
            input=text.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        return tmp.name
    except subprocess.TimeoutExpired:
        log.error("TTS synthesis timeout")
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return None
    except subprocess.CalledProcessError as e:
        log.error(f"Piper error: {e}")
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return None
    except FileNotFoundError:
        log.error(f"Piper not found at {_get_piper_exe()}")
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return None


def _play_wav(wav_path: str):
    """Play WAV file through speakers."""
    try:
        with wave.open(wav_path, "rb") as w:
            frames = w.readframes(w.getnframes())
            rate = w.getframerate()

        audio = np.frombuffer(frames, dtype=np.int16)
        sd.play(audio, samplerate=rate, device=config.AUDIO_DEVICE)
        sd.wait()
    except Exception as e:
        log.error(f"Playback error: {e}")


def _split_for_speech(text: str) -> list:
    """Split text into natural speech chunks with pauses."""
    if not text or not text.strip():
        return []

    processed_text = text

    # Handle common abbreviations and units - protect with marker
    processed_text = re.sub(
        r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|i\.e|e\.g|U\.S|U\.K)\.", r"\1<ABDOT>", processed_text
    )
    processed_text = re.sub(
        r"\b(IP|CPU|RAM|GHz|GB|MB)\b", r"<ABDOT>\1", processed_text, flags=re.IGNORECASE
    )
    processed_text = re.sub(r"\b(percent)\b", "<PERCENT>", processed_text, flags=re.IGNORECASE)

    # Split on sentence endings
    sentences = []
    current = ""
    i = 0
    while i < len(processed_text):
        char = processed_text[i]
        current += char

        # Check for sentence-ending punctuation
        if char in ".!?" and len(current) > 2:
            # Check if this could be a decimal dot (digit.digit or digit.digit with space)
            is_decimal = False
            if char == ".":
                # Check if preceded by digit or space+digit and followed by digit or space+digit
                before_idx = len(current) - 2
                before = current[before_idx] if before_idx >= 0 else ""
                if before == " " and before_idx > 0:
                    before = current[before_idx - 1]
                after_idx = i + 1
                after = processed_text[after_idx] if after_idx < len(processed_text) else ""
                if before.isdigit() and after.isdigit():
                    is_decimal = True
                # Also check for "0. 0" pattern (digit space digit - not a sentence end)
                if (
                    before.isdigit()
                    and after == " "
                    and i + 2 < len(processed_text)
                    and processed_text[i + 2].isdigit()
                ):
                    is_decimal = True

            if not is_decimal:
                # Check if followed by space/tab/newline (likely sentence end)
                next_idx = i + 1
                if next_idx >= len(processed_text) or processed_text[next_idx] in " \n\t":
                    sentences.append(current.strip())
                    current = ""

        # Comma splits - brief pause
        elif char in ",;:—–" and len(current) > 3:
            sentences.append(current.strip())
            current = ""

        i += 1

    # Add remaining
    if current.strip():
        sentences.append(current.strip())

    # Restore all protected markers
    sentences = [s.replace("<ABDOT>", ".").replace("<PERCENT>", "percent") for s in sentences]
    # Clean up any leading dots from abbreviation processing
    sentences = [s.lstrip(". ") for s in sentences]

    # Filter empty and very short fragments
    return [s for s in sentences if s.strip() and len(s.strip()) > 1]


def _format_for_speech(text: str) -> str:
    """Format text for better TTS readability with enhanced conversational qualities."""
    if not text:
        return ""

    text = text.strip()

    # Expand URLs to be more spoken-friendly
    text = re.sub(r"https?://\S+", lambda m: _expand_url(m.group()), text)

    # Convert backslashes to forward slashes for better pronunciation
    text = re.sub(r"\\+", "/", text)

    # Expand file paths to be more spoken naturally
    text = re.sub(r"([A-Z]:\\|/[\w/]+(?:\\[\w./]+)+)", _expand_path, text)

    # Expand numbers to be spoken naturally (e.g., "1000" -> "one thousand")
    text = re.sub(r"\b(\d+(?:[.,]\d+)?)\b", _expand_numbers, text)

    # Split camelCase and PascalCase words for better pronunciation
    text = re.sub(r"\b([A-Z][a-z]+)([A-Z]\w+)\b", lambda m: f"{m.group(1)} {m.group(2)}", text)

    # Replace underscores with spaces
    text = re.sub(r"_", " ", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    # Add conversational enhancements
    text = _add_conversational_flow(text)

    return text.strip()


def _add_conversational_flow(text: str) -> str:
    """Add conversational flow elements to make TTS sound more natural."""
    if not text:
        return ""

    # Add natural pauses and emphasis for better rhythm
    # Mark places where natural pauses would occur
    text = re.sub(r"([.!?])\s+", r"\1\n", text)  # Add newlines after sentences for pausing

    # Convert some technical phrasing to more conversational
    conversational_replacements = {
        r"\b(is running)\b": "is currently running",
        r"\b(is active)\b": "is currently active",
        r"\b(is not available)\b": "is not currently available",
        r"\bat\s+(\d+)\s*percent\b": r"at \1 percent",
    }

    for pattern, replacement in conversational_replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def _expand_url(url: str) -> str:
    domain = re.sub(r"https?://", "", url)
    domain = domain.split("/")[0]
    return f"link to {domain}"


def _expand_path(path: str) -> str:
    path = re.sub(r"\\+", "/", path)
    parts = [p for p in path.replace(":", "").split("/") if p and p != "/"]
    return " ".join(parts) if parts else path


def _expand_numbers(match: str) -> str:
    num = match.group(1).replace(",", ".")
    try:
        val = float(num)
        if val >= 1000:
            if val >= 1000000:
                return f"{val/1000000:.1f} million"
            return f"{val/1000:.1f} thousand"
        elif val == int(val):
            return str(int(val))
        return f"{val:.2f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return match.group(1)


def read_aloud(content: str, max_chars: int = 500):
    """Read file content aloud with paragraph formatting."""
    if not content:
        return

    content = _format_for_speech(content)

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]

    for para in paragraphs:
        if len(para) > max_chars:
            para = para[:max_chars].rsplit(" ", 1)[0].rstrip(",:;.") + "..."

        if para:
            speak(para)
            time.sleep(0.3)


def speak(text: str):
    """Synthesize text and play it through speakers (blocking) with natural pacing."""
    if not text or not text.strip():
        return

    try:
        import wake_word

        wake_word.reset_cooldown()
    except (ImportError, AttributeError):
        pass

    text = _format_for_speech(text)
    chunks = _split_for_speech(text)

    for i, chunk in enumerate(chunks):
        wav_path = _synthesize_to_wav(chunk)
        if not wav_path:
            continue

        try:
            _play_wav(wav_path)
        finally:
            if os.path.exists(wav_path):
                try:
                    os.unlink(wav_path)
                except OSError as e:
                    log.warning(f"Failed to delete temp file {wav_path}: {e}")

        # Natural pause between chunks
        if i < len(chunks) - 1:
            if chunk.endswith("!") or chunk.endswith("?"):
                time.sleep(PAUSE_LONG)
            elif chunk.endswith("."):
                time.sleep(PAUSE_MEDIUM)
            else:
                time.sleep(PAUSE_SHORT)


class TTSQueue:
    """Thread-safe TTS queue for non-blocking playback with natural pacing."""

    def __init__(self):
        self._queue = queue.Queue()
        self._stop_flag = False
        self._thread = None

    def start(self):
        """Start the background TTS worker thread."""
        self._stop_flag = False
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the worker thread to stop and wait for it."""
        self._stop_flag = True
        self._queue.put(None)  # Sentinel to wake up thread
        if self._thread:
            self._thread.join(timeout=2)

    def put(self, text: str):
        """Add text to the playback queue."""
        if not self._stop_flag:
            text = _format_for_speech(text)
            chunks = _split_for_speech(text)
            for chunk in chunks:
                self._queue.put(chunk)

    def join(self):
        """Wait for all queued items to finish playing."""
        self._queue.join()

    def _worker(self):
        """Background worker that processes the queue with natural pacing."""
        while not self._stop_flag:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if item is None:
                    return
                if item:
                    try:
                        import wake_word

                        wake_word.reset_cooldown()
                    except (ImportError, AttributeError):
                        pass

                    wav_path = _synthesize_to_wav(item)
                    if wav_path:
                        _play_wav(wav_path)
                        try:
                            os.unlink(wav_path)
                        except OSError:
                            pass

                    # Small pause between items for natural flow
                    if item.endswith("!") or item.endswith("?"):
                        time.sleep(PAUSE_LONG)
                    elif item.endswith("."):
                        time.sleep(PAUSE_MEDIUM)
                    else:
                        time.sleep(PAUSE_SHORT)

            except Exception as e:
                log.error(f"TTS Queue error: {e}")
            finally:
                self._queue.task_done()
