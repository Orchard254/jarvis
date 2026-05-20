import logging
import threading
import time
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from core.event_bus import event_bus

logger = logging.getLogger(__name__)

_stop_event: threading.Event = threading.Event()
_observer: Observer | None = None
_main_event_loop: asyncio.AbstractEventLoop | None = None

class FileSystemEventPublisher(FileSystemEventHandler):
    def __init__(self, main_loop: asyncio.AbstractEventLoop):
        self.main_loop = main_loop

    def on_any_event(self, event):
        import os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        logs_dir = os.path.join(root, "logs")
        IGNORED = [
            logs_dir, "__pycache__", ".git", ".chroma",
            ".db-journal", ".db-wal", ".db-shm",
            "chroma.sqlite3", "header.bin", "data_level0.bin",
            "length.bin", "link_lists.bin",
            "recall_db", "pc_index.db",
        ]
        if any(pat in event.src_path for pat in IGNORED):
            return
        logger.info(f"File system event: {event.event_type} - {event.src_path}")

        event_payload = {
            "event_type": event.event_type,
            "src_path": event.src_path,
            "is_directory": event.is_directory,
            "dest_path": getattr(event, 'dest_path', None)
        }
        asyncio.run_coroutine_threadsafe(event_bus.publish("file_system_changed", event_payload, "file_system_monitor"), self.main_loop)

def start(main_loop: asyncio.AbstractEventLoop, path: str = None) -> dict:
    global _observer, _main_event_loop
    _main_event_loop = main_loop
    if _observer and _observer.is_alive():
        return {"success": True, "reason": "already_running"}

    if path is None:
        import os
        path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    event_handler = FileSystemEventPublisher(_main_event_loop)
    _observer = Observer()
    _observer.schedule(event_handler, path, recursive=True)
    _observer.start()
    logger.info(f"File system monitor started for path: {path}")
    return {"success": True}

def stop() -> dict:
    global _observer
    if _observer:
        _observer.stop()
        _observer.join(timeout=5)
    return {"success": True}
