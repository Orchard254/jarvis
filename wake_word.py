# wake_word.py — always-on listener with cooldown + agent abort support

import logging
import threading
import time

import numpy as np
import sounddevice as sd

# openwakeword 0.4.0+ uses ONNX runtime by default - no tflite_runtime needed
# Models are auto-downloaded on Model initialization

logging.disable(logging.WARNING)
import openwakeword
from openwakeword.model import Model

logging.disable(logging.NOTSET)

import config

SAMPLE_RATE = config.SAMPLE_RATE
CHUNK_SIZE = 1280
THRESHOLD = 0.45  # Slightly lower threshold for better detection
WAKE_MODEL = "alexa"
COOLDOWN_SECONDS = 3.0

_last_activation_time = 0.0
_agent_active = False  # True while agent loop is running
_abort_model = None  # Separate model instance for abort thread (avoids threading conflicts)

# In openwakeword 0.4.0+, models are auto-downloaded on Model initialization
# No need to call download_models separately - removed incompatible call

logging.disable(logging.WARNING)
# In openwakeword 0.4.0+, models are auto-loaded on Model initialization
# Specify the model to load explicitly using the full path
import os
model_path = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models", f"{WAKE_MODEL}_v0.1.onnx")
oww_model = Model(wakeword_model_paths=[model_path])
logging.disable(logging.NOTSET)
# Silenced startup print - too noisy
# print("Wake word ready. Say 'Alexa' to activate.\n")


# ── Cooldown helpers ─────────────────────────────────────────────────────────


def reset_cooldown():
    """Call this when TTS starts speaking to block immediate re-activation."""
    global _last_activation_time
    _last_activation_time = time.time()


def extend_cooldown(extra_seconds: float = 4.0):
    """Push the cooldown window forward by extra_seconds from now.

    Call this right after the agent loop finishes so returning to
    listen_for_wake_word() doesn't false-trigger on fading TTS audio.
    Unlike reset_cooldown() which anchors to 'now', this adds a buffer
    on top of the current timestamp so even a fresh reset doesn't expire
    before the caller is ready.
    """
    global _last_activation_time
    _last_activation_time = time.time() + extra_seconds


# ── Agent abort listener ─────────────────────────────────────────────────────


def _get_abort_model() -> Model:
    """Lazily create a second oww model instance for the abort thread.

    We never share oww_model between threads because predict() is not
    thread-safe. A second instance is cheap after the first download.
    """
    global _abort_model
    if _abort_model is None:
        logging.disable(logging.WARNING)
        import os
        model_path = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models", f"{WAKE_MODEL}_v0.1.onnx")
        _abort_model = Model(wakeword_model_paths=[model_path])
        logging.disable(logging.NOTSET)
    return _abort_model


def _abort_listener_thread(abort_event: threading.Event):
    """Background thread: listens for the wake word WHILE the agent loop runs.

    Sets abort_event if the user says 'Alexa', which signals the agent
    loop to exit cleanly at its next iteration boundary. Never raises —
    a crash here must not take down the agent loop.
    """
    global _agent_active
    try:
        model = _get_abort_model()
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=config.MIC_DEVICE,
            blocksize=CHUNK_SIZE,
        ) as stream:
            while not abort_event.is_set() and _agent_active:
                chunk, _ = stream.read(CHUNK_SIZE)
                prediction = model.predict(chunk.flatten())
                score = prediction.get(WAKE_MODEL, 0)
                if score >= THRESHOLD:
                    now = time.time()
                    # Honour cooldown — TTS speaking "Alexa" (e.g. in a script
                    # result) must not abort the agent that produced it.
                    if now - _last_activation_time >= COOLDOWN_SECONDS:
                        abort_event.set()
                        model.reset()
                        return
    except Exception:
        # Silently die — never propagate into the caller's thread
        pass


def start_abort_listener() -> tuple:
    """Start the background abort listener for the duration of an agent loop.

    Returns (abort_event, thread).  The caller MUST call stop_abort_listener()
    in a finally block to release the mic and join the thread.

    Usage::

        abort_event, abort_thread = wake_word.start_abort_listener()
        try:
            result = _run_agent_loop(..., abort_event=abort_event)
        finally:
            wake_word.stop_abort_listener(abort_event, abort_thread)
    """
    global _agent_active
    _agent_active = True
    abort_event = threading.Event()
    thread = threading.Thread(
        target=_abort_listener_thread,
        args=(abort_event,),
        daemon=True,
        name="abort-listener",
    )
    thread.start()
    return abort_event, thread


def stop_abort_listener(abort_event: threading.Event, thread: threading.Thread):
    """Signal the abort thread to exit and wait for it to release the mic."""
    global _agent_active
    _agent_active = False
    abort_event.set()  # Wake the thread if it's blocked in stream.read()
    thread.join(timeout=2.0)  # Give it time to close the InputStream cleanly


# ── Main wake-word loop ──────────────────────────────────────────────────────


def listen_for_wake_word() -> bool:
    """Block until 'alexa' is detected (with cooldown)."""
    global _last_activation_time

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=config.MIC_DEVICE,
        blocksize=CHUNK_SIZE,
    ) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_SIZE)
            prediction = oww_model.predict(chunk.flatten())
            score = prediction.get(WAKE_MODEL, 0)

            if score >= THRESHOLD:
                now = time.time()
                if now - _last_activation_time < COOLDOWN_SECONDS:
                    continue
                oww_model.reset()
                _last_activation_time = now
                return True
