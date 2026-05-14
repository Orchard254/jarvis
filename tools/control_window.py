"""
Primitive: control_window(window_title, action, params)
AttachThreadInput fallback + foreground verification.

Close flow (action="close"):
  1. PostMessage WM_CLOSE — graceful, lets the app save its state.
  2. If the window survives after CLOSE_GRACE_SECS, try Alt+F4 via pyautogui.
  3. If still alive, fall back to `taskkill /F /IM <exe>` — hard kill.
All three steps are audit-logged and respect SAFETY_ENABLED + path/process guards.

Layer boundary: this module is in `tools/` and imports only from `safety/`
and stdlib — never from `brain/`.
"""

import logging
import subprocess
from typing import Optional

import settings  # allowed: tools/ → settings.py
import win32api
import win32con
import win32gui
import win32process
from safety import audit_log  # allowed: tools/ → safety/

# Cross-platform abstraction layer for window/process operations.
# Falls back gracefully if unavailable (e.g. in headless/container env).
try:
    from core.platform_abstraction import PlatformAbstraction
    _platform = PlatformAbstraction()
    _HAS_PLATFORM = True
except Exception:
    _HAS_PLATFORM = False

logger = logging.getLogger(__name__)

# Seconds to wait after WM_CLOSE before escalating to the next fallback.
_CLOSE_GRACE_SECS = 1.5


def _wait_grace():
    """Non-blocking wait using Windows message pump instead of time.sleep."""
    import time as _time
    start = _time.time()
    pumped = 0
    while (_time.time() - start) < _CLOSE_GRACE_SECS:
        if pumped % 10 == 0:
            try:
                import pythoncom
                pythoncom.PumpWaitingMessages()
            except Exception as e:
                logger.debug(f"PumpWaitingMessages failed: {e}")
        pumped += 1
        _time.sleep(0.05)


# ── helpers ──────────────────────────────────────────────────────────────────


def _find_hwnd(window_title: str, retries: int = 10, delay: float = 0.5):
    """Return the first visible HWND whose title contains `window_title` (case-insensitive).

    Retries up to `retries` times with `delay` seconds between attempts to
    handle the window not yet being registered (e.g. just after launch).
    """
    hwnd_ref = [None]
    search_title = str(window_title).lower().strip()

    def _search():
        def _cb(h, _):
            try:
                if not h or not win32gui.IsWindow(h):
                    return 1
                if win32gui.IsWindowVisible(h):
                    t = win32gui.GetWindowText(h).lower()
                    if search_title in t:
                        hwnd_ref[0] = h
                        return 0
            except Exception as e:
                logger.debug(f"GetWindowText failed: {e}")
            return 1

        try:
            win32gui.EnumWindows(_cb, None)
        except Exception as e:
            logger.error(f"EnumWindows failed in _find_hwnd: {e}")
        return hwnd_ref[0]

    import time as _time
    for attempt in range(retries):
        result = _search()
        if result is not None:
            return result
        if attempt < retries - 1:
            _time.sleep(delay)
    return None


def _window_alive(hwnd: int) -> bool:
    """Return True if the HWND still exists and is visible."""
    try:
        return bool(win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd))
    except Exception:
        return False


