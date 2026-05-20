"""
Programmatic Audio Chime Synthesizer.
Generates clean, premium digital chimes mathematically using NumPy sine waves and plays them
via pygame.mixer in background threads to avoid blocking execution.
"""

import logging
import math
import threading
import numpy as np
import pygame
import settings

logger = logging.getLogger(__name__)


def generate_tone(frequency: float, duration: float, sample_rate: int = 44100) -> np.ndarray:
    """Generate a sine wave with exponential decay (fade-out)."""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    decay = np.exp(-4.5 * t)  # soft, elegant fade-out
    wave = np.sin(2 * np.pi * frequency * t) * decay
    return wave


def _play_thread(chime_type: str) -> None:
    """Synchronous sound generator and player; run within a daemon thread."""
    try:
        # Import local initializer to avoid circular imports and reuse sound hardware setup
        from output.tts import _init_mixer
        
        if not _init_mixer():
            logger.debug("Sounds: pygame mixer not initialized — skipping chime")
            return

        sample_rate = 44100

        if chime_type == "wake":
            # Rising double arpeggio chime (E5 -> A5)
            # E5 = 659.25 Hz (0.12s), A5 = 880.00 Hz (0.22s)
            w1 = generate_tone(659.25, 0.12, sample_rate)
            w2 = generate_tone(880.00, 0.22, sample_rate)
            
            # Blend them with an 80ms overlap
            overlap_samples = int(sample_rate * 0.08)
            combined = np.zeros(len(w1) + len(w2) - overlap_samples)
            combined[: len(w1)] += w1
            combined[len(w1) - overlap_samples :] += w2

        elif chime_type == "success":
            # Gentle, clear high-pitch verification arpeggio (C6)
            # C6 = 1046.50 Hz
            combined = generate_tone(1046.50, 0.18, sample_rate)

        elif chime_type == "error":
            # Low, dissonant alert tone (G3 + B3)
            # G3 = 196.00 Hz, B3 = 246.94 Hz
            w1 = generate_tone(196.00, 0.25, sample_rate)
            w2 = generate_tone(246.94, 0.25, sample_rate)
            combined = (w1 + w2) * 0.5
        else:
            return

        # Normalize to prevent clipping, and scale to a pleasant, non-intrusive volume
        max_val = np.max(np.abs(combined))
        if max_val > 0:
            combined = combined / max_val
        
        # Scale to comfortable 16-bit PCM integer range (~40% volume level)
        audio_data = (combined * 13107).astype(np.int16)

        # Pygame requires 2D stereo array for stereo mix
        stereo_audio = np.column_stack((audio_data, audio_data))

        # Create pygame Sound object directly from memory buffer and play
        sound = pygame.sndarray.make_sound(stereo_audio)
        sound.play()
        
        # Wait just enough for playback to complete so the sound object is preserved in memory
        duration_sec = len(combined) / sample_rate
        pygame.time.wait(int(duration_sec * 1000) + 50)

    except Exception as e:
        logger.warning(f"Sounds: failed to synthesize/play programmatic chime '{chime_type}' — {e}")


def play_chime(chime_type: str = "wake") -> None:
    """
    Play a mathematically-synthesized digital chime (non-blocking).
    
    Supported types:
      "wake"    — played when the wake word is triggered (E5 -> A5)
      "success" — played when speech is successfully transcribed (C6)
      "error"   — played on transcription or system error (G3 + B3)
    """
    if not settings.TTS_ENABLED:
        logger.debug(f"Sounds: chimes disabled (TTS_ENABLED=False) — skipping '{chime_type}'")
        return

    # Run in background daemon thread so it doesn't block wake-word or transcription pipelines
    threading.Thread(
        target=_play_thread,
        args=(chime_type,),
        daemon=True,
        name=f"chime-{chime_type}",
    ).start()
