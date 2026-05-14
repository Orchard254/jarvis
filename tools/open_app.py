"""
Primitive: open_app(app_name) — Launch an application by name or path.

Resolves app path from PC Index DB (scanned from registry + Start Menu shortcuts),
launches with proper subprocess, verifies the window appeared via Win32 enumeration,
and attempts to focus the window.

Fallbacks: PlatformAbstraction start_process -> os.startfile -> subprocess shell.
"""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from core.platform_abstraction import PlatformAbstraction
    _platform = PlatformAbstraction()
    _HAS_PLATFORM = True
except Exception:
    _HAS_PLATFORM = False


def _find_exe_in_index(app_name: str) -> str | None:
    """Look up the app's executable path from the PC Index DB."""
    try:
        from settings import PC_INDEX_DB
        from core.thread_db import get_connection

        if not PC_INDEX_DB.exists():
            return None

        conn = get_connection(PC_INDEX_DB, timeout=2.0)
        c = conn.cursor()

        clean = app_name.lower().replace(".exe", "").replace(".lnk", "")
        q = f"%{clean}%"

        # Exact name match first, preferring entries with a real exe_path
        c.execute(
            "SELECT exe_path FROM apps WHERE lower(name) = ? AND exe_path IS NOT NULL AND exe_path != '' ORDER BY source LIMIT 1",
            (clean,),
        )
        row = c.fetchone()
        if row and row[0]:
            return row[0]

        # LIKE match on name or exe_path
        c.execute(
            "SELECT exe_path FROM apps WHERE (lower(name) LIKE ? OR lower(exe_path) LIKE ?) AND exe_path IS NOT NULL AND exe_path != '' ORDER BY name LIMIT 1",
            (q, q),
        )
        row = c.fetchone()
        if row and row[0]:
            return row[0]

        return None
    except Exception as e:
        logger.debug(f"PC index lookup failed for '{app_name}': {e}")
        return None


def _resolve_to_exe(path: str, app_name: str) -> str | None:
    """Resolve a candidate path to a real .exe file, or None."""
    p = Path(path)
    if p.is_file():
        return str(p)
    if p.is_dir():
        exe = p / f"{app_name}.exe"
        if exe.exists():
            return str(exe)
        for child in p.iterdir():
            if child.suffix.lower() == ".exe" and app_name.lower() in child.stem.lower():
                return str(child)
    return None


def _wait_for_window(name: str, timeout: float = 5.0) -> bool:
    """Poll visible windows until one matching *name* appears.

    Uses pygetwindow instead of win32gui.EnumWindows to avoid the known
    ctypes/calling-convention crash that occurs with EnumWindows callbacks.
    """
    try:
        import pygetwindow as gw
    except ImportError:
        return False

    name_lower = name.lower()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            for w in gw.getAllWindows():
                if w.visible and w.title:
                    if name_lower in w.title.lower():
                        return True
        except Exception as e:
            logger.debug(f"lower failed: {e}")
        time.sleep(0.3)
    return False


def _is_running(app_name: str) -> tuple[bool, int | None]:
    """Check if a process matching *app_name* is already running.

    Returns (found, pid).
    """
    try:
        import psutil
    except ImportError:
        return False, None

    name_lower = app_name.lower().replace(".exe", "").replace(".lnk", "")
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info["name"] or "").lower().replace(".exe", "")
            if name_lower in pname or pname in name_lower:
                return True, proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False, None


def _focus_existing(name: str) -> bool:
    """Find and focus an existing window matching *name*. Returns True on success."""
    try:
        import pygetwindow as gw

        name_lower = name.lower()
        for w in gw.getAllWindows():
            if w.visible and w.title and name_lower in w.title.lower():
                try:
                    w.activate()
                    return True
                except Exception:
                    try:
                        w.restore()
                        w.activate()
                    except Exception as e:
                        logger.debug(f"activate failed: {e}")
                    return True
    except ImportError:
        pass

    if _HAS_PLATFORM:
        try:
            return bool(_platform.focus_window(name))
        except Exception as e:
            logger.debug(f"bool failed: {e}")
    return False


def open_app(app_name: str) -> dict:
    """Launch an application by name or path.

    Smart open:
      1. If the app is already running → focus its window → done.
      2. If not running → find its path → launch → wait for window → focus → done.
    """
    if not app_name or not isinstance(app_name, str):
        return {"success": False, "error": "Invalid app name"}

    # ── Step 1: Check if already running ─────────────────────────────────────
    running, existing_pid = _is_running(app_name)
    if running:
        focused = _focus_existing(app_name)
        msg = f"'{app_name}' is already running"
        if existing_pid:
            msg += f" (pid={existing_pid})"
        if focused:
            msg += " — focused"
            logger.info(msg)
            return {"success": True, "pid": existing_pid, "action": "focused"}
        logger.warning(f"{msg} — but could not focus window")
        return {"success": True, "pid": existing_pid, "action": "running_no_focus",
                "warning": "App is running but no visible window found to focus"}

    # ── Step 2: Not running — resolve path and launch ────────────────────────
    exe_path = _find_exe_in_index(app_name)
    if not exe_path and _HAS_PLATFORM:
        try:
            resolved = _platform.get_app_path(app_name)
            if resolved:
                exe_path = resolved
        except Exception as e:
            logger.debug(f"get_app_path failed: {e}")

    if exe_path:
        exe_path = _resolve_to_exe(exe_path, app_name)

    pid = None
    launched = False

    if exe_path and os.path.isfile(exe_path):
        try:
            proc = subprocess.Popen(
                [exe_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            pid = proc.pid
            launched = True
        except Exception as e:
            logger.debug(f"Launch with resolved path '{exe_path}' failed: {e}")

    if not launched and _HAS_PLATFORM:
        try:
            pid = _platform.start_process(app_name)
            if pid is not None:
                launched = True
        except Exception as e:
            logger.debug(f"Platform abstraction start failed for '{app_name}': {e}")

    if not launched and sys.platform == "win32":
        try:
            ret = os.startfile(app_name)
            if ret is not None and not isinstance(ret, int):
                logger.warning(f"os.startfile returned unexpected type: {type(ret).__name__}")
            launched = True
        except Exception as e:
            logger.debug(f"os.startfile failed for '{app_name}': {e}")

    if not launched:
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(
                    ["cmd", "/c", "start", "", app_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                proc = subprocess.Popen(
                    [app_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            launched = True
        except Exception as e:
            logger.debug(f"subprocess shell launch failed for '{app_name}': {e}")

    if not launched:
        return {
            "success": False,
            "error": f"Could not launch '{app_name}'. Try using execute_code with os.startfile or subprocess.",
        }

    # ── Step 3: Post-launch — wait for window and focus ─────────────────────
    window_seen = _wait_for_window(app_name, timeout=5.0)
    if _HAS_PLATFORM:
        try:
            _platform.focus_window(app_name)
        except Exception as e:
            logger.debug(f"focus_window failed: {e}")

    msg = f"Launched '{app_name}'"
    if pid:
        msg += f" (pid={pid})"

    if not window_seen:
        logger.warning(f"{msg} — no window appeared")
        return {
            "success": True,
            "pid": pid,
            "warning": f"Process '{app_name}' started but no visible window appeared within timeout",
            "action": "launched_no_window",
        }

    logger.info(msg)
    return {"success": True, "pid": pid, "action": "launched"}
