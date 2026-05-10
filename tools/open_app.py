"""
Primitive: open_app(name)
Opens an application by name or full path using the Windows shell.

Resolution order
----------------
1. If ``name`` looks like a path (contains a separator or ends with .exe/.lnk)
   and the file exists → launch it directly via ``ShellExecuteW``.
2. Try Windows shell association  (cmd /c start "" <name>)
   which covers registered apps, PATH executables, and .lnk shortcuts
   that Windows itself knows about.
3. Fuzzy filesystem search in common locations (Desktop, Start Menu,
   Program Files, user AppData) looking for <name>.exe or <name>.lnk.
   The first match is launched.
"""

import glob
import logging
import os
import subprocess
import sys
from pathlib import Path

# Windows-only constant for hiding console windows
if sys.platform == "win32":
    CREATE_NO_WINDOW = 0x00080000  # CREATE_NO_WINDOW constant for hiding console windows
else:
    CREATE_NO_WINDOW = 0

logger = logging.getLogger(__name__)

# Directories scanned when shell association fails (ordered by likelihood)
_SEARCH_ROOTS: list[Path] = [
    Path(os.environ.get("USERPROFILE", "")) / "Desktop",
    Path(os.environ.get("PUBLIC", "")) / "Desktop",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
]


def _launch_path(path: str | Path) -> dict:
    """Launch an executable or shortcut by its full filesystem path."""
    try:
        import ctypes

        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "open", str(path), None, None, 1
        )
        if ret > 32:
            return {"success": True, "opened": str(path)}
        # ShellExecute error codes ≤ 32 are errors
        return {"success": False, "error": f"ShellExecuteW returned {ret} for '{path}'"}
    except Exception as e:
        logger.warning(f"_launch_path ShellExecuteW failed: {e}, falling back to Popen")

    # Fallback: subprocess
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", str(path)],
            shell=False,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return {"success": True, "opened": str(path)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _shell_start(name: str) -> dict:
    """Try to open via Windows shell association (handles registered apps + PATH)."""
    try:
        proc = subprocess.Popen(
            ["cmd", "/c", "start", "", name],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        proc.wait(timeout=3)
        # cmd /c start always returns 0 even if the app isn't found, but
        # stderr will be non-empty on failure.
        stderr = proc.stderr.read().decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and not stderr:
            return {"success": True, "opened": name}
        return {
            "success": False,
            "error": stderr or f"start returned {proc.returncode}",
        }
    except subprocess.TimeoutExpired:
        # App launched fine (it's running), the cmd shell just didn't exit.
        return {"success": True, "opened": name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _fuzzy_search(name: str) -> Path | None:
    """
    Search common locations for an .exe or .lnk whose stem matches `name`
    (case-insensitive, ignoring spaces/hyphens/underscores).
    Returns the first match, or None.
    """
    needle = name.lower().replace(" ", "").replace("-", "").replace("_", "")

    for root in _SEARCH_ROOTS:
        if not root.exists():
            continue
        for ext in ("*.exe", "*.lnk"):
            # Use rglob only for Start Menu (deep); flat glob elsewhere for speed
            pattern = root.rglob(ext) if "Start Menu" in str(root) else root.glob(ext)
            for candidate in pattern:
                stem = (
                    candidate.stem.lower()
                    .replace(" ", "")
                    .replace("-", "")
                    .replace("_", "")
                )
                if needle in stem or stem in needle:
                    logger.info(f"open_app: fuzzy match '{candidate}'")
                    return candidate
    return None


def open_app(name: str) -> dict:
    """
    Open an application.

    Parameters
    ----------
    name : str
        Either a bare app name ("notepad", "ultraviewr"),
        or a full/partial filesystem path
        (e.g., "%USERPROFILE%/Desktop/UltraViewr.exe").
    """
    name = name.strip()

    # ── Step 1: explicit path ──────────────────────────────────────────
    p = Path(name)
    if (
        os.sep in name or "/" in name or name.lower().endswith((".exe", ".lnk"))
    ) and p.exists():
        logger.info(f"open_app: launching by explicit path '{p}'")
        return _launch_path(p)

    # ── Step 2: Windows shell association ─────────────────────────────
    result = _shell_start(name)
    if result["success"]:
        logger.info(f"open_app: shell-start succeeded for '{name}'")
        return result

    logger.info(
        f"open_app: shell-start failed ({result.get('error')}), trying fuzzy search"
    )

    # ── Step 3: fuzzy filesystem search ───────────────────────────────
    found = _fuzzy_search(name)
    if found:
        return _launch_path(found)

    logger.error(f"open_app: could not find '{name}' anywhere")
    return {
        "success": False,
        "error": (
            f"Could not find '{name}'. If you know the full path, pass it directly."
        ),
    }
