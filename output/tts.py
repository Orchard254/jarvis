"""
Text-to-Speech — Edge TTS primary, Piper local fallback.

Engine selection (settings.TTS_ENGINE):
  "edge"  — Microsoft Edge TTS via edge-tts (requires internet, zero install).
            Audio is synthesised to a temp MP3 then played through pygame.
  "piper" — Local Piper binary (offline, needs piper.exe + model files).
  any other value falls back to Piper as well.

IS_SPEAKING is set to True on *entry* (before any try/except) so the STT
listener is muted for the entire duration of speech synthesis + playback.
It is always cleared in the finally block — even on error — to guarantee
the mic is never permanently silenced.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

import settings

logger = logging.getLogger(__name__)

# ── Lazy pygame mixer initialisation ──────────────────────────────────────────
_mixer_ready: bool = False

# Files queued for deletion after non-blocking playback finishes.
# _speak_edge appends the path; _wait_and_clear drains the queue.
_tmp_cleanup_queue: list[str] = []


def _init_mixer() -> bool:
    """Initialise pygame.mixer on first use. Returns True on success."""
    global _mixer_ready
    if _mixer_ready:
        return True
    try:
        import pygame  # noqa: PLC0415

        if not pygame.get_init():
            pygame.init()
        pygame.mixer.init()
        _mixer_ready = True
        logger.debug("TTS: pygame mixer initialised")
        return True
    except Exception as exc:
        logger.warning(f"TTS: pygame mixer init failed — {exc}")
        return False


# ── Public API ─────────────────────────────────────────────────────────────────


def speak(text: str, blocking: bool = True) -> bool:
    """
    Convert *text* to speech and play it through the default audio device.

    Args:
        text:     The string to speak.  Empty / whitespace-only strings are
                  silently ignored (returns True).
        blocking: Wait for playback to finish before returning (default True).
                  When False the function returns as soon as playback starts;
                  IS_SPEAKING will be cleared by a background thread.

    Returns:
        True  — audio was synthesised and playback started (or was skipped
                because TTS is disabled or text was empty).
        False — synthesis or playback failed (error is logged).
    """
    # Fast exits — don't touch IS_SPEAKING so we don't accidentally mute STT
    if not settings.TTS_ENABLED:
        logger.debug("TTS: disabled in settings — skipping")
        return True

    text = text.strip()
    if not text:
        logger.debug("TTS: empty text — skipping")
        return True

    # ── Mute STT immediately on entry, before ANY try/except ─────────────────
    settings.IS_SPEAKING.set()

    try:
        engine = settings.TTS_ENGINE.lower().strip()

        if engine == "edge":
            return _speak_edge(text, blocking)
        else:
            # "piper" or any unrecognised value → local fallback
            from output.tts_piper import speak_piper  # noqa: PLC0415

            return speak_piper(text, blocking)

    except Exception as exc:
        logger.error(f"TTS: unexpected error in speak() — {exc}", exc_info=True)
        return False

    finally:
        # ── Always restore STT after an acoustic drain delay ──────────────────
        if blocking:
            # 0.8s gives speaker echo time to dissipate before mic reopens.
            time.sleep(0.8)
            settings.IS_SPEAKING.clear()
        else:
            # Non-blocking: background thread waits for playback to finish,
            # cleans up the temp file, then clears IS_SPEAKING.
            # DO NOT unload/delete the file here — audio would cut mid-sentence.
            import threading  # noqa: PLC0415

            def _wait_and_clear():
                try:
                    import pygame  # noqa: PLC0415

                    while pygame.mixer.music.get_busy():
                        pygame.time.Clock().tick(20)
                    # Unload so Windows releases the file handle, then delete queued temps.
                    try:
                        pygame.mixer.music.unload()
                    except Exception:
                        pass
                    for p in list(_tmp_cleanup_queue):
                        try:
                            Path(p).unlink(missing_ok=True)
                            _tmp_cleanup_queue.remove(p)
                        except Exception:
                            pass
                    time.sleep(0.8)
                except Exception:
                    pass
                finally:
                    settings.IS_SPEAKING.clear()

            threading.Thread(target=_wait_and_clear, daemon=True, name="tts-clear").start()


# ── Edge TTS implementation ───────────────────────────────────────────────────


def _speak_edge(text: str, blocking: bool) -> bool:
    """
    Synthesise *text* with Microsoft Edge TTS and play via pygame.

    Flow:
        1. Run async edge_tts.Communicate.save() to write an MP3 to a temp file.
        2. Load the MP3 with pygame.mixer.music.
        3. Play (blocking or non-blocking).
        4. Delete the temp file after playback.

    Falls back to Piper on any failure.
    """
    try:
        import edge_tts  # noqa: PLC0415
    except ImportError:
        logger.warning("TTS: edge-tts not installed — falling back to Piper")
        return _fallback_piper(text, blocking)

    if not _init_mixer():
        logger.warning("TTS: pygame unavailable — falling back to Piper")
        return _fallback_piper(text, blocking)

    tmp_path: str | None = None
    try:
        # ── 1. Synthesise to temp file ─────────────────────────────────────
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="jarvis_tts_")
        os.close(tmp_fd)  # edge-tts opens the file itself; close the fd first

        communicate = edge_tts.Communicate(
            text=text,
            voice=settings.EDGE_TTS_VOICE,
            rate=settings.EDGE_TTS_RATE,
            volume=settings.EDGE_TTS_VOLUME,
            pitch=settings.EDGE_TTS_PITCH,
        )

        # asyncio.run() works even if no event loop is running (e.g. main thread).
        # For callers inside an existing loop use loop.run_until_complete() instead.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an async context — schedule as a task and spin the loop
            import concurrent.futures  # noqa: PLC0415

            future = asyncio.run_coroutine_threadsafe(communicate.save(tmp_path), loop)
            future.result(timeout=settings.EDGE_TTS_TIMEOUT)
        else:
            asyncio.run(
                asyncio.wait_for(
                    communicate.save(tmp_path),
                    timeout=settings.EDGE_TTS_TIMEOUT,
                )
            )

        logger.debug(f"TTS(edge): synthesised {len(text)} chars → {tmp_path}")

        # ── 2 & 3. Load and play ──────────────────────────────────────────
        import pygame  # noqa: PLC0415

        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()

        if blocking:
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(20)
            # Give mixer a moment to fully flush
            time.sleep(0.1)

        logger.info(f"TTS(edge): spoke {len(text)} chars via {settings.EDGE_TTS_VOICE}")
        return True

    except asyncio.TimeoutError:
        logger.error(
            f"TTS(edge): synthesis timed out after {settings.EDGE_TTS_TIMEOUT}s "
            "— falling back to Piper"
        )
        return _fallback_piper(text, blocking)

    except Exception as exc:
        logger.error(f"TTS(edge): failed — {exc} — falling back to Piper")
        return _fallback_piper(text, blocking)

    finally:
        # ── 4. Clean up temp file ──────────────────────────────────────────────
        # Blocking: playback finished, safe to unload and delete now.
        # Non-blocking: queue the path for the tts-clear thread to delete
        # after get_busy() returns False — deleting here cuts audio mid-sentence.
        if blocking and tmp_path:
            try:
                import pygame  # noqa: PLC0415
                pygame.mixer.music.unload()
            except Exception:
                pass
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
        elif tmp_path:
            _tmp_cleanup_queue.append(tmp_path)


# ── Piper fallback helper ─────────────────────────────────────────────────────


def _fallback_piper(text: str, blocking: bool) -> bool:
    """Delegate to the Piper module and log the fallback."""
    logger.info("TTS: using Piper fallback")
    try:
        from output.tts_piper import speak_piper  # noqa: PLC0415

        return speak_piper(text, blocking)
    except Exception as exc:
        logger.error(f"TTS(piper fallback): failed — {exc}")
        return False
