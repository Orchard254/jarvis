"""
Primitive: read_pc_state()
Enumerates the real desktop state live via Win32.  This is the SINGLE source
of truth for "what's on the taskbar" — used by both ``read_pc_state()`` (the
tool) and ``state_monitor.py`` (the background cache).

Exports:
    read_pc_state()       — full desktop state dict
    get_taskbar_apps()    — filtered, deduplicated list of user-visible windows
    get_raw_windows()     — all visible top-level windows without filtering
    BACKGROUND_TASKS      — helper: returns snapshot of execute_code bg processes
    SYSTEM_PROCS          — blocklist of background / system processes
"""

import json
import logging
import threading

logger = logging.getLogger(__name__)

# ── Background task snapshot (lazy import to avoid circular dependency) ───────
_bg_lock = threading.Lock()
_bg_processes_imported = False
_bg_processes_ref = None


def BACKGROUND_TASKS() -> list[dict]:
    global _bg_processes_imported, _bg_processes_ref, _bg_lock
    if not _bg_processes_imported:
        try:
            from tools.execute_code import _bg_processes, _bg_lock as _exec_bg_lock
            _bg_processes_ref = _bg_processes
            _bg_lock = _exec_bg_lock
        except ImportError:
            _bg_processes_ref = {}
        _bg_processes_imported = True
    d = _bg_processes_ref
    if not d:
        return []
    now = __import__("time").time()
    result = []
    with _bg_lock:
        items = list(d.items())
    for pid, info in items:
        p = info.get("proc")
        rc = p.poll() if p else None
        done = rc is not None
        result.append({
            "pid": pid,
            "running": not done,
            "returncode": rc,
            "elapsed_seconds": round(now - info.get("started", now), 1),
            "language": info.get("language", "?"),
            "code_preview": info.get("code", "")[:80],
        })
    return result


# ── System processes that are never real user-facing taskbar apps ────────────
SYSTEM_PROCS = {
    "SystemSettings.exe",
    "ShellExperienceHost.exe",
    "SearchHost.exe",
    "SearchUI.exe",
    "SearchIndexer.exe",
    "TextInputHost.exe",
    "LockApp.exe",
    "RuntimeBroker.exe",
    "dllhost.exe",
    "svchost.exe",
    "conhost.exe",
    "ctfmon.exe",
    "SecurityHealthSystray.exe",
    "OneDrive.exe",
    # ApplicationFrameHost.exe NOT blocked — it hosts UWP apps (Calculator, Photos, etc.)
    #   that ARE user-facing taskbar apps and must appear in the window list.
    # explorer.exe intentionally NOT here — File Explorer IS a user app
}


def get_raw_windows() -> list[dict]:
    """Enumerate all visible, sized, top-level windows with a title.

    Returns list of dicts with keys: hwnd, title, process, pid.
    No SYSTEM_PROCS / dedup filtering — that's what ``get_taskbar_apps()`` adds.
    """
    import win32con
    import win32gui
    import win32process
    import psutil

    results = []

    def callback(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            if win32gui.GetParent(hwnd) != 0:
                return
            rect = win32gui.GetWindowRect(hwnd)
            if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
                return
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = psutil.Process(pid).name() if pid else "unknown"
            results.append({
                "hwnd": int(hwnd),
                "title": title,
                "process": proc_name,
                "pid": pid,
            })
        except Exception:
            pass

    win32gui.EnumWindows(callback, None)
    return results


def get_taskbar_apps() -> list[dict]:
    """Return taskbar-visible apps: SYSTEM_PROCS filtered + title-deduplicated.

    This is the authoritative list that matches what the user sees on their
    taskbar.  Each dict: ``hwnd``, ``title``, ``process``, ``pid``.
    """
    seen_titles = set()
    apps = []
    for w in get_raw_windows():
        if w["process"] in SYSTEM_PROCS:
            continue
        if w["title"] in seen_titles:
            continue
        seen_titles.add(w["title"])
        apps.append(w)
    return apps


def _get_clipboard(max_chars: int = 500) -> str:
    """Read clipboard text (up to *max_chars*).  Returns ``""`` on failure."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return str(data)[:max_chars] if data else ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return ""
    return ""


def read_pc_state(**kwargs) -> dict:
    """Live desktop snapshot.  Zero DB / cache calls — enumerates Win32 directly.

    Returned dict keys (all consumers agree on this shape):
        success         — bool
        windows         — filtered, deduplicated taskbar-visible apps list
        processes       — unique process names from *windows*
        app_count       — len(windows)
        window_count    — raw (unfiltered) window count
        focused_window  — title of the foreground window
        focused_process — process name of the foreground window
        clipboard       — current clipboard text (up to 500 chars)
    """
    try:
        import win32gui
        import win32process
        import psutil

        apps = get_taskbar_apps()
        raw_windows = get_raw_windows()

        focused_title = ""
        focused_proc = ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                focused_title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                focused_proc = psutil.Process(pid).name()
        except Exception:
            pass

        return {
            "success": True,
            "windows": apps,
            "processes": list({a["process"] for a in apps}),
            "app_count": len(apps),
            "window_count": len(raw_windows),
            "focused_window": focused_title,
            "focused_process": focused_proc,
            "clipboard": _get_clipboard(),
            "background_tasks": BACKGROUND_TASKS(),
        }
    except Exception as e:
        logger.error(f"read_pc_state error: {e}", exc_info=True)
        return {"success": False, "error": f"Internal error: {str(e)}"}


get_taskbar_windows = get_taskbar_apps  # backward-compat alias
