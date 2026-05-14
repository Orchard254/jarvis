"""
JARVIS Tool Registry.

Tools that require non-trivial integration code the LLM would struggle to
write correctly inline via execute_code.  Simple operations (screenshots,
window control, file ops, etc.) the LLM can do directly with Python/PowerShell.
"""

# ── Vision & Screen ───────────────────────────────────────────────────────────
from tools.vision import vision_query

# ── System & Automation ───────────────────────────────────────────────────────
from tools.system import execute_code, query_pc_index

# ── Browser ───────────────────────────────────────────────────────────────────
from tools.browser import browser

# ── Voice I/O ─────────────────────────────────────────────────────────────────
from tools.voice import speak, listen

# ── Communication & Calendar ──────────────────────────────────────────────────
from tools.comm import send_message, schedule, time_calendar

# ── Memory ────────────────────────────────────────────────────────────────────
from tools.memory import memory


TOOL_REGISTRY = {
    # ── Vision & Screen ──────────────────────────────────────────────────────
    "vision_query": vision_query,
    # ── System & Automation ──────────────────────────────────────────────────
    "execute_code": execute_code,
    "query_pc_index": query_pc_index,
    # ── Browser ──────────────────────────────────────────────────────────────
    "browser": browser,
    # ── Voice I/O ────────────────────────────────────────────────────────────
    "speak": speak,
    "listen": listen,
    # ── Communication & Calendar ─────────────────────────────────────────────
    "send_message": send_message,
    "schedule": schedule,
    "time_calendar": time_calendar,
    # ── Memory & User Interaction ────────────────────────────────────────────
    "memory": memory,
}


TOOL_SCHEMAS = [
    # ═══════════════════════════════════════════════════════════════════════════
    # Vision & Screen
    # ═══════════════════════════════════════════════════════════════════════════
    {
        "type": "function",
        "function": {
            "name": "vision_query",
            "description": (
                "Capture the screen and ask gemma3:27b a specific question about what it sees. "
                "Use this whenever visual content is needed: detecting dialogs, reading UI text, "
                "confirming visual state, or finding element positions. "
                "One call does both capture and analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "Specific question about the screen. "
                            "Good: 'Is there an error dialog open?' / 'What text is in the search bar?' "
                            "Bad: 'describe the screen' (too generic)."
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
    },
    # ═══════════════════════════════════════════════════════════════════════════
    # System & Automation
    # ═══════════════════════════════════════════════════════════════════════════
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": (
                "Run Python or PowerShell on the local machine. "
                "Primary tool for OS tasks, launching apps (os.startfile), "
                "installing software (winget), file ops, and system queries. "
                "Set background=True for long-running tasks — returns immediately "
                "with a PID, then use action='check'/'wait'/'kill' to manage."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Code to execute (required for action='run')"},
                    "language": {"type": "string", "enum": ["python", "powershell"]},
                    "background": {"type": "boolean", "description": "Run in background (default false)."},
                    "action": {"type": "string", "enum": ["run", "check", "wait", "kill", "list"]},
                    "pid": {"type": "integer", "description": "Process ID for check/wait/kill actions"},
                    "timeout": {"type": "integer", "description": "Max seconds for wait action (default 60)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_pc_index",
            "description": (
                "Search the PC index for installed apps, recent files, or running windows/processes. "
                "Use this to quickly locate applications, find files, or check what's running."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text (e.g. app name, file name, process name)"},
                    "type": {"type": "string", "enum": ["app", "file", "state"]},
                },
                "required": ["query"],
            },
        },
    },
    # ═══════════════════════════════════════════════════════════════════════════
    # Browser
    # ═══════════════════════════════════════════════════════════════════════════
    {
        "type": "function",
        "function": {
            "name": "browser",
            "description": (
                "Control a web browser (Playwright). "
                "Use for interactive browsing, form filling, clicking buttons, "
                "tab management (close_tab, get_tabs, switch_tab)."
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
                            "close_tab",
                            "new_tab",
                            "get_tabs",
                            "switch_tab",
                            "back",
                            "forward",
                            "get_url",
                            "scroll",
                            "refresh",
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
    # ═══════════════════════════════════════════════════════════════════════════
    # Voice I/O
    # ═══════════════════════════════════════════════════════════════════════════
    {
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
    # ═══════════════════════════════════════════════════════════════════════════
    # Communication & Calendar
    # ═══════════════════════════════════════════════════════════════════════════
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
    {
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
    },
    {
        "type": "function",
        "function": {
            "name": "time_calendar",
            "description": (
                "Calendar management: list, create, and delete events.  "
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
                        "enum": ["get_events", "create_event", "delete_event"],
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
    # ═══════════════════════════════════════════════════════════════════════════
    # Memory & User Interaction
    # ═══════════════════════════════════════════════════════════════════════════
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
    },
]

# ── Merge custom drop-in tools ───────────────────────────────────────────────
from tools.custom import get_custom_schemas, get_custom_tools

_CUSTOM_REGISTRY = get_custom_tools()
_CUSTOM_SCHEMAS = get_custom_schemas()

if _CUSTOM_REGISTRY:
    TOOL_REGISTRY.update(_CUSTOM_REGISTRY)
    TOOL_SCHEMAS.extend(_CUSTOM_SCHEMAS)
