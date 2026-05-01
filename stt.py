# stt.py — Whisper STT with noise reduction + WebRTC VAD

import os
import tempfile
import wave

import numpy as np
import sounddevice as sd
import speech_recognition as sr
import noisereduce as nr
import webrtcvad

import config
from logger import get_logger

log = get_logger("stt")

# Try to import Whisper for better accuracy in noisy environments
try:
    import whisper
    WHISPER_AVAILABLE = True
    log.info("[STT] Whisper library available for enhanced accuracy")
except ImportError:
    WHISPER_AVAILABLE = False
    log.warning("[STT] Whisper not installed. For better accuracy run: pip install openai-whisper")


class ImprovedVAD:
    """WebRTC VAD for robust voice activity detection in noisy environments."""
    
    def __init__(self, sample_rate=16000, aggression=2):
        """
        Args:
            sample_rate: Audio sample rate (must be 8000, 16000, 32000, or 48000)
            aggression: VAD aggressiveness 0-3 (higher = more aggressive filtering)
        """
        self.vad = webrtcvad.Vad(aggression)
        self.sample_rate = sample_rate
        self.frame_duration_ms = 30
        self.frame_size = int(sample_rate * self.frame_duration_ms / 1000)
    
    def is_speech(self, frame):
        """Check if a frame contains speech. Frame must be 16-bit mono."""
        try:
            return self.vad.is_speech(frame, self.sample_rate)
        except Exception:
            # Fallback for invalid frames
            return False
    
    def has_speech(self, audio_data, sample_rate):
        """Check if audio segment contains any speech."""
        # Resample if needed for WebRTC (must be 8k/16k/32k/48k)
        if sample_rate != self.sample_rate:
            # Simple decimation for conversion to target sample rate
            ratio = sample_rate // self.sample_rate
            if ratio > 1 and len(audio_data) % ratio == 0:
                audio_data = audio_data[::ratio].astype(np.int16)
            else:
                return False
        
        # Check multiple frames throughout the audio
        num_frames = len(audio_data) // self.frame_size
        if num_frames == 0:
            return False
        
        # Sample frames at regular intervals
        step = max(1, num_frames // 10)
        speech_count = 0
        for i in range(0, num_frames, step):
            start = i * self.frame_size
            end = start + self.frame_size
            frame = audio_data[start:end].tobytes()
            if self.is_speech(frame):
                speech_count += 1
        
        # Consider it speech if >30% of frames contain speech
        return speech_count > (num_frames // step) * 0.3


def _reduce_noise(audio_data, sample_rate):
    """Apply noise reduction using spectral gating."""
    try:
        # Convert to float32 normalized [-1, 1]
        audio_float = audio_data.astype(np.float32) / 32768.0
        
        # Apply noise reduction
        reduced = nr.reduce_noise(
            y=audio_float,
            sr=sample_rate,
            prop_decrease=0.75,  # Reduce noise by 75%
            stationary=True,     # Assume stationary noise (fan, AC, etc.)
            n_std_thresh_stationary=1.5,  # Sensitivity to noise changes
        )
        
        # Convert back to int16
        return (np.clip(reduced, -1.0, 1.0) * 32768.0).astype(np.int16)
    except Exception as e:
        log.warning(f"[STT] Noise reduction failed: {e}, using original audio")
        return audio_data


def _normalize_audio(audio_data, target_dbfs=-20):
    """Normalize audio levels using RMS-based normalization."""
    try:
        from pydub import AudioSegment
        import io
        
        # Convert numpy array to AudioSegment
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(config.SAMPLE_RATE)
            w.writeframes(audio_data.tobytes())
        wav_io.seek(0)
        
        audio = AudioSegment.from_wav(wav_io)
        
        # Normalize to target dBFS
        normalized = audio.normalize(headroom=0.1)
        
        # Convert back to numpy array
        samples = np.array(normalized.get_array_of_samples(), dtype=np.int16)
        return samples
    except Exception as e:
        log.warning(f"[STT] Audio normalization failed: {e}, using original audio")
        return audio_data


def _record_to_wav(max_seconds: float = None, apply_noise_reduction: bool = True) -> str:
    """Record from mic until silence, save to temp wav. Returns file path."""

    if config.MIC_DEVICE is None:
        log.error("[STT] No microphone device found!")
        return None

    if max_seconds is None:
        max_seconds = config.MAX_RECORD_SECS

    chunk_size = int(config.SAMPLE_RATE * 0.1)
    max_chunks = int(max_seconds / 0.1)
    silent_limit = int(config.SILENCE_DURATION / 0.1)

    log.debug("[STT] Listening...")

    audio_chunks = []
    silent_count = 0
    started = False
    max_amplitude = 0
    
    # Initialize WebRTC VAD (resample to 16kHz internally)
    vad = ImprovedVAD(sample_rate=16000, aggression=2)

    try:
        with sd.InputStream(
            samplerate=config.SAMPLE_RATE, channels=1, dtype="int16", device=config.MIC_DEVICE
        ) as stream:

            # Flush ~400 ms to discard wake-word tail AND any chime reverberation
            for _ in range(4):
                stream.read(chunk_size)

            # ── Adaptive noise-floor calibration (300 ms, 3 chunks) ────────────
            calibration = []
            for _ in range(3):
                cal_chunk, _ = stream.read(chunk_size)
                calibration.append(float(np.abs(cal_chunk.flatten()).mean()))
            noise_floor = float(np.median(calibration))
            # Use config floor so quiet mics aren't drowned out by the hardcoded minimum
            threshold = max(noise_floor * 1.5, config.STT_THRESHOLD_FLOOR)
            log.debug(f"Noise floor: {noise_floor:.1f}  ->  threshold: {threshold:.1f}")
            # ───────────────────────────────────────────────────────────────────

            for i in range(max_chunks):
                chunk, _ = stream.read(chunk_size)
                chunk = chunk.flatten()
                audio_chunks.append(chunk)

                amplitude = float(np.abs(chunk).mean())
                max_amplitude = max(max_amplitude, amplitude)

                if i % 10 == 0:
                    log.debug(f"Amplitude: {amplitude:.0f}  threshold: {threshold:.0f}")

                # Minimum recording time - don't stop too early (500ms = 5 chunks)
                if i < 5:
                    continue

                # Dual detection: amplitude + WebRTC VAD for robustness
                vad_speech = False
                if i >= 5:  # Only check VAD after minimum time
                    # Collect last 3 chunks (~300ms) for VAD analysis
                    recent_audio = np.concatenate(audio_chunks[-3:])
                    vad_speech = vad.has_speech(recent_audio, config.SAMPLE_RATE)

                if amplitude > threshold or vad_speech:
                    started = True
                    silent_count = 0
                elif started:
                    # Require both low amplitude AND no VAD speech to count as silence
                    if amplitude <= threshold and not vad_speech:
                        silent_count += 1
                        if silent_count >= silent_limit:
                            break
                    else:
                        silent_count = 0

    except sd.PortAudioError as e:
        log.error(f"Audio device error: {e}")
        raise

    log.debug(f"Recording complete. Peak: {max_amplitude:.0f}")

    if not audio_chunks:
        return None

    all_audio = np.concatenate(audio_chunks)
    
    # Apply noise reduction before saving
    if apply_noise_reduction and len(all_audio) > 0:
        all_audio = _reduce_noise(all_audio, config.SAMPLE_RATE)
    
    # Apply audio normalization for consistent levels
    if len(all_audio) > 0:
        all_audio = _normalize_audio(all_audio)

    if not started:
        log.warning("No speech detected above threshold — check mic volume")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    try:
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(config.SAMPLE_RATE)
            w.writeframes(all_audio.tobytes())
    except Exception as e:
        log.error(f"Failed to write WAV: {e}")
        os.unlink(tmp.name)
        raise

    return tmp.name


def listen(max_seconds: float = None, use_whisper: bool = True) -> str:
    """Record speech and return transcript using Whisper (preferred) or Google STT."""
    log.debug(f"[STT] Starting to listen (max_seconds={max_seconds})")
    wav_path = None
    try:
        wav_path = _record_to_wav(max_seconds)
        log.debug(f"[STT] Recording completed, wav_path={wav_path}")
        if not wav_path or not os.path.exists(wav_path):
            log.debug("[STT] No audio recorded")
            return ""

        # Check if audio is long enough (at least 100ms)
        with wave.open(wav_path, 'rb') as w:
            frames = w.getnframes()
            rate = w.getframerate()
            duration = frames / float(rate)
        
        if duration < 0.1:
            log.warning("[STT] Audio too short, skipping")
            return ""

        # Use Whisper if available and enabled, otherwise fall back to Google
        if WHISPER_AVAILABLE and use_whisper:
            try:
                log.info("[STT] Using Whisper for transcription...")
                # Load tiny model for speed, or base for better accuracy
                model = whisper.load_model("tiny.en")
                result = model.transcribe(
                    wav_path,
                    language="en",
                    fp16=False,  # CPU compatibility
                    condition_on_previous_text=False,
                    temperature=0.0,  # More deterministic
                )
                text = result["text"].strip()
                if text:
                    log.info(f"[STT] Recognized: '{text}'")
                    return text
                else:
                    log.debug("[STT] Whisper returned empty text")
            except Exception as e:
                log.error(f"[STT] Whisper error: {e}, falling back to Google")
        
        # Fall back to Google STT
        recognizer = sr.Recognizer()
        # Adjust for ambient noise to improve accuracy
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8

        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        if len(audio_data.frame_data) < 1600:
            log.warning("[STT] Audio too short for Google STT")
            return ""

        # Try Google STT with language hints for better accuracy
        try:
            text = recognizer.recognize_google(audio_data, language="en-US")
            log.info(f"[STT] Recognized: '{text}'")
            return text
        except sr.UnknownValueError:
            log.debug("[STT] Could not understand audio")
            return ""
        except sr.RequestError as e:
            log.error(f"[STT] Network error: {e}")
            return ""
        except Exception as e:
            log.error(f"[STT] Unexpected error: {e}")
            return ""

    except Exception as e:
        log.error(f"[STT] Recording error: {e}")
        return ""
    finally:
        if wav_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except OSError as e:
                log.warning(f"[STT] Failed to delete temporary file {wav_path}: {e}")
