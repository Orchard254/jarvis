"""
Captures live desktop state every N seconds. Caches in memory, pushes to write queue.

Window enumeration is DELEGATED to ``tools.read_pc_state`` — the single source
of truth for "what's on the taskbar".  This module only adds the periodic
cache-and-push loop on top.
"""

import json
import logging
import threading
import time

from settings import STATE_MONITOR_INTERVAL

logger = logging.getLogger(__name__)
_latest_snapshot = {}
_lock = threading.Lock()


def monitor_loop(writer, stop_event):
    global _latest_snapshot
    while not stop_event.is_set():
        try:
            state = capture_state()
            with _lock:
                _latest_snapshot = state
            writer.push("state_snapshots", [state])
        except Exception as e:
            logger.error(f"State monitor error: {e}")
        stop_event.wait(STATE_MONITOR_INTERVAL)


def _get_clipboard() -> str:
    """Read the current clipboard text. Returns empty string on any failure."""
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return str(data)[:500] if data else ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e:
        logger.debug(f"CloseClipboard failed: {e}")
    return ""


def capture_state() -> dict:
    from tools.read_pc_state import get_raw_windows, get_taskbar_apps

    import psutil
    import win32gui
    import win32process

    user_apps = get_taskbar_apps()
    raw_windows = get_raw_windows()

    focused = ""
    focused_proc = ""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            focused = win32gui.GetWindowText(hwnd)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                focused_proc = psutil.Process(pid).name()
            except Exception:
                focused_proc = "unknown"
    except Exception as e:
        logger.debug(f"Process failed: {e}")

    return {
        "captured_at": time.time(),
        "windows_json": json.dumps(user_apps[:25]),
        "processes_json": json.dumps(list({w["process"] for w in user_apps})[:20]),
        "focused_app": focused,
        "focused_process": focused_proc,
        "app_count": len(user_apps),
        "window_count": len(raw_windows),
        "clipboard": _get_clipboard(),
    }


def get_latest() -> dict:
    with _lock:
        snap = dict(_latest_snapshot)
    if "windows_json" in snap and isinstance(snap["windows_json"], str):
        try:
            snap["windows"] = json.loads(snap["windows_json"])
        except Exception:
            snap["windows"] = []
    if "processes_json" in snap and isinstance(snap["processes_json"], str):
        try:
            snap["processes"] = json.loads(snap["processes_json"])
        except Exception:
            snap["processes"] = []
    return snap
