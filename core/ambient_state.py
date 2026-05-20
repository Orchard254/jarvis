"""
Ambient state — live snapshot of what's happening on the computer.

Updated continuously by background monitors (window_monitor, clipboard_monitor,
ambient_monitor) and available for injection into every JARVIS turn so the
agent is always aware of the current computer state without being asked.
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class AmbientState:
    """Thread-safe singleton holding live computer state."""

    _lock = threading.Lock()
    _instance: "AmbientState | None" = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._data = {
            # Window
            "active_window_title": None,
            "active_window_process": None,
            "last_non_terminal_window": None,
            # Clipboard
            "clipboard_content": None,
            "clipboard_last_changed": None,
            # System (updated periodically)
            "running_apps": [],
            "installed_apps": [],
            "cpu_percent": 0.0,
            "ram_percent": 0.0,
            "ram_free_mb": 0,
            "disk_percent": 0.0,
            "disk_free_gb": 0.0,
            "battery_percent": None,
            "battery_plugged": None,
            # Meta
            "last_updated": None,
            "uptime_since": time.time(),
        }
        self._data["current_time"] = datetime.now().isoformat()
        logger.info("AmbientState initialized")

    def is_terminal_window(self, title: str) -> bool:
        if not title:
            return False
        title_lower = title.lower()
        terminal_keywords = [
            "powershell",
            "cmd.exe",
            "command prompt",
            "terminal",
            "git bash",
            "conhost",
            "jarvis",
            "pycmd",
            "bash",
            "wsl"
        ]
        return any(kw in title_lower for kw in terminal_keywords)

    # ── Setters (called by monitors) ────────────────────────────────────────

    def _refresh_active_window(self):
        """Fallback: query Windows API directly for active window."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd) + 1
            buf = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buf, length)
            title = buf.value
            if title and title != self._data.get("active_window_title"):
                self.set("active_window_title", title)
        except Exception:
            pass

    def set(self, key: str, value):
        with self._lock:
            if key not in ("current_time", "uptime_since"):
                self._data["last_updated"] = time.time()
            self._data[key] = value
            if key == "active_window_title" and value:
                if not self.is_terminal_window(value):
                    self._data["last_non_terminal_window"] = value

    def set_many(self, updates: dict):
        with self._lock:
            for k, v in updates.items():
                if k not in ("current_time", "uptime_since"):
                    self._data["last_updated"] = time.time()
                self._data[k] = v
                if k == "active_window_title" and v:
                    if not self.is_terminal_window(v):
                        self._data["last_non_terminal_window"] = v

    # ── Getters ─────────────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def snapshot(self) -> dict:
        """Return a copy of all current state."""
        self._refresh_active_window()
        self._try_refresh_apps({})
        with self._lock:
            snap = dict(self._data)
            snap["current_time"] = datetime.now().isoformat()
            snap["uptime_seconds"] = int(time.time() - snap["uptime_since"])
            return snap

    def format_context(self) -> str:
        """Format state as a compact string for LLM context injection."""
        snap = self.snapshot()
        lines = ["## Current computer state"]
        lines.append(f"  Time: {snap['current_time']}")
        if snap["active_window_title"]:
            lines.append(f"  Active window: {snap['active_window_title']}")
        if snap["clipboard_content"]:
            cc = snap["clipboard_content"][:120]
            lines.append(f"  Clipboard: {cc!r}")
        if snap["running_apps"]:
            apps = snap["running_apps"][:15]
            lines.append(f"  Running apps ({len(apps)}): {', '.join(a[:25] for a in apps)}")
        lines.append(f"  CPU: {snap['cpu_percent']:.0f}% | RAM: {snap['ram_percent']:.0f}% | "
                     f"Disk: {snap['disk_percent']:.0f}%")
        if snap["battery_percent"] is not None:
            plug = "plugged in" if snap["battery_plugged"] else "on battery"
            lines.append(f"  Battery: {snap['battery_percent']:.0f}% ({plug})")
        # Always try to refresh running apps
        self._try_refresh_apps(snap)
        return "\n".join(lines)

    def _try_refresh_apps(self, snap: dict):
        """Best-effort refresh of running apps list."""
        if not snap.get("running_apps"):
            try:
                import psutil
                apps = []
                for proc in psutil.process_iter(["name"]):
                    try:
                        n = proc.info["name"]
                        if n and n not in apps:
                            apps.append(n)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                if apps:
                    self.set("running_apps", apps[:30])
            except ImportError:
                pass


# Module-level singleton
_state = AmbientState()


def get_state() -> AmbientState:
    return _state
