import logging
import threading
import time
import asyncio
import pyperclip

from core.event_bus import event_bus

logger = logging.getLogger(__name__)

_stop_event: threading.Event = threading.Event()
_thread: "threading.Thread | None" = None
_last_clipboard_content: str | None = None
_main_event_loop: asyncio.AbstractEventLoop | None = None

MONITOR_INTERVAL = 1  # Check every 1 second

def start(main_loop: asyncio.AbstractEventLoop) -> dict:
    global _thread, _main_event_loop
    _main_event_loop = main_loop
    if _thread and _thread.is_alive():
        return {"success": True, "reason": "already_running"}
    _stop_event.clear()
    _thread = threading.Thread(target=_monitor_loop, daemon=True, name="clipboard-monitor", args=(_main_event_loop,))
    _thread.start()
    return {"success": True}

def stop() -> dict:
    global _thread
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    return {"success": True}

def _monitor_loop(main_loop: asyncio.AbstractEventLoop):
    global _last_clipboard_content
    logger.info("clipboard_monitor: loop started")
    while not _stop_event.is_set():
        try:
            current_clipboard_content = pyperclip.paste()

            if current_clipboard_content and current_clipboard_content != _last_clipboard_content:
                logger.info(f"Clipboard content changed.")
                event_payload = {"content": current_clipboard_content}
                asyncio.run_coroutine_threadsafe(event_bus.publish("clipboard_changed", event_payload, "clipboard_monitor"), main_loop)
                _last_clipboard_content = current_clipboard_content
        except Exception as e:
            logger.error(f"clipboard_monitor: Error checking clipboard: {e}")
        _stop_event.wait(MONITOR_INTERVAL)
    logger.info("clipboard_monitor: loop stopped")
