"""
Reflex Layer — tool precondition enforcement.

Every tool call passes through preconditions before execution.
Zero LLM involvement. Milliseconds. Cannot fail.
"""

import logging

logger = logging.getLogger(__name__)

_DANGEROUS_KEYS = {"alt+f4", "ctrl+w", "alt+tab", "ctrl+f4", "win+d", "alt+f4"}

_session = {
    "window_focused": False,
    "focused_window_name": "",
    "last_tool": None,
}


def reset_session():
    _session["window_focused"] = False
    _session["focused_window_name"] = ""
    _session["last_tool"] = None


def check_preconditions(tool_name: str, args: dict) -> str | None:
    if tool_name == "press_keys":
        keys = args.get("keys", "").lower().replace(" ", "")
        if any(d in keys for d in _DANGEROUS_KEYS):
            if not _session["window_focused"]:
                return (
                    f"REFLEX BLOCKED: {args.get('keys')} requires a focused window. "
                    "Call focus_window first."
                )

    if tool_name == "type_text":
        if not _session["window_focused"]:
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
