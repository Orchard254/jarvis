"""
Reflex Layer — tool precondition enforcement.

Every tool call passes through preconditions before execution.
Zero LLM involvement. Milliseconds. Cannot fail.
"""

import logging
import os

logger = logging.getLogger(__name__)

_DANGEROUS_KEYS = {"alt+f4", "ctrl+w", "alt+tab", "ctrl+f4", "win+d"}

_session = {
    "window_focused": False,
    "focused_window_name": "",
    "last_tool": None,
}


def _os_has_foreground_window() -> bool:
    """Check whether the OS reports a non-empty foreground window title.

    Returns True if a real window is in the foreground, False if we can't
    determine it (e.g. pygetwindow not installed, or no window is focused).
    This makes the reflex layer aware of windows the *user* focused manually
    or that were focused by tools we don't track (e.g. click_element).
    """
    if os.name != "nt":
        return False
    try:
        import pygetwindow as gw
        win = gw.getActiveWindow()
        return bool(win and win.title.strip())
    except Exception:
        return False


def reset_session():
    _session["window_focused"] = False
    _session["focused_window_name"] = ""
    _session["last_tool"] = None


def _is_window_available(args: dict) -> bool:
    """Return True if a window is available for interaction.

    A window is considered available if:
      1. Our in-memory session says we focused one, OR
      2. The tool call specifies an explicit 'target' window
         (the adapter's _focus_target_window will handle focusing), OR
      3. The OS currently has a real foreground window.
    """
    if _session["window_focused"]:
        return True
    if args.get("target"):
        return True
    return _os_has_foreground_window()


def check_preconditions(tool_name: str, args: dict) -> str | None:
    if tool_name == "press_keys":
        keys = args.get("keys", "").lower().replace(" ", "")
        if any(d in keys for d in _DANGEROUS_KEYS):
            if not _is_window_available(args):
                return (
                    f"REFLEX BLOCKED: {args.get('keys')} requires a focused window. "
                    "Call focus_window first."
                )

    if tool_name == "type_text":
        if not _is_window_available(args):
            return (
                "REFLEX BLOCKED: type_text requires a focused window. "
                "Call focus_window first."
            )

    if tool_name == "open_app":
        _session["window_focused"] = True
        _session["focused_window_name"] = str(args.get("name", ""))

    if tool_name == "focus_window":
        _session["window_focused"] = True
        _session["focused_window_name"] = str(
            args.get("title") or args.get("process") or args.get("process_name", "")
        )

    if tool_name in ("close_app", "kill_process"):
        _session["window_focused"] = False

    _session["last_tool"] = tool_name
    return None


def wrap(execute_fn):
    """Wrap an execute function with reflex precondition checks."""
    def wrapped(tool_name: str, args: dict) -> dict:
        error = check_preconditions(tool_name, args)
        if error:
            logger.warning(f"Reflex blocked {tool_name}: {error}")
            return {
                "success": False,
                "error": error,
                "blocked_by": "reflex",
            }
        return execute_fn(tool_name, args)
    return wrapped

