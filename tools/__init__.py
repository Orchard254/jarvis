"""
JARVIS Tool Registry — 8 consolidated tools.

Each tool has a single responsibility and uses an `action` parameter
for operation selection. Tools self-verify: check state before acting,
report partial success honestly, never return success=True with hidden warnings.
"""

from __future__ import annotations

from tools.screen import screen
from tools.input import input as input_tool
from tools.window import window
from tools.system import system
from tools.browser import browser
from tools.mem import memory
from tools.exec import exec as exec_tool
from tools.speak import speak

TOOL_REGISTRY = {
    "screen": screen,
    "input": input_tool,
    "window": window,
    "system": system,
    "browser": browser,
    "memory": memory,
    "exec": exec_tool,
    "speak": speak,
}

TOOL_SCHEMAS = [
    # ── 1. screen — unified perception ─────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "screen",
            "description": (
                "Perceive the screen. Actions: "
                "'capture' (screenshot, returns base64 image), "
                "'find' (locate UI element by visible text using Windows UIA — most reliable, no OCR), "
                "'tree' (get UIA accessibility tree of all interactive elements with names and bounds), "
                "'query' (ask vision model about screen content), "
                "'watch' (monitor screen until condition met or timeout), "
                "'ocr' (read visible text from a region). "
                "Prefer 'find' over 'query' for locating buttons/text fields — UIA is deterministic. "
                "Do NOT use for sending keyboard/mouse input — use input() instead. "
                "Do NOT use for launching apps — use window(open) instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["capture", "find", "tree", "query", "watch", "ocr"],
                        "description": "What to do",
                    },
                    "text": {
                        "type": "string",
                        "description": "Visible text to find (required for 'find' action)",
                    },
                    "question": {
                        "type": "string",
                        "description": "Question about screen content (required for 'query' action)",
                    },
                    "condition": {
                        "type": "string",
                        "description": "Natural language condition to watch for (required for 'watch' action), e.g. 'download complete'",
                    },
                    "region": {
                        "type": "object",
                        "description": "Screen region {left, top, width, height} for crop",
                    },
                    "window_title": {
                        "type": "string",
                        "description": "Window title substring to scope the action to",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Max seconds for watch/find timeout (default 30 for watch, 5 for find)",
                    },
                    "check_interval": {
                        "type": "integer",
                        "description": "Seconds between vision polls during watch (default 5)",
                    },
                    "click": {
                        "type": "boolean",
                        "description": "Click the element after finding it (default false, only for 'find' action)",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Max depth for 'tree' action (default 3)",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ── 2. input — mouse + keyboard ────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "input",
            "description": (
                "Send mouse or keyboard input. Actions: "
                "'click' (click at x,y or on element by text), "
                "'type' (type text at current focus), "
                "'hotkey' (send keyboard shortcut like 'ctrl+c', 'alt+tab'), "
                "'scroll' (scroll up/down N clicks), "
                "'drag' (drag from one point to another), "
                "'move' (move mouse to x,y). "
                "For clicking a known UI element, prefer screen(action='find', text='...', click=true) — "
                "it uses UIA for deterministic targeting. "
                "Do NOT use for launching apps — use window(open) instead. "
                "Do NOT use for window management — use window(close/focus/etc) instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["click", "type", "hotkey", "scroll", "drag", "move"],
                        "description": "Input action to perform",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type (required for 'type' action)",
                    },
                    "keys": {
                        "type": "string",
                        "description": "Keyboard shortcut with '+' separator, e.g. 'ctrl+c', 'alt+tab' (required for 'hotkey' action)",
                    },
                    "x": {
                        "type": "integer",
                        "description": "X coordinate for click/move/drag",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate for click/move/drag",
                    },
                    "target_text": {
                        "type": "string",
                        "description": "Click element by visible text (alternative to x,y for 'click')",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Scroll direction (default 'down')",
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "Number of scroll clicks (default 1)",
                    },
                    "from_x": {"type": "integer", "description": "Drag start X"},
                    "from_y": {"type": "integer", "description": "Drag start Y"},
                    "to_x": {"type": "integer", "description": "Drag end X"},
                    "to_y": {"type": "integer", "description": "Drag end Y"},
                    "window_title": {
                        "type": "string",
                        "description": "Target window title for 'type' action — focuses the window before typing (e.g. 'Notepad', 'Chrome')",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ── 3. window — app/window management ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "window",
            "description": (
                "Manage applications and windows. Actions: "
                "'open' (launch an app by name — checks if already running, focuses if so, "
                "else finds path, launches, waits for window, and focuses. One-call done.), "
                "'close' (close window by title), "
                "'focus' (bring window to foreground by title), "
                "'list' (list all visible windows and running processes), "
                "'info' (get window position, size, process), "
                "'minimize'/'maximize'/'restore' (window state). "
                "For open, always prefer this over exec(run) for launching apps. "
                "Do NOT use for clicking UI elements inside a window — use screen(find) or input(click). "
                "Do NOT use for taking screenshots — use screen(capture)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["open", "close", "focus", "list", "info", "resize", "move", "minimize", "maximize", "restore"],
                        "description": "Window action to perform",
                    },
                    "app_name": {
                        "type": "string",
                        "description": "App name to launch (required for 'open' action, e.g. 'chrome', 'notepad')",
                    },
                    "window_title": {
                        "type": "string",
                        "description": "Window title substring for close/focus/info/minimize/maximize/restore",
                    },
                    "params": {
                        "type": "object",
                        "description": "Additional params: {width, height, left, top} for resize/move",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ── 4. system — live system state ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "system",
            "description": (
                "Query live system state. Actions: "
                "'state' (snapshot of open windows, running processes, focused app, clipboard), "
                "'search_app' (find installed apps by name — returns exe paths), "
                "'search_file' (find files on disk by name), "
                "'hardware' (CPU, RAM, disk usage). "
                "Call state() before planning to understand what's running. "
                "Do NOT use for launching apps or managing windows — use window() instead. "
                "Do NOT use for screen perception — use screen() instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["state", "search_app", "search_file", "hardware"],
                        "description": "What system info to retrieve",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search term (required for search_app/search_file actions)",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ── 5. browser — web interaction (unchanged) ──────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "browser",
            "description": (
                "Control a web browser for interactive browsing. "
                "Use for: navigating pages, filling forms, clicking links, managing tabs. "
                "Actions: launch, navigate, click, type, read_page, screenshot, close, "
                "close_tab, new_tab, get_tabs, switch_tab, back, forward, get_url, "
                "scroll, refresh, wait_for. "
                "Do NOT use for simple HTTP requests or API calls (use exec with 'search_web' or 'fetch' actions)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["launch", "navigate", "click", "type", "read_page", "screenshot", "close", "close_tab", "new_tab", "get_tabs", "switch_tab", "back", "forward", "get_url", "scroll", "refresh", "wait_for"],
                        "description": "Browser action",
                    },
                    "url": {"type": "string", "description": "URL (required for navigate)"},
                    "selector": {"type": "string", "description": "CSS selector or Playwright text locator, e.g. '#btn' or 'text=Submit'"},
                    "text": {"type": "string", "description": "Text to type into field"},
                    "timeout": {"type": "integer", "description": "Timeout in ms (default 10000)"},
                },
                "required": ["action"],
            },
        },
    },
    # ── 6. memory — persistent memory + scheduling ─────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "memory",
            "description": (
                "Persistent memory and task scheduling. Actions: "
                "'store' (save a fact: key+value pair — use for user preferences, learned info), "
                "'recall' (retrieve a fact by key), "
                "'forget' (remove a fact), "
                "'search' (semantic search across all stored memories), "
                "'summary' (list all stored facts), "
                "'schedule' (create timed/recurring task — e.g. 'in 10 minutes', 'every day at 09:00'), "
                "'cancel' (cancel a scheduled task by task_id), "
                "'list' (list all scheduled tasks). "
                "Do NOT store code snippets — those go into skills."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["store", "recall", "forget", "search", "summary", "schedule", "cancel", "list"],
                        "description": "Memory or scheduling action",
                    },
                    "key": {"type": "string", "description": "Fact key (required for store, recall, forget)"},
                    "value": {"description": "Value to store (required for store action; any JSON type)"},
                    "query": {"type": "string", "description": "Search text for 'search' action"},
                    "command": {"type": "string", "description": "Task command (required for schedule action), e.g. 'speak \"time for standup\"'"},
                    "when": {"type": "string", "description": "Schedule expression (required for schedule). Examples: 'in 10 minutes', 'every 30 minutes', 'every day at 07:30', 'on Monday at 09:00'"},
                    "task_id": {"type": "string", "description": "Task ID to cancel (required for cancel action)"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["action"],
            },
        },
    },
    # ── 7. exec — code execution + file/system ops ────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "exec",
            "description": (
                "Execute code, manage files, and call system utilities. Actions: "
                "'run' (execute Python/PowerShell — use only when no dedicated tool fits), "
                "'read' (read file content by path), "
                "'write' (write content to file by path), "
                "'clipboard' (get current clipboard text), "
                "'notify' (show desktop notification), "
                "'search_web' (search the web by query, returns results), "
                "'fetch' (fetch URL content). "
                "Do NOT use for launching apps — use window(open). "
                "Do NOT use for web browsing — use browser(). "
                "Do NOT use for screen interaction — use screen() or input(). "
                "Do NOT use for window management — use window()."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["run", "read", "write", "clipboard", "notify", "search_web", "fetch"],
                        "description": "Action to perform",
                    },
                    "code": {"type": "string", "description": "Python/PowerShell code (required for 'run' action)"},
                    "language": {"type": "string", "enum": ["python", "powershell"], "description": "Code language (default 'python')"},
                    "path": {"type": "string", "description": "File path (required for read/write actions)"},
                    "content": {"type": "string", "description": "File content (required for write action)"},
                    "message": {"type": "string", "description": "Notification message (required for notify action)"},
                    "urgency": {"type": "string", "enum": ["low", "normal", "high"], "description": "Notification urgency (default 'low')"},
                    "query": {"type": "string", "description": "Search query (required for search_web action)"},
                    "url": {"type": "string", "description": "URL to fetch (required for fetch action)"},
                    "background": {"type": "boolean", "description": "Run code in background (default false, only for 'run' action)"},
                    "timeout": {"type": "integer", "description": "Max seconds for execution (default 30)"},
                },
                "required": ["action"],
            },
        },
    },
    # ── 8. speak — voice I/O ──────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "speak",
            "description": (
                "Voice input/output. Actions: "
                "'speak' (output text via TTS — narrate progress to user), "
                "'ask' (show dialog with question, wait for typed/clicked response), "
                "'listen' (capture spoken input via microphone). "
                "Use ask() when you need user input. "
                "Use speak() to narrate during long tasks. "
                "Use listen() when the user should speak aloud. "
                "Do NOT use for notifying the user silently — use exec(notify). "
                "Do NOT use for screen interaction or clicking — use screen() or input()."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["speak", "ask", "listen"],
                        "description": "Voice action",
                    },
                    "text": {"type": "string", "description": "Text to speak aloud (required for 'speak' action)"},
                    "prompt": {"type": "string", "description": "Prompt text to show or speak (for 'ask' or 'listen')"},
                    "choices": {"type": "array", "items": {"type": "string"}, "description": "Button labels for 'ask' action (optional; shows buttons instead of text field)"},
                    "timeout_seconds": {"type": "integer", "description": "Timeout in seconds (default 60 for ask, 10 for listen)"},
                    "blocking": {"type": "boolean", "description": "Wait for TTS to finish (default true, only for 'speak')"},
                },
                "required": ["action"],
            },
        },
    },
]

# ── Merge custom drop-in tools ───────────────────────────────────────────────
from tools.custom import get_custom_schemas, get_custom_tools

_CUSTOM_REGISTRY = get_custom_tools()
_CUSTOM_SCHEMAS = get_custom_schemas()

if _CUSTOM_REGISTRY:
    TOOL_REGISTRY.update(_CUSTOM_REGISTRY)
    TOOL_SCHEMAS.extend(_CUSTOM_SCHEMAS)
