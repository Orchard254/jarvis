"""
JARVIS Tool Registry.

Tier 1 — Native tool schemas (~13): tools with external state or cross-thread
         coordination that must go through the tool protocol.

Tier 2 — Python stdlib skills: live in skills/stdlib/ and are imported directly
         inside execute_code. NOT in TOOL_SCHEMAS — removed from the LLM's
         schema list to reduce decision overhead and hallucination risk.
         Imports here kept so skills/stdlib wrappers can re-export from tools/.
"""

# ── Original 9 tools ──────────────────────────────────────────────────────────
# ── 8 new tools ───────────────────────────────────────────────────────────────
from tools.browser import browser
from tools.capture_screen import capture_screen
from tools.clipboard_tool import clipboard
from tools.control_input import control_input
from tools.control_window import control_window
from tools.execute_code import execute_code
from tools.fetch_url import fetch_url
from tools.file_ops import file_ops
from tools.find_on_screen import find_on_screen
from tools.vision_query import vision_query
from tools.notify_user import notify_user
from tools.process_manager import process_manager
from tools.query_pc_index import query_pc_index
from tools.read_file import read_file
from tools.read_pc_state import read_pc_state
from tools.search_web import search_web
from tools.system_settings import system_settings
from tools.write_file import write_file
# ── Phase-2 tools: disconnected organs now wired up ──────────────────────────
from tools.memory_tool import memory
from tools.speak import speak
from tools.schedule_tool import schedule
# ── Phase-3: pending tools now implemented ────────────────────────────────────
from tools.ask_user import ask_user
from tools.network_check import network_check
from tools.time_calendar import time_calendar
from tools.listen import listen
from tools.watch_screen import watch_screen
from tools.send_message import send_message

TOOL_REGISTRY = {
    # ── Tier 1: Native tools (tool-protocol only) ────────────────────────────
    "execute_code": execute_code,
    "capture_screen": capture_screen,
    "read_pc_state": read_pc_state,
    "query_pc_index": query_pc_index,
    "browser": browser,
    "find_on_screen": find_on_screen,
    "vision_query": vision_query,
    "memory": memory,
    "speak": speak,
    "schedule": schedule,
    "ask_user": ask_user,
    "listen": listen,
    "watch_screen": watch_screen,
    # ── Phase-3 tools: now fully registered ───────────────────────────────────
    "network_check": network_check,
    "time_calendar": time_calendar,
    "send_message": send_message,
}

