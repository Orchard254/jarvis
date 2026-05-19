import logging
import threading
import time
import asyncio
import pygetwindow

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

def _monitor_loop(main_loop: asyncio.AbstractEventLoop):
    global _last_active_window
    logger.info("window_monitor: loop started")
    while not _stop_event.is_set():
        try:
            active_window = pygetwindow.getActiveWindow()
            current_window_title = active_window.title if active_window else None

            if current_window_title and current_window_title != _last_active_window:
                logger.info(f"Window focus changed to: {current_window_title}")
                event_payload = {"title": current_window_title}
                asyncio.run_coroutine_threadsafe(event_bus.publish("window_focus_changed", event_payload, "window_monitor"), main_loop)
                _last_active_window = current_window_title
        except Exception as e:
            logger.error(f"window_monitor: Error checking active window: {e}")
        _stop_event.wait(MONITOR_INTERVAL)
    logger.info("window_monitor: loop stopped")
