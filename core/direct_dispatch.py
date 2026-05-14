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
    r"^(?:open|launch|start)\s+(?!https?://)(.+)$",
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
    r"^(?:focus|switch to|go to)\s+(?!https?://)(.+)$",
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

# ── Type text ─────────────────────────────────────────────────────────────────
_register(
    r"^(?:type|write|enter)\s+[\"'](.+)[\"']$",
    "type_text",
    "Type text",
)

# ── Keyboard shortcuts ───────────────────────────────────────────────────────
_register(
    r"^(?:press|hit|send)\s+((?:ctrl|alt|shift|win|super|f\d+|enter|escape|tab|delete|backspace|space|home|end|pageup|pagedown|volumeup|volumedown|volumemute)(?:\+(?:ctrl|alt|shift|win|super|[a-z0-9]|f\d+|enter|escape|tab|delete|backspace|space))*)\s*$",
    "hotkey",
    "Press keyboard shortcut",
)

# ── System state ─────────────────────────────────────────────────────────────
_register(
    r"^(?:what(?:'s| is) running|list (?:windows|apps)|show (?:windows|apps)|show desktop)$",
    "window_list",
    "List running windows",
)

# ── System info ──────────────────────────────────────────────────────────────
_register(
    r"^(?:what(?:'s| is) the )?(?:time|date|day)(?:\?)?$",
    "time_check",
    "Check time/date",
)
_register(
    r"^(?:what(?:'s| is)(?:\s+the)? |check |show )?(?:system ?info|system ?status|hardware|ram|cpu|memory|disk ?space|battery)\s*(?:\?)?$",
    "system_info",
    "Check system info",
)

# ── Volume with words ────────────────────────────────────────────────────────
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
    elif action_key == "window_focus":
        return {"tool": "window", "args": {"action": "focus", "window_title": target}}
    elif action_key == "volume_set":
        try:
            level = int(target)
            level = max(0, min(100, level))
            ps_code = (
                "Add-Type -TypeDefinition '"
                "using System.Runtime.InteropServices; "
                "public class Vol { "
                '[DllImport("winmm.dll")] '
                "public static extern int waveOutSetVolume(IntPtr hwo, uint dwVolume); "
                "}'; "
                f"$v = [math]::Round({level} / 100 * 65535); "
                "$pair = $v -bor ($v -shl 16); "
                "[Vol]::waveOutSetVolume([IntPtr]::Zero, $pair); "
                f"Write-Output 'Volume set to {level}%'"
            )
            return {"tool": "exec", "args": {
                "action": "run",
                "code": ps_code,
                "language": "powershell",
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
    elif action_key == "type_text":
        return {"tool": "input", "args": {"action": "type", "text": target}}
    elif action_key == "hotkey":
        return {"tool": "input", "args": {"action": "hotkey", "keys": target.lower()}}
    elif action_key == "time_check":
        return {"tool": "exec", "args": {
            "action": "run",
            "code": "import datetime; now = datetime.datetime.now(); print(f'{now:%A, %B %d, %Y at %I:%M %p}')",
        }}
    elif action_key == "system_info":
        return {"tool": "window", "args": {"action": "state"}}
    elif action_key == "volume_up":
        return {"tool": "input", "args": {"action": "hotkey", "keys": "volumeup"}}
    elif action_key == "volume_down":
        return {"tool": "input", "args": {"action": "hotkey", "keys": "volumedown"}}

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
