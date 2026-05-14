"""
Direct dispatch for trivial single-action commands.

Only handles commands that are 100% unambiguous and can never be misrouted:
  - "open <app>"  (single word app names only, no compound sentences)
  - "close/minimize/maximize <window>"
  - "screenshot"
  - volume controls
  - "press <shortcut>"
  - "mute" / "unmute"
  - time/date checks

Everything else goes to the LLM — it has the knowledge to figure it out.

Returns None when no pattern matches → falls through to the LLM planner.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_PATTERNS: list[tuple[re.Pattern, str, str]] = []


def _register(pattern: str, tool: str, description: str):
    """Register a direct dispatch pattern."""
    _PATTERNS.append((re.compile(pattern, re.IGNORECASE), tool, description))


# ── Window management ────────────────────────────────────────────────────────
# Only match simple "open <appname>" — single app name (1-3 words, no
# conjunctions like "and", "then", "to", "in").  Anything more complex
# goes to the LLM.
_APP_NAME = r"((?:(?!\b(?:and|then|to|in|on|with|for)\b)[a-zA-Z0-9_\-])+(?:\s+(?:(?!\b(?:and|then|to|in|on|with|for)\b)[a-zA-Z0-9_\-])+){0,2})"
_register(
    rf"^(?:open|launch|start)\s+{_APP_NAME}$",
    "window_open",
    "Open/launch an application",
)
_register(
    rf"^(?:close|quit|exit)\s+{_APP_NAME}$",
    "window_close",
    "Close a window/application",
)
_register(
    rf"^minimize\s+{_APP_NAME}$",
    "window_minimize",
    "Minimize a window",
)
_register(
    rf"^maximize\s+{_APP_NAME}$",
    "window_maximize",
    "Maximize a window",
)

# ── Volume ────────────────────────────────────────────────────────────────────
# Only handle simple up/down/mute via keyboard media keys (these always work).
# "set volume to 50" goes to the LLM which can use screen interaction
# to click the volume slider — PowerShell/Python volume APIs are unreliable.
_register(r"^(?:mute|unmute)(?:\s+audio)?$", "volume_toggle", "Mute/unmute")
_register(
    r"^(?:turn\s+)?(?:volume\s+)?(?:up|louder)$",
    "volume_up",
    "Increase volume",
)
_register(
    r"^(?:turn\s+)?(?:volume\s+)?(?:down|quieter|softer)$",
    "volume_down",
    "Decrease volume",
)

# ── Screenshots ──────────────────────────────────────────────────────────────
_register(
    r"^(?:take\s+a?\s*)?screenshot$",
    "screen_capture",
    "Take a screenshot",
)

# ── Keyboard shortcuts ───────────────────────────────────────────────────────
_register(
    r"^(?:press|hit)\s+((?:ctrl|alt|shift|win|super|f\d+|enter|escape|tab|delete|backspace|space|home|end|pageup|pagedown|volumeup|volumedown|volumemute)(?:\+(?:ctrl|alt|shift|win|super|[a-z0-9]|f\d+|enter|escape|tab|delete|backspace|space))*)\s*$",
    "hotkey",
    "Press keyboard shortcut",
)

# ── Time/date ────────────────────────────────────────────────────────────────
_register(
    r"^(?:what(?:'s| is) the )?(?:time|date|day)(?:\?)?$",
    "time_check",
    "Check time/date",
)


def _build_tool_call(action_key: str, match: re.Match) -> Optional[dict]:
    """Convert a matched pattern into a tool call dict."""
    groups = match.groups()
    target = groups[0].strip() if groups else ""

    if action_key == "window_open":
        return {"tool": "window", "args": {"action": "open", "app_name": target}}
    elif action_key == "window_close":
        return {"tool": "window", "args": {"action": "close", "window_title": target}}
    elif action_key == "window_minimize":
        return {"tool": "window", "args": {"action": "minimize", "window_title": target}}
    elif action_key == "window_maximize":
        return {"tool": "window", "args": {"action": "maximize", "window_title": target}}
    elif action_key == "volume_toggle":
        return {"tool": "input", "args": {"action": "hotkey", "keys": "volumemute"}}
    elif action_key == "volume_up":
        return {"tool": "input", "args": {"action": "hotkey", "keys": "volumeup"}}
    elif action_key == "volume_down":
        return {"tool": "input", "args": {"action": "hotkey", "keys": "volumedown"}}
    elif action_key == "screen_capture":
        return {"tool": "screen", "args": {"action": "capture"}}
    elif action_key == "hotkey":
        return {"tool": "input", "args": {"action": "hotkey", "keys": target.lower()}}
    elif action_key == "time_check":
        return {"tool": "exec", "args": {
            "action": "run",
            "code": "import datetime; now = datetime.datetime.now(); print(f'{now:%A, %B %d, %Y at %I:%M %p}')",
        }}

    return None


def try_direct_dispatch(user_input: str, execute_fn) -> Optional[str]:
    """Attempt to match and execute a command via direct dispatch.

    Args:
        user_input: The raw user command.
        execute_fn: Callable(tool_name, args) -> result dict.

    Returns:
        Response string if dispatched, None if no pattern matched.
    """
    text = user_input.strip()
    if not text:
        return None

    for pattern, action_key, description in _PATTERNS:
        m = pattern.match(text)
        if m:
            call = _build_tool_call(action_key, m)
            if call:
                logger.info(f"Direct dispatch: {description} → {call['tool']}({call['args']})")
                try:
                    result = execute_fn(call["tool"], call["args"])
                    ok = result.get("success", False)
                    if ok:
                        detail = result.get("result", result.get("output", "Done"))
                        return f"✓ {description}: {detail}" if detail else f"✓ {description}"
                    else:
                        error = result.get("error", "Unknown error")
                        return f"✗ {description} failed: {error}"
                except Exception as exc:
                    logger.error(f"Direct dispatch error: {exc}")
                    return f"✗ {description} failed: {exc}"

    return None
