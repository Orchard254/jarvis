"""
JARVIS Tool Registry — 6 consolidated tools.

Each tool has a single responsibility and uses an `action` parameter
for operation selection. Tools self-verify: check state before acting,
report partial success honestly, never return success=True with hidden warnings.

Tools:
  1. screen  — perception (see the screen, find elements, read text)
  2. input   — mouse + keyboard (click, type, hotkey, scroll, drag)
  3. window  — app/window management + desktop state
  4. browser — web interaction via Playwright
  5. exec    — code execution + file I/O (the escape hatch)
  6. memory  — persistent key-value memory
"""

from __future__ import annotations

from tools.screen import screen
from tools.input import input as input_tool
from tools.window import window
from tools.browser import browser
from tools.mem import memory
from tools.exec import exec as exec_tool

TOOL_REGISTRY = {
    "screen": screen,
    "input": input_tool,
    "window": window,
    "browser": browser,
    "memory": memory,
    "exec": exec_tool,
}

TOOL_SCHEMAS = [
    # ── 1. screen — unified perception ─────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "screen",
            "description": (
                "Perceive the screen. Actions: "
                "'capture' (screenshot; set grid=true for coordinate grid overlay), "
                "'find' (locate UI element by visible text using Windows UIA — most reliable, no OCR; "
                "falls back to vision+grid for apps UIA can't see like Chrome web content), "
                "'tree' (get UIA accessibility tree of all interactive elements with names and bounds), "
                "'elements' (list ALL interactive elements with coordinates — merges UIA + vision; "
                "best for exploring an unfamiliar app or when you don't know the element's name), "
                "'query' (ask vision model about screen content), "
                "'ocr' (read visible text from a region). "
                "Prefer 'find' for clicking known elements. Use 'elements' to discover what's clickable. "
                "Do NOT use for sending keyboard/mouse input — use input() instead. "
                "Do NOT use for launching apps — use window(open) instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["capture", "find", "tree", "elements", "query", "ocr"],
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
                        "description": "Max seconds for find timeout (default 5)",
                    },
                    "click": {
                        "type": "boolean",
                        "description": "Click the element after finding it (default false, only for 'find' action)",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Max depth for 'tree'/'elements' action (default 3)",
                    },
                    "grid": {
                        "type": "boolean",
                        "description": "Overlay coordinate grid on screenshot (for 'capture' action, default false)",
                    },
                    "grid_size": {
                        "type": "integer",
                        "description": "Grid cell size in pixels (default 100, only with grid=true)",
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
                "'drag' (drag from one point to another). "
                "For clicking a known UI element, prefer screen(action='find', text='...', click=true) — "
                "it uses UIA for deterministic targeting. "
                "Do NOT use for launching apps — use window(open) instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["click", "type", "hotkey", "scroll", "drag"],
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
                        "description": "X coordinate for click/drag",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate for click/drag",
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
                        "description": "Target window title for 'type' action — focuses the window before typing",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ── 3. window — app/window management + desktop state ──────────────────────
    {
        "type": "function",
        "function": {
            "name": "window",
            "description": (
                "Manage applications and windows. Actions: "
                "'open' (launch an app by name — checks if already running, focuses if so, "
                "else finds path, launches, waits for window, and focuses), "
                "'close' (close window by title), "
                "'focus' (bring window to foreground by title), "
                "'list' (list all visible windows), "
                "'minimize'/'maximize' (window state), "
                "'state' (live snapshot of open windows, running processes, focused app). "
                "Do NOT use for clicking UI elements inside a window — use screen(find) or input(click). "
                "Do NOT use for taking screenshots — use screen(capture)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["open", "close", "focus", "list", "minimize", "maximize", "state"],
                        "description": "Window action to perform",
                    },
                    "app_name": {
                        "type": "string",
                        "description": "App name to launch (required for 'open' action, e.g. 'chrome', 'notepad')",
                    },
                    "window_title": {
                        "type": "string",
                        "description": "Window title substring for close/focus/minimize/maximize",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ── 4. browser — web interaction ───────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "browser",
            "description": (
                "Control a web browser for interactive browsing. "
                "Auto-connects to existing Chrome via CDP (port 9222) if available — "
                "this controls the user's actual browser, not a separate one. "
                "Falls back to launching a new Chrome if CDP is unavailable. "
                "Actions: 'navigate' (go to URL, auto-launches browser), "
                "'click' (click element by CSS selector), "
                "'type' (type text into field by selector), "
                "'read_page' (get page text content), "
                "'screenshot' (capture browser page), "
                "'scroll' (scroll down the page). "
                "For tab management use input(hotkey) — e.g. 'ctrl+t', 'ctrl+w', 'ctrl+tab'. "
                "For back/forward use input(hotkey) — 'alt+left', 'alt+right'. "
                "For refresh use input(hotkey) — 'f5'. "
                "Do NOT use for desktop app interaction — use screen() and input() instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["navigate", "click", "type", "read_page", "screenshot", "scroll"],
                        "description": "Browser action",
                    },
                    "url": {"type": "string", "description": "URL (required for navigate)"},
                    "selector": {"type": "string", "description": "CSS selector or Playwright text locator, e.g. '#btn' or 'text=Submit'"},
                    "text": {"type": "string", "description": "Text to type into field"},
                    "timeout": {"type": "integer", "description": "Timeout in ms (default 30000)"},
                },
                "required": ["action"],
            },
        },
    },
    # ── 5. exec — code execution + file I/O ────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "exec",
            "description": (
                "Execute code and manage files. Actions: "
                "'run' (execute Python/PowerShell — the escape hatch for anything not covered by other tools), "
                "'read' (read file content by path), "
                "'write' (write content to file by path). "
                "Do NOT use for launching apps — use window(open). "
                "Do NOT use for web browsing — use browser(). "
                "Do NOT use for screen interaction — use screen() or input()."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["run", "read", "write"],
                        "description": "Action to perform",
                    },
                    "code": {"type": "string", "description": "Python/PowerShell code (required for 'run' action)"},
                    "language": {"type": "string", "enum": ["python", "powershell"], "description": "Code language (default 'python')"},
                    "path": {"type": "string", "description": "File path (required for read/write actions)"},
                    "content": {"type": "string", "description": "File content (required for write action)"},
                    "background": {"type": "boolean", "description": "Run code in background (default false)"},
                    "timeout": {"type": "integer", "description": "Max seconds for execution (default 30)"},
                },
                "required": ["action"],
            },
        },
    },
    # ── 6. memory — persistent key-value memory ───────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "memory",
            "description": (
                "Persistent memory for storing and retrieving facts. Actions: "
                "'store' (save a fact: key+value pair — use for user preferences, learned info), "
                "'recall' (retrieve a fact by key), "
                "'search' (semantic search across all stored memories). "
                "Do NOT store code snippets — those go into skills."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["store", "recall", "search"],
                        "description": "Memory action",
                    },
                    "key": {"type": "string", "description": "Fact key (required for store, recall)"},
                    "value": {"description": "Value to store (required for store action; any JSON type)"},
                    "query": {"type": "string", "description": "Search text for 'search' action"},
                    "limit": {"type": "integer", "description": "Max results for search (default 10)"},
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