def _get_process_name(hwnd: int) -> Optional[str]:
    """Resolve the .exe name for a given HWND (e.g. 'notepad.exe')."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = win32api.OpenProcess(0x0400 | 0x0010, False, pid)  # QUERY + VM_READ
        path = win32process.GetModuleFileNameEx(handle, 0)
        win32api.CloseHandle(handle)
        return path.split("\\")[-1]  # keep only the basename
    except Exception as exc:
        logger.debug(f"_get_process_name failed for hwnd={hwnd}: {exc}")
        return None


def _taskkill(process_name: str, window_title: str) -> dict:
    """
    Hard-kill via taskkill /F /IM <process_name>.

    Guards enforced here (even though safety.executor already ran check_paths):
    - process_name must be a plain .exe name with no path separators.
    - SAFETY_ENABLED must be True (or the guard is intentionally bypassed by
      the operator by setting SAFETY_ENABLED=false in .env — their choice).

    Returns a result dict compatible with the rest of the tool.
    """
    # --- process-name sanity check (no path traversal) -------------------
    if not process_name or any(c in process_name for c in ("/", "\\", "..", ":")):
        reason = f"Refused taskkill: unsafe process name '{process_name}'"
        logger.warning(reason)
        audit_log.log_blocked(
            "control_window:taskkill", {"process": process_name}, reason
        )
        return {"success": False, "error": reason}

    # --- SAFETY_ENABLED guard --------------------------------------------
    # settings.SAFETY_ENABLED controls whether hard kills are permitted.
    safety_on = getattr(settings, "SAFETY_ENABLED", True)
    if safety_on:
        logger.warning("SAFETY_ENABLED=True — skipping forced taskkill")
        return {"success": False, "error": "taskkill blocked by SAFETY_ENABLED"}
    logger.warning("SAFETY_ENABLED=False — proceeding with forced taskkill")

    logger.info(f"taskkill fallback: /F /IM {process_name}")
    proc = subprocess.run(
        ["taskkill", "/F", "/IM", process_name],
        capture_output=True,
        text=True,
        check=False,  # never raise — we inspect returncode manually
    )

    if proc.returncode == 0:
        msg = f"taskkill succeeded for '{process_name}' (window: '{window_title}')"
        logger.info(msg)
        audit_log.log_call(
            "control_window:taskkill",
            {"process": process_name, "window": window_title},
            {"success": True, "stdout": proc.stdout.strip()},
        )
        return {"success": True, "method": "taskkill", "process": process_name}
    else:
        stderr = proc.stderr.strip() or proc.stdout.strip()
        msg = f"taskkill failed for '{process_name}': {stderr}"
        logger.error(msg)
        audit_log.log_call(
            "control_window:taskkill",
            {"process": process_name, "window": window_title},
            {"success": False, "error": stderr, "returncode": proc.returncode},
        )
        return {"success": False, "method": "taskkill", "error": stderr}


def _close_with_fallbacks(hwnd: int, window_title: str) -> dict:
    """
    Three-stage close sequence for action="close":

      Stage 1 — WM_CLOSE  (graceful, honour save-dialogs)
      Stage 2 — Alt+F4    (slightly more insistent, still GUI-layer)
      Stage 3 — taskkill  (hard kill, last resort)

    Returns a result dict with keys: success, method, window, [error].
    """
    # ── Stage 1: WM_CLOSE ────────────────────────────────────────────────
    logger.info(f"Stage 1 close (WM_CLOSE): '{window_title}' hwnd={hwnd}")
    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception as exc:
        logger.warning(f"WM_CLOSE failed: {exc}")

    _wait_grace()

    if not _window_alive(hwnd):
        logger.info(f"Window '{window_title}' closed via WM_CLOSE")
        audit_log.log_call(
            "control_window",
            {"window_title": window_title, "action": "close", "method": "WM_CLOSE"},
            {"success": True},
        )
        return {"success": True, "method": "WM_CLOSE", "window": window_title}

    # ── Stage 2: Alt+F4 via pyautogui ───────────────────────────────────
    logger.info(f"Stage 2 close (Alt+F4): '{window_title}' hwnd={hwnd}")
    try:
        import pyautogui  # optional; only imported when needed

        _force_focus(hwnd)
        pyautogui.hotkey("alt", "f4")
        _wait_grace()
    except Exception as exc:
        logger.warning(f"Alt+F4 attempt failed: {exc}")

    if not _window_alive(hwnd):
        logger.info(f"Window '{window_title}' closed via Alt+F4")
        audit_log.log_call(
            "control_window",
            {"window_title": window_title, "action": "close", "method": "Alt+F4"},
            {"success": True},
        )
        return {"success": True, "method": "Alt+F4", "window": window_title}

    # ── Stage 3: taskkill /F /IM ─────────────────────────────────────────
    logger.info(f"Stage 3 close (taskkill): '{window_title}' hwnd={hwnd}")
    process_name = _get_process_name(hwnd)

    if not process_name:
        # Last-ditch: try deriving the .exe name from the window_title itself.
        # e.g. "ultraviewr" → "ultraviewr.exe"
        guessed = window_title.strip().split()[0].lower()
        if not guessed.endswith(".exe"):
            guessed += ".exe"
        logger.warning(
            f"Could not resolve process name from hwnd; guessing '{guessed}' from title"
        )
        process_name = guessed

    return _taskkill(process_name, window_title)


# ── window listing helpers ────────────────────────────────────────────────────


def list_windows() -> dict:
    """List all visible windows with their titles, positions, and process names."""
    # Prefer platform abstraction for cross-platform support
    if _HAS_PLATFORM:
        try:
            windows = _platform.get_windows()
            return {"success": True, "count": len(windows), "windows": windows}
        except Exception as e:
            logger.debug(f"len failed: {e}")

    # Fallback to direct win32 enumeration
    windows = []

    def _cb(h, _):
        try:
            if not h or not win32gui.IsWindow(h):
                return 1
            if win32gui.IsWindowVisible(h):
                title = win32gui.GetWindowText(h)
                if title:
                    rect = win32gui.GetWindowRect(h)
                    process_name = _get_process_name(h)
                    windows.append({
                        "hwnd": h,
                        "title": title,
                        "left": rect[0],
                        "top": rect[1],
                        "right": rect[2],
                        "bottom": rect[3],
                        "width": rect[2] - rect[0],
                        "height": rect[3] - rect[1],
                        "process": process_name or "unknown",
                    })
        except Exception as e:
            logger.debug(f"append failed: {e}")
        return 1

    try:
        win32gui.EnumWindows(_cb, None)
        return {"success": True, "count": len(windows), "windows": windows}
    except Exception as e:
        return {"success": False, "error": str(e), "windows": []}


def get_window_info(window_title: str) -> dict:
    """Get detailed info about a specific window by title substring."""
    try:
        hwnd = _find_hwnd(window_title)
        if not hwnd:
            return {"success": False, "error": f"No window found: '{window_title}'"}

        rect = win32gui.GetWindowRect(hwnd)
        process_name = _get_process_name(hwnd)
        title = win32gui.GetWindowText(hwnd)
        is_visible = win32gui.IsWindowVisible(hwnd)
        is_minimized = win32gui.IsIconic(hwnd)
        is_maximized = win32gui.IsZoomed(hwnd)

        return {
            "success": True,
            "hwnd": hwnd,
            "title": title,
            "left": rect[0],
            "top": rect[1],
            "right": rect[2],
            "bottom": rect[3],
            "width": rect[2] - rect[0],
            "height": rect[3] - rect[1],
            "process": process_name or "unknown",
            "visible": is_visible,
            "minimized": is_minimized,
            "maximized": is_maximized,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_window_topmost(window_title: str, topmost: bool = True) -> dict:
    """Set a window to always-on-top or remove always-on-top."""
    try:
        hwnd = _find_hwnd(window_title)
        if not hwnd:
            return {"success": False, "error": f"No window found: '{window_title}'"}

        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST if topmost else win32con.HWND_NOTOPMOST,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
        )
        return {
            "success": True,
            "window": window_title,
            "topmost": topmost,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── public API ────────────────────────────────────────────────────────────────


def control_window(
    window_title: str = "", action: str = "list", params: Optional[dict] = None
) -> dict:
    """
    Control a visible window by title substring.

    Supported actions: minimize | maximize | restore | close | resize | move |
                       focus | list | info | topmost

    For action="close" a three-stage escalation is used:
      WM_CLOSE → Alt+F4 → taskkill /F /IM
    Each stage is audit-logged independently.

    Special actions (no window_title needed):
      list — list all visible windows
    """
    params = params or {}

    # ── Global actions that don't need a window_title ───────────────────────
    if action == "list":
        return list_windows()

    # ── Actions that need a window_title ────────────────────────────────────
    if not window_title:
        return {"success": False, "error": "window_title is required for this action"}

    try:
        # info and topmost use separate handlers
        if action == "info":
            return get_window_info(window_title)

        if action == "topmost":
            return set_window_topmost(window_title, params.get("enabled", True))

        hwnd = _find_hwnd(window_title)
        if not hwnd:
            return {"success": False, "error": f"No window found: '{window_title}'"}

        # ── non-close actions ───────────────────────────────────────────────
        if action == "minimize":
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

        elif action == "maximize":
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

        elif action == "restore":
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        elif action == "close":
            return _close_with_fallbacks(hwnd, window_title)

        elif action == "resize":
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = int(params.get("width", right - left))
            height = int(params.get("height", bottom - top))
            win32gui.MoveWindow(hwnd, left, top, width, height, True)

        elif action == "move":
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            new_left = int(params.get("left", left))
            new_top = int(params.get("top", top))
            win32gui.MoveWindow(
                hwnd, new_left, new_top, right - left, bottom - top, True
            )

        elif action == "focus":
            _force_focus(hwnd)

        else:
            return {"success": False, "error": f"Unknown action: '{action}'"}

        # ── focus verification (non-close only) ──────────────────────────────
        focused_hwnd = win32gui.GetForegroundWindow()
        focus_ok = (focused_hwnd == hwnd) if action == "focus" else True
        result = {
            "success": not (action == "focus" and not focus_ok),
            "window": window_title,
            "action": action,
            "focus_verified": focus_ok,
        }
        if action == "focus" and not focus_ok:
            result["error"] = f"Could not focus window '{window_title}'"
        audit_log.log_call(
            "control_window",
            {"window_title": window_title, "action": action, "params": params},
            result,
        )
        return result

    except Exception as exc:
        err_str = str(exc)
        if "Access is denied" in err_str or "error (5," in err_str:
            msg = (
                f"Cannot move/resize '{window_title}' — it runs as administrator. "
                f"JARVIS does not have permission to control elevated windows."
            )
            logger.warning(f"control_window: {msg}")
            return {"success": False, "error": msg, "elevated": True}
        logger.exception(f"control_window error: {exc}")
        return {"success": False, "error": str(exc)}


def _force_focus(hwnd: int) -> bool:
    """Bring a window to the foreground reliably.

    Uses three methods in order of reliability:
      1. SwitchToThisWindow  — bypasses foreground lock (most reliable)
      2. SetForegroundWindow + AttachThreadInput  — standard approach
      3. Minimize+restore    — nuclear option, always works

    Returns True if the foreground window matches *hwnd* after the attempt.
    """
    try:
        # Method 1: SwitchToThisWindow — bypasses Windows foreground lock
        import ctypes
        ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
        if win32gui.GetForegroundWindow() == hwnd:
            return True
    except Exception as e:
        logger.debug(f"GetForegroundWindow failed: {e}")

    try:
        # Method 2: Standard SetForegroundWindow + AttachThreadInput
        if win32gui.SetForegroundWindow(hwnd):
            return win32gui.GetForegroundWindow() == hwnd
        tid_target, _ = win32process.GetWindowThreadProcessId(hwnd)
        tid_current = win32api.GetCurrentThreadId()
        win32process.AttachThreadInput(tid_current, tid_target, True)
        win32gui.SetForegroundWindow(hwnd)
        win32process.AttachThreadInput(tid_current, tid_target, False)
        if win32gui.GetForegroundWindow() == hwnd:
            return True
    except Exception as e:
        logger.debug(f"GetForegroundWindow failed: {e}")

    # Method 3: Minimize then restore — forces Windows to foreground the window
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        import ctypes
        ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        return False
