"""
watch_screen — screen-condition watcher.

Monitors the screen for a natural-language condition and returns when it's met
(or when a timeout expires).  Frees the LLM from burning context budget on
manual polling inside a tool loop.

Design
------
- Takes a ``condition`` string (e.g. "the download bar shows 100%", "a dialog
  box has appeared", "the progress spinner is gone").
- Screenshots + vision-queries on a configurable interval.
- A lightweight pixel-diff pre-filter gates the full vision call: if the
  screen hasn't changed meaningfully since the last sample, the vision call is
  skipped (saves ~1–2 s per cycle).
- Returns immediately when vision says YES, or after timeout.
- Fully cancellable: caller can pass ``_cancel_event`` (threading.Event) to
  abort from another thread.

Performance note
----------------
Each vision_query call currently takes ~2–4 s on gemma3:27b-cloud.  The
default ``check_interval=5`` gives the model enough time between calls without
hammering the backend.  Reduce for time-sensitive conditions.
"""

from __future__ import annotations

import logging
import sys
import time
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Pixel-diff threshold — fraction of pixels that must change to trigger vision.
# 0.005 = 0.5% of screen pixels.  Tune down for subtle UI changes.
_PIXEL_DIFF_THRESHOLD = 0.005


def _pixel_diff_ratio(img_a, img_b) -> float:
    """
    Cheap pixel difference ratio between two PIL images.
    Returns 0.0–1.0 (fraction of pixels that differ by >10 in any channel).
    Falls back to 1.0 (always-trigger) if PIL arithmetic fails.
    """
    try:
        from PIL import ImageChops, ImageFilter  # type: ignore
        diff = ImageChops.difference(img_a.convert("RGB"), img_b.convert("RGB"))
        total = 0
        changed = 0
        for p in diff.getdata():
            total += 1
            if max(p) > 10:
                changed += 1
        return changed / max(total, 1)
    except Exception:
        return 1.0  # safe default: always trigger vision


def _grab_screen(region: dict | None = None):
    """Return a PIL Image of the screen (or region)."""
    try:
        import pyautogui  # type: ignore
        if region:
            left = region.get("left", 0)
            top = region.get("top", 0)
            width = region.get("width")
            height = region.get("height")
            if width is None or height is None:
                logger.warning("watch_screen: region missing width/height — using full screen")
                return pyautogui.screenshot()
            return pyautogui.screenshot(
                region=(left, top, width, height)
            )
        return pyautogui.screenshot()
    except Exception as exc:
        logger.warning(f"watch_screen: screenshot failed — {exc}")
        return None


def watch_screen(
    condition: str,
    timeout_seconds: int = 60,
    check_interval: int = 5,
    region: dict | None = None,
    _cancel_event: threading.Event | None = None,
) -> dict:
    """
    Watch the screen until ``condition`` is true or timeout expires.

    Parameters
    ----------
    condition : str
        Natural-language description of what to wait for.
        E.g. ``"the download has finished"`` or ``"a Save dialog is open"``.
    timeout_seconds : int
        Maximum seconds to wait (default 60).
    check_interval : int
        Seconds between vision-query polls (default 5).
    region : dict | None
        Optional crop ``{left, top, width, height}``.  Omit for full screen.
    _cancel_event : threading.Event | None
        If set by caller, aborts the watch loop early.

    Returns
    -------
    dict
        ``{"success": True, "condition_met": bool, "elapsed_seconds": float,
           "checks_performed": int, "timed_out": bool}``
    """
    if not condition:
        return {"success": False, "error": "condition is required"}

    logger.info(f"watch_screen: watching for '{condition}' (timeout={timeout_seconds}s)")

    # Lazy import to avoid hard dependency at module load
    try:
        from tools.vision_query import vision_query
    except ImportError:
        return {"success": False, "error": "vision_query tool not available"}

    deadline = time.monotonic() + timeout_seconds
    t_start = time.monotonic()
    checks = 0
    prev_img = None

    while time.monotonic() < deadline:
        # Cancellation check
        if _cancel_event and _cancel_event.is_set():
            return {
                "success": True,
                "condition_met": False,
                "elapsed_seconds": round(time.monotonic() - t_start, 1),
                "checks_performed": checks,
                "timed_out": False,
                "cancelled": True,
            }

        # Pixel-diff pre-filter
        curr_img = _grab_screen(region)
        if curr_img is not None and prev_img is not None:
            diff = _pixel_diff_ratio(prev_img, curr_img)
            if diff < _PIXEL_DIFF_THRESHOLD:
                logger.debug(f"watch_screen: pixel diff {diff:.4f} below threshold — skip vision")
                # Non-blocking wait on Windows with message pumping
                sleep_time = min(check_interval, max(1, deadline - time.monotonic()))
                if sys.platform == "win32":
                    import pythoncom
                    grace_end = time.monotonic() + sleep_time
                    while time.monotonic() < grace_end:
                        pythoncom.PumpWaitingMessages()
                        time.sleep(0.05)
                else:
                    time.sleep(sleep_time)
                continue
        prev_img = curr_img

        # Vision query
        checks += 1
        question = (
            f"Look carefully at the screen. "
            f"Is this condition currently true? '{condition}'. "
            f"Answer ONLY with YES or NO."
        )
        try:
            result = vision_query(question=question, region=region)
            answer = result.get("answer", "").strip().upper()
            logger.debug(f"watch_screen: check #{checks} → '{answer}'")
            if answer.startswith("YES"):
                elapsed = round(time.monotonic() - t_start, 1)
                logger.info(f"watch_screen: condition met after {elapsed}s ({checks} checks)")
                return {
                    "success": True,
                    "condition_met": True,
                    "elapsed_seconds": elapsed,
                    "checks_performed": checks,
                    "timed_out": False,
                }
        except Exception as exc:
            logger.warning(f"watch_screen: vision_query failed on check #{checks} — {exc}")

        # Sleep until next check (or deadline)
        remaining = deadline - time.monotonic()
        sleep_time = min(check_interval, max(0, remaining))
        if sys.platform == "win32":
            import pythoncom
            grace_end = time.monotonic() + sleep_time
            while time.monotonic() < grace_end:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.05)
        else:
            time.sleep(sleep_time)

    elapsed = round(time.monotonic() - t_start, 1)
    logger.info(f"watch_screen: timed out after {elapsed}s ({checks} checks)")
    return {
        "success": True,
        "condition_met": False,
        "elapsed_seconds": elapsed,
        "checks_performed": checks,
        "timed_out": True,
    }