TOOL_SCHEMAS = [
    # ── Tier 1 schemas only ──────────────────────────────────────────────────
    # Tier-2 tools (network_check, send_message, time_calendar, file_ops,
    # process_manager, system_settings, clipboard, notify_user, search_web,
    # fetch_url, control_input, control_window, read_file, write_file) have
    # been moved to skills/stdlib/ — the LLM imports them in execute_code.
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": (
                "Run Python or PowerShell on the local machine. "
                "Primary tool for OS tasks, launching apps (os.startfile), "
                "installing software (winget), file ops, and system queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "language": {"type": "string", "enum": ["python", "powershell"]},
                },
                "required": ["code"],
            },
        },
    },{
        "type": "function",
        "function": {
            "name": "capture_screen",
            "description": "Screenshot the desktop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "object"},
                },
            },
        },
    },{
        "type": "function",
        "function": {
            "name": "read_pc_state",
            "description": "Read live desktop state: open windows, focused app, running processes.",
            "parameters": {"type": "object"},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_pc_index",
            "description": (
                "Search the local PC index for installed apps, files, or window state. "
                "Always call this BEFORE guessing a path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "type": {"type": "string", "enum": ["app", "file", "state"]},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser",
            "description": (
                "Control a web browser (Playwright). "
                "Use for interactive browsing, form filling, clicking buttons."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "launch",
                            "navigate",
                            "click",
                            "type",
                            "read_page",
                            "screenshot",
                            "close",
                            "back",
                            "forward",
                            "get_url",
                            "scroll",
                            "wait_for",
                        ],
                    },
                    "url": {"type": "string"},
                    "selector": {
                        "type": "string",
                        "description": "CSS selector or element description",
                    },
                    "text": {"type": "string", "description": "Text to type"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in ms (default 10000)",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_on_screen",
            "description": (
                "Find a UI element on screen by visual description using AI vision. "
                "Can optionally click the found element."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": (
                            "Description of what to find "
                            "(e.g. 'the blue Submit button', 'search bar', 'close button')"
                        ),
                    },
                    "click": {
                        "type": "boolean",
                        "description": "Click the found element (default false)",
                    },
                    "region": {
                        "type": "object",
                        "description": "Optional screen region {left, top, width, height}",
                    },
                },
                "required": ["description"],
            },
        },
    },{
        "type": "function",
        "function": {
            "name": "vision_query",
            "description": (
                "Capture the screen and ask gemma3:27b a specific question about what it sees. "
                "Use this whenever visual content is needed: detecting dialogs, reading UI text, "
                "confirming visual state, or finding element positions. "
                "ALWAYS use this instead of capture_screen — it returns a plain-text answer, "
                "not raw image data. One call does both capture and analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "Specific question about the screen. "
                            "Good: 'Is there an error dialog open?' / 'What text is in the search bar?' "
                            "Bad: 'describe the screen' (too generic — be targeted)."
                        ),
                    },
                    "region": {
                        "type": "object",
                        "description": "Optional crop {left, top, width, height}. Omit for full desktop.",
                    },
                },
                "required": ["question"],
            },
        },
    },# ── Phase-2: disconnected organs now wired up ─────────────────────────────────
{
        "type": "function",
        "function": {
            "name": "memory",
            "description": (
                "Active long-term memory control. "
                "store: save a key/value fact (e.g. key='user_docs_path', value='D:/Work'). "
                "recall: retrieve a stored value by key. "
                "forget: permanently delete a key. "
                "summary: get a digest of all stored preferences and frequent commands. "
                "search: full-text search across recent episodic history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["store", "recall", "forget", "summary", "search"],
                    },
                    "key": {
                        "type": "string",
                        "description": "Preference/fact key (required for store, recall, forget)",
                    },
                    "value": {
                        "description": "Value to store (required for 'store'; any JSON-serialisable type)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Text to search for in episodic history (required for 'search')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results for summary/search (default 10)",
                    },
                },
                "required": ["action"],
            },
        },
    },{
        "type": "function",
        "function": {
            "name": "speak",
            "description": (
                "Speak text aloud mid-task using the configured TTS engine (Edge TTS / Piper). "
                "Use this to narrate progress, read content to the user, or give verbal "
                "confirmations without ending the task. "
                "The orchestrator also speaks the final response automatically — "
                "only call this for intermediate speech during a multi-step task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to speak aloud",
                    },
                    "blocking": {
                        "type": "boolean",
                        "description": "Wait for audio to finish before continuing (default true). "
                                       "Set false to speak and keep working simultaneously.",
                    },
                },
                "required": ["text"],
            },
        },
    },{
        "type": "function",
        "function": {
            "name": "schedule",
            "description": (
                "Create, list, or cancel timed / recurring tasks. "
                "The Scheduler thread picks up new tasks within 5 seconds. "
                "Recurring tasks survive Jarvis restarts. "
                "Supported 'when' expressions: "
                "'in 10 minutes', 'in 2 hours', 'at 09:00', "
                "'every 30 minutes', 'every 2 hours', "
                "'every day at 07:30', 'on Monday at 09:00'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "cancel", "list"],
                    },
                    "command": {
                        "type": "string",
                        "description": "Natural-language task to run at the scheduled time (required for 'add')",
                    },
                    "when": {
                        "type": "string",
                        "description": "Schedule expression (required for 'add'). "
                                       "E.g. 'in 10 minutes', 'every day at 08:00'.",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "Task ID to cancel (required for 'cancel'). "
                                       "Get IDs from action='list'.",
                    },
                },
                "required": ["action"],
            },
        },
    },]

