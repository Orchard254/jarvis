"""
Primitive: read_pc_state()
Zero DB call. Reads live cache from state_monitor.

Always sets ``success: True`` on a normal snapshot so the tool loop, verifier,
and reporter agree (raw ``capture_state`` dicts omitted this field before).

Exports:
    read_pc_state() — full desktop state
    get_taskbar_windows() — list of taskbar-visible window dicts (for skills)
"""

import json
import logging

from indexer.state_monitor import capture_state, get_latest

logger = logging.getLogger(__name__)


def _normalize_state(state: dict) -> dict:
    """Ensure ``windows`` / ``processes`` lists exist (DB/cache use *_json columns)."""
    out = dict(state)
    if "windows" not in out and "windows_json" in out:
        wj = out.get("windows_json")
        try:
            out["windows"] = json.loads(wj) if isinstance(wj, str) else []
        except (json.JSONDecodeError, TypeError):
            out["windows"] = []
    if "processes" not in out and "processes_json" in out:
        pj = out.get("processes_json")
        try:
            out["processes"] = json.loads(pj) if isinstance(pj, str) else []
        except (json.JSONDecodeError, TypeError):
            out["processes"] = []
    out.setdefault("windows", [])
    out.setdefault("processes", [])
    out.setdefault("app_count", 0)
    out.setdefault("window_count", 0)
    out.setdefault("focused_process", "")
    return out


def read_pc_state() -> dict:
    try:
        state = get_latest()
        if not state:
            state = capture_state()
        state = _normalize_state(state)
        return {"success": True, **state}
    except Exception as e:
        logger.error(f"read_pc_state error: {e}", exc_info=True)
        return {"success": False, "error": f"Internal error: {str(e)}"}


def get_taskbar_windows() -> list[dict]:
    """
    Return list of taskbar-visible windows for window arrangement tasks.

    This is the SAME enumeration used by read_pc_state, ensuring skills count
    the same windows the user sees in their taskbar.

    Each window dict contains: hwnd, title, process, pid
    """
    try:
        import win32con
        import win32gui
        import win32process
        import psutil
    except ImportError:
        # Fallback: read from state_monitor cache
        state = read_pc_state()
        return state.get("windows", [])

    windows = []

    def enum_callback(hwnd, results):
        try:
            if not hwnd:
                return 1
            if not win32gui.IsWindowVisible(hwnd):
                return 1
            # Top-level only (no parent)
            if win32gui.GetParent(hwnd) != 0:
                return 1
            # Has actual size
            try:
                rect = win32gui.GetWindowRect(hwnd)
                width, height = rect[2] - rect[0], rect[3] - rect[1]
                if width <= 0 or height <= 0:
                    return 1
            except Exception:
                return 1
            # Taskbar visibility filters (must match state_monitor.py)
            try:
                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                if ex_style & win32con.WS_EX_TOOLWINDOW:
                    return 1  # No taskbar button
                if not (style & win32con.WS_CAPTION):
                    return 1  # No title bar
                owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
                if owner and owner != 0:
                    return 1  # Owned window
            except Exception:
                pass
            try:
                title = win32gui.GetWindowText(hwnd)
            except Exception:
                return 1
            if not title.strip():
                return 1
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_name = psutil.Process(pid).name() if pid else "unknown"
            except Exception:
                proc_name = "unknown"
                pid = 0
            results.append({"hwnd": int(hwnd), "title": title, "process": proc_name, "pid": pid})
        except Exception:
            pass
        return 1

    try:
        win32gui.EnumWindows(enum_callback, windows)
    except Exception as e:
        logger.error(f"get_taskbar_windows: EnumWindows failed: {e}")

    return windows
