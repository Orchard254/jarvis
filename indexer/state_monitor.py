"""
Captures live desktop state every N seconds. Caches in memory, pushes to write queue.
"""

import json
import logging
import threading
import time

import psutil
import win32con
import win32gui
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
                # Cap to 500 chars to avoid context bloat
                return str(data)[:500] if data else ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    return ""


def capture_state() -> dict:
    import time

    import psutil
    import win32gui
    import win32process

    windows = []

    # System processes to exclude from "app" count (background services, shell components)
    SYSTEM_PROCS = {
        "explorer.exe", "SearchUI.exe", "SearchIndexer.exe", "ShellExperienceHost.exe",
        "RuntimeBroker.exe", "dllhost.exe", "svchost.exe", "conhost.exe",
        "TextInputHost.exe", "ctfmon.exe", "SecurityHealthSystray.exe",
        "OneDrive.exe",  # Usually background, not a visible window user thinks of
    }

    def enum_callback(hwnd, results):
        try:
            if not hwnd:
                return 1
            if not win32gui.IsWindowVisible(hwnd):
                return 1
            # Filter to top-level windows only (no parent)
            if win32gui.GetParent(hwnd) != 0:
                return 1
            # Check window has actual size
            try:
                rect = win32gui.GetWindowRect(hwnd)
                width, height = rect[2] - rect[0], rect[3] - rect[1]
                if width <= 0 or height <= 0:
                    return 1
            except Exception:
                return 1
            # TASKBAR VISIBILITY FILTER
            # Windows shows a button in taskbar only if:
            # 1. Not a tool window (WS_EX_TOOLWINDOW)
            # 2. Has an owner window OR is not owned
            # 3. Has WS_CAPTION style (title bar)
            try:
                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                # Skip tool windows (no taskbar button)
                if ex_style & win32con.WS_EX_TOOLWINDOW:
                    return 1
                # Skip windows without caption (dialog frames, popups)
                if not (style & win32con.WS_CAPTION):
                    return 1
                # Skip owned windows (child dialogs that don't have taskbar buttons)
                owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
                if owner and owner != 0:
                    return 1
            except Exception:
                pass  # Continue if style check fails
            try:
                title = win32gui.GetWindowText(hwnd)
            except Exception:
                return 1
            if not title.strip():
                return 1
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid:
                    proc_name = psutil.Process(pid).name()
                else:
                    proc_name = "unknown"
            except Exception:
                proc_name = "unknown"
            results.append({"title": title, "process": proc_name, "hwnd": int(hwnd), "pid": pid})
        except Exception:
            pass
        return 1

    try:
        win32gui.EnumWindows(enum_callback, windows)
    except Exception as e:
        logger.error(f"EnumWindows failed: {e}")

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
    except Exception:
        pass

    # Build summary: unique user-facing apps vs raw window count
    user_apps = set()
    for w in windows:
        proc = w.get("process", "").lower()
        if proc not in {s.lower() for s in SYSTEM_PROCS}:
            user_apps.add(w["process"])

    # Limit storage but keep enough for meaningful queries
    return {
        "captured_at": time.time(),
        "windows_json": json.dumps(windows[:25]),
        "processes_json": json.dumps(list(user_apps)[:20]),
        "focused_app": focused,
        "focused_process": focused_proc,
        "app_count": len(user_apps),  # Meaningful: distinct user-facing applications
        "window_count": len(windows),   # Raw: actual top-level windows with size
        "clipboard": _get_clipboard(),
    }


def get_latest() -> dict:
    with _lock:
        snap = dict(_latest_snapshot)
    # Deserialize JSON strings back to Python lists for API consumers
    # (DB stores TEXT; callers expect lists for backward compat)
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