TOOL_SCHEMAS += [
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Pause the task and ask the user a question, waiting for their typed or "
                "button-click response before continuing.  Use this when the task is "
                "genuinely ambiguous and guessing would be wrong "
                "(e.g. 'I found 3 files named report — which one?').  "
                "Shows a GUI dialog (tkinter) or falls back to console input."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The question to display to the user.",
                    },
                    "choices": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of button labels.  If provided, the dialog shows "
                            "buttons instead of a free-text field."
                        ),
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Seconds to wait before auto-cancelling (default 60).",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "network_check",
            "description": (
                "Check network connectivity before tools that require the internet "
                "(search_web, fetch_url, browser).  Actions: "
                "ping (is a host reachable?), "
                "dns (resolve hostname to IPs), "
                "speed (rough download throughput), "
                "connections (active TCP/UDP connections), "
                "interfaces (list network adapters)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["ping", "dns", "speed", "connections", "interfaces"],
                        "description": "Check to perform (default: ping).",
                    },
                    "host": {
                        "type": "string",
                        "description": "Host for ping/dns actions (default: 8.8.8.8).",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Seconds before ping times out (default 3).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "time_calendar",
            "description": (
                "Real-time clock and calendar management.  "
                "get_time: current date/time/timezone.  "
                "get_events: upcoming calendar events (next N days).  "
                "create_event: add a new event to the calendar.  "
                "delete_event: remove an event by subject.  "
                "Backend: Outlook (default) or .ics file — set CALENDAR_BACKEND in .env."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_time", "get_events", "create_event", "delete_event"],
                    },
                    "subject": {
                        "type": "string",
                        "description": "Event title (required for create/delete).",
                    },
                    "start": {
                        "type": "string",
                        "description": "ISO datetime e.g. '2025-05-10T14:00:00' (required for create).",
                    },
                    "end": {
                        "type": "string",
                        "description": "ISO datetime for event end (defaults to start + 1 hour).",
                    },
                    "location": {
                        "type": "string",
                        "description": "Optional venue.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional notes/description.",
                    },
                    "all_day": {
                        "type": "boolean",
                        "description": "True to create an all-day event.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "How many days ahead to fetch (get_events, default 7).",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date filter YYYY-MM-DD (for delete_event).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listen",
            "description": (
                "Capture a single spoken utterance from the microphone and return "
                "the transcription.  Use mid-task when you need the user to say something "
                "(e.g. confirm a file name, spell out a value) without requiring them to type.  "
                "Pauses the wake-word listener during capture."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Optional text to speak aloud before opening the mic, "
                            "so the user knows it's their turn."
                        ),
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Seconds to wait for speech (default 10).",
                    },
                    "speak_prompt": {
                        "type": "boolean",
                        "description": "Whether to speak the prompt via TTS (default true).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "watch_screen",
            "description": (
                "Monitor the screen for a natural-language condition and return when it's met "
                "or a timeout expires.  Use for long-running async processes: downloads, "
                "installs, renders — anything where you'd otherwise need to poll with "
                "vision_query every loop iteration.  "
                "Example: condition='the download progress bar shows 100 percent'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "string",
                        "description": "Natural-language description of the screen state to wait for.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Max seconds to wait (default 60).",
                    },
                    "check_interval": {
                        "type": "integer",
                        "description": "Seconds between vision polls (default 5).",
                    },
                    "region": {
                        "type": "object",
                        "description": "Optional crop {left, top, width, height}.",
                    },
                },
                "required": ["condition"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": (
                "Send an outbound message to the user or a contact after a background task "
                "completes — more reliable than a toast notification.  "
                "Backends: email (SMTP) or telegram (Bot API).  "
                "Configure credentials in .env: SMTP_USER/SMTP_PASS for email, "
                "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID for Telegram."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "backend": {
                        "type": "string",
                        "enum": ["email", "telegram"],
                        "description": "Delivery backend (default: email).",
                    },
                    "body": {
                        "type": "string",
                        "description": "Message content (required).",
                    },
                    "to": {
                        "type": "string",
                        "description": "Recipient email address (required for email backend).",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line (email backend only).",
                    },
                    "html": {
                        "type": "boolean",
                        "description": "Render body as HTML in email (default false).",
                    },
                    "chat_id": {
                        "type": "string",
                        "description": (
                            "Telegram chat ID override.  Falls back to TELEGRAM_CHAT_ID in .env."
                        ),
                    },
                },
                "required": ["body"],
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
