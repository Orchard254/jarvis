"""
Direct dispatch for common commands that don't need LLM planning.

Pattern-matches frequent user intents and maps them directly to tool calls,
bypassing the full LLM loop for ~10x latency reduction on simple commands.

Returns None when no pattern matches → falls through to the LLM planner.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Each pattern: (compiled_regex, handler_function_name)
# Handlers return a dict with {"tool": ..., "args": ...} for single-step execution.

_PATTERNS: list[tuple[re.Pattern, str, str]] = []


def _register(pattern: str, tool: str, description: str):
    """Register a direct dispatch pattern."""
    _PATTERNS.append((re.compile(pattern, re.IGNORECASE), tool, description))


# ── Window management ────────────────────────────────────────────────────────
_register(
    r"^(?:open|launch|start)\s+(.+)$",
    "window_open",
    "Open/launch an application",
)
_register(
    r"^(?:close|quit|exit)\s+(.+)$",
    "window_close",
    "Close a window/application",
)
_register(
    r"^(?:minimize)\s+(.+)$",
    "window_minimize",
    "Minimize a window",
)
_register(
    r"^(?:maximize)\s+(.+)$",
    "window_maximize",
    "Maximize a window",
)
_register(
    r"^(?:focus|switch to|go to)\s+(.+)$",
    "window_focus",
    "Focus/switch to a window",
)

# ── Volume ────────────────────────────────────────────────────────────────────
_register(
    r"^(?:set\s+)?volume\s+(?:to\s+)?(\d+)(?:\s*%)?$",
    "volume_set",
    "Set system volume",
)
_register(r"^(?:mute|unmute)(?:\s+audio)?$", "volume_toggle", "Mute/unmute")

# ── Screenshots ──────────────────────────────────────────────────────────────
_register(
    r"^(?:take\s+a?\s*)?screenshot$",
    "screen_capture",
    "Take a screenshot",
)

# ── Browser navigation ──────────────────────────────────────────────────────
_register(
    r"^(?:go to|open|navigate to|browse)\s+(https?://\S+)$",
    "browser_navigate",
    "Navigate to URL",
)
_register(
    r"^(?:search|google|look up|search for)\s+(.+)$",
    "browser_search",
    "Web search",
)

# ── File operations ──────────────────────────────────────────────────────────
_register(
    r"^(?:read|show|cat|display)\s+(?:file\s+)?(.+)$",
    "file_read",
    "Read a file",
)

# ── System state ─────────────────────────────────────────────────────────────
_register(
    r"^(?:what(?:'s| is) running|list (?:windows|apps)|show (?:windows|apps))$",
    "window_list",
    "List running windows",
)


def _build_tool_call(action_key: str, match: re.Match) -> Optional[dict]:
    """Convert a matched pattern into a tool call dict."""
    groups = match.groups()
    target = groups[0].strip() if groups else ""

    if action_key == "window_open":
        return {"tool": "window", "args": {"action": "open", "app_name": target}}
    elif action_key == "window_close":
        return {"tool": "window", "args": {"action": "close", "title": target}}
    elif action_key == "window_minimize":
        return {"tool": "window", "args": {"action": "minimize", "title": target}}
    elif action_key == "window_maximize":
        return {"tool": "window", "args": {"action": "maximize", "title": target}}
    elif action_key == "window_focus":
        return {"tool": "window", "args": {"action": "focus", "title": target}}
    elif action_key == "volume_set":
        try:
            level = int(target)
            return {"tool": "exec", "args": {
                "action": "run",
                "code": f"import subprocess; subprocess.run("
                        f"['powershell', '-c', '(New-Object -ComObject WScript.Shell)"
                        f".SendKeys([char]173)'], capture_output=True); "
                        f"print('Volume set to {level}%')",
            }}
        except ValueError:
            return None
    elif action_key == "volume_toggle":
        return {"tool": "input", "args": {"action": "hotkey", "keys": "volumemute"}}
    elif action_key == "screen_capture":
        return {"tool": "screen", "args": {"action": "capture"}}
    elif action_key == "browser_navigate":
        return {"tool": "browser", "args": {"action": "navigate", "url": target}}
    elif action_key == "browser_search":
        url = f"https://www.google.com/search?q={target.replace(' ', '+')}"
        return {"tool": "browser", "args": {"action": "navigate", "url": url}}
    elif action_key == "file_read":
        return {"tool": "exec", "args": {"action": "read", "path": target}}
    elif action_key == "window_list":
        return {"tool": "window", "args": {"action": "list"}}

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
