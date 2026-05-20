import logging
import threading
import time
import asyncio
try:
    import pygetwindow
    _HAS_PYGETWINDOW = True
except ImportError:
    pygetwindow = None
    _HAS_PYGETWINDOW = False

from core.event_bus import event_bus

logger = logging.getLogger(__name__)

_stop_event: threading.Event = threading.Event()
_thread: "threading.Thread | None" = None
_last_active_window: str | None = None
_main_event_loop: asyncio.AbstractEventLoop | None = None

MONITOR_INTERVAL = 1  # Check every 1 second

def start(main_loop: asyncio.AbstractEventLoop) -> dict:
    global _thread, _main_event_loop
    _main_event_loop = main_loop
    if _thread and _thread.is_alive():
        return {"success": True, "reason": "already_running"}
    _stop_event.clear()
    _thread = threading.Thread(target=_monitor_loop, daemon=True, name="window-monitor", args=(_main_event_loop,))
    _thread.start()
    return {"success": True}

def stop() -> dict:
    global _thread
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    return {"success": True}

def _get_active_window_title() -> str | None:
    """Get active window title with fallback chain."""
    # Try pygetwindow first
    if _HAS_PYGETWINDOW:
        try:
            w = pygetwindow.getActiveWindow()
            if w and w.title:
                return w.title
        except Exception:
            pass
    # Fallback: Windows API directly
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        return buf.value or None
    except Exception:
        return None

def _monitor_loop(main_loop: asyncio.AbstractEventLoop):
    global _last_active_window
    logger.info("window_monitor: loop started")
    from core.ambient_state import get_state
    ambient = get_state()
    while not _stop_event.is_set():
        try:
            current_window_title = _get_active_window_title()

            if current_window_title and current_window_title != _last_active_window:
                logger.info(f"Window focus changed to: {current_window_title}")
                event_payload = {"title": current_window_title}
                ambient.set("active_window_title", current_window_title)
                asyncio.run_coroutine_threadsafe(event_bus.publish("window_focus_changed", event_payload, "window_monitor"), main_loop)
                _last_active_window = current_window_title
        except Exception as e:
            logger.error(f"window_monitor: Error checking active window: {e}")
        _stop_event.wait(MONITOR_INTERVAL)
    logger.info("window_monitor: loop stopped")
