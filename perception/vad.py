"""
WebRTC VAD audio capture — replaces speech_recognition's energy-based VAD.

Uses WebRTC Voice Activity Detection with a ring buffer for lookback
and smart endpoint detection that won't cut off natural pauses.

Usage:
    from perception.vad import VADCapture

    with VADCapture() as cap:
        audio_data = cap.record(timeout=10)
        # audio_data is speech_recognition.AudioData, usable with recognize_google()
"""

from __future__ import annotations

import io
import logging
import struct
import threading
import wave
from collections import deque
from typing import Optional

import sounddevice as sd
import webrtcvad

logger = logging.getLogger(__name__)

# WebRTC VAD requires specific frame sizes
FRAME_DURATIONS_MS = {10, 20, 30}
SUPPORTED_SAMPLE_RATES = {8000, 16000, 32000, 48000}


class _RingBuffer:
    """Fixed-size ring buffer for audio lookback."""

    def __init__(self, max_frames: int):
        self._buf: deque[bytes] = deque(maxlen=max_frames)
        self._max_frames = max_frames

    def add(self, frame: bytes):
        self._buf.append(frame)

    def get_all(self) -> list[bytes]:
        return list(self._buf)

    def clear(self):
        self._buf.clear()

    @property
    def filled(self) -> int:
        return len(self._buf)


class VADCapture:
    """
    Context manager that captures audio with WebRTC VAD.

    Parameters
    ----------
    sample_rate : int
        Must be one of 8000, 16000, 32000, 48000 (default 16000).
    frame_duration_ms : int
        Must be 10, 20, or 30 (default 30). Smaller = more responsive but more CPU.
    aggressiveness : int
        VAD aggressiveness 0-3 (default 1).
        0 = least aggressive (more false accepts, less false rejects).
        3 = most aggressive (less false accepts, more false rejects).
    lookback_seconds : float
        Seconds of audio kept in ring buffer before speech starts (default 0.5).
    min_speech_seconds : float
        Minimum consecutive speech frames before accepting speech start (default 0.15).
    max_silence_seconds : float
        Consecutive silence frames before marking speech end (default 0.6).
    device : int | None
        Sounddevice device index (None = default).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        aggressiveness: int = 1,
        lookback_seconds: float = 0.5,
        min_speech_seconds: float = 0.15,
        max_silence_seconds: float = 0.6,
        device: int | None = None,
    ):
        if sample_rate not in SUPPORTED_SAMPLE_RATES:
            raise ValueError(f"sample_rate must be one of {SUPPORTED_SAMPLE_RATES}")
        if frame_duration_ms not in FRAME_DURATIONS_MS:
            raise ValueError(f"frame_duration_ms must be one of {FRAME_DURATIONS_MS}")

        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self._samples_per_frame = int(sample_rate * frame_duration_ms / 1000)
        self.frame_size = self._samples_per_frame * 2  # 16-bit = 2 bytes per sample
        self.aggressiveness = aggressiveness
        self.device = device

        self._ring = _RingBuffer(int(lookback_seconds * 1000 / frame_duration_ms))
        self._min_speech_frames = int(min_speech_seconds * 1000 / frame_duration_ms) or 1
        self._max_silence_frames = int(max_silence_seconds * 1000 / frame_duration_ms)
        self._speech_buf: list[bytes] = []

        self._vad = webrtcvad.Vad(aggressiveness)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def _read_frames(self, timeout: float, callback=None) -> Optional[bytes]:
        """
        Read frames from mic, run VAD, return captured audio or None on timeout.

        States: idle → validating → speech → draining
        """
        state = "idle"
        silence_frames = 0
        total_elapsed = 0.0
        frame_sec = self.frame_duration_ms / 1000

        def _reset():
            nonlocal state, silence_frames
            state = "idle"
            silence_frames = 0
            self._speech_buf.clear()
            self._ring.clear()

        stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self._samples_per_frame,
            device=self.device,
        )

        with stream:
            while True:
                frame, _ = stream.read(self._samples_per_frame)
                frame_bytes = bytes(frame)
                total_elapsed += frame_sec

                if total_elapsed >= timeout:
                    if state == "idle":
                        return None
                    # In validating/speech: force-end with what we have
                    if state == "speech" and self._speech_buf:
                        result = b"".join(self._speech_buf)
                        _reset()
                        return result
                    if state == "validating":
                        _reset()
                        return None

                is_speech = self._vad.is_speech(frame_bytes, self.sample_rate)

                # Always add to ring buffer
                self._ring.add(frame_bytes)

                if state == "idle":
                    if is_speech:
                        state = "validating"
                        self._speech_buf = self._ring.get_all()
                        self._speech_buf.append(frame_bytes)
                        silence_frames = 0

                elif state == "validating":
                    self._speech_buf.append(frame_bytes)
                    if is_speech:
                        silence_frames = 0
                        if len(self._speech_buf) >= self._ring._max_frames + self._min_speech_frames:
                            state = "speech"
                            if callback:
                                callback("listening")
                    else:
                        silence_frames += 1
                        if silence_frames > self._max_silence_frames // 2:
                            _reset()

                elif state == "speech":
                    self._speech_buf.append(frame_bytes)
                    if is_speech:
                        silence_frames = 0
                    else:
                        silence_frames += 1
                        if silence_frames >= self._max_silence_frames:
                            result = b"".join(self._speech_buf)
                            _reset()
                            return result

        return None

    def record(self, timeout: float = 10.0, callback=None) -> Optional[bytes]:
        """
        Record one utterance with VAD.

        Parameters
        ----------
        timeout : float
            Max seconds to wait for speech to start.
        callback : callable, optional
            Called with status strings: "listening", "done", "timeout".

        Returns
        -------
        bytes | None
            Raw 16-bit PCM audio data, or None if timeout.
        """
        result = self._read_frames(timeout, callback)
        if result is None:
            if callback:
                callback("timeout")
            return None
        if callback:
            callback("done")
        return result

    def pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """Wrap raw 16-bit PCM data in a WAV container (RIFF header)."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)
        return buf.getvalue()

    def record_as_audiodata(self, timeout: float = 10.0, callback=None):
        """
        Record utterance and return speech_recognition.AudioData.

        Returns None on timeout.
        """
        pcm = self.record(timeout, callback)
        if pcm is None:
            return None

        import speech_recognition as sr

        return sr.AudioData(pcm, sample_rate=self.sample_rate, sample_width=2)


def list_devices() -> list[dict]:
    """Return all audio input devices."""
    devices = sd.query_devices()
    results = []
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            results.append({
                "index": i,
                "name": dev["name"],
                "channels": dev["max_input_channels"],
                "sample_rate": dev["default_samplerate"],
            })
    return results
