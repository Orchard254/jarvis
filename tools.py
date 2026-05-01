# tools.py — Tool definitions in Ollama/OpenAI function-calling format
# (Ollama wraps each tool as {"type": "function", "function": {...}})

# DYNAMIC SCRIPTING: Primary execution method for complex tasks


def _tool(name: str, description: str, properties: dict, required: list = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOLS = [
    # ═══════════════════════════════════════════════════════════════════════
    # 🚀 DYNAMIC SCRIPTING — PRIMARY EXECUTION METHOD
    # ═══════════════════════════════════════════════════════════════════════
    # Use this for ANY complex task. The LLM writes custom Python code.
    _tool(
        "execute_dynamic_script",
        "PRIMARY METHOD: Execute a custom Python script for complex tasks. "
        "Use this INSTEAD of hardcoded tools when the task requires multiple steps, "
        "file operations, data processing, or custom logic. "
        "The script runs in a secure sandbox with limited imports (os, pathlib, shutil, json, etc.). "
        "Examples: organize files by type, analyze logs, batch rename files, process images, "
        "generate reports, compare directories, extract data from files.",
        {
            "script": {
                "type": "string",
                "description": "Python code to execute. Keep under 50 lines. Use only safe imports."
            },
            "description": {
                "type": "string",
                "description": "Brief description of what the script does (1 sentence)"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30, max 60)",
                "default": 30
            }
        },
        ["script", "description"]
    ),
    
    # ═══════════════════════════════════════════════════════════════════════
    # ⚡ QUICK ACTIONS — For simple, time-critical tasks only
    # ═══════════════════════════════════════════════════════════════════════
    # Only use these for trivial operations where speed matters more than flexibility
    _tool("get_time", "Get the current local time (QUICK - use instead of script for time queries)", {}),
    _tool("get_date", "Get today's date (QUICK)", {}),
    _tool("screenshot", "Take a screenshot instantly (QUICK verification)", {}),
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🔧 LEGACY HARDCODED TOOLS — Backward compatibility only
    # ═══════════════════════════════════════════════════════════════════════
    # DEPRECATED: Prefer execute_dynamic_script for new implementations
    # These remain for backward compatibility and extremely simple cases
    
    # File operations (use dynamic scripting for complex file tasks)
    _tool(
        "read_file",
        "Read a text file (LEGACY - use dynamic script for multiple files or processing)",
        {"path": {"type": "string", "description": "Full file path"}},
        ["path"],
    ),
    _tool(
        "create_file",
        "Create a file (LEGACY - use dynamic script for batch operations)",
        {
            "path": {"type": "string", "description": "Full file path"},
            "content": {"type": "string", "description": "File content"},
        },
        ["path"],
    ),
    _tool(
        "open_file",
        "Open a file with default app (LEGACY)",
        {"path": {"type": "string", "description": "File path"}},
        ["path"],
    ),
    
    # App control (simple cases only)
    _tool(
        "open_app",
        "Open an application (LEGACY - chrome, notepad, calculator, etc.)",
        {"app_name": {"type": "string", "description": "Application name"}},
        ["app_name"],
    ),
    _tool(
        "close_app",
        "Force-close an application (LEGACY)",
        {"app_name": {"type": "string", "description": "Process name"}},
        ["app_name"],
    ),
    _tool("list_running_apps", "List running applications (LEGACY)", {}),
    
    # System info (quick queries)
    _tool("battery_status", "Get battery level (LEGACY)", {}),
    _tool("system_info", "Get CPU/RAM/disk info (LEGACY)", {
        "type": {"type": "string", "enum": ["cpu", "ram", "disk", "battery", "all"]}
    }),
    _tool("system_health", "Full health report (LEGACY)", {}),
    _tool("get_top_processes", "Top processes by usage (LEGACY)", {
        "limit": {"type": "integer", "description": "How many (default 5)"}
    }),
    
    # Volume control
    _tool("set_volume", "Set volume 0-100 (LEGACY)", {"level": {"type": "integer"}}, ["level"]),
    _tool("volume_up", "Increase volume (LEGACY)", {"amount": {"type": "integer", "default": 10}}),
    _tool("volume_down", "Decrease volume (LEGACY)", {"amount": {"type": "integer", "default": 10}}),
    _tool("mute_volume", "Toggle mute (LEGACY)", {}),
    _tool("get_volume", "Get current volume (LEGACY)", {}),
    
    # Web & Network
    _tool("search_web", "Google search in browser (LEGACY)", {"query": {"type": "string"}}, ["query"]),
    _tool("get_wifi", "Get Wi-Fi info (LEGACY)", {}),
    _tool("get_ip", "Get IP address (LEGACY)", {}),
    _tool("ping", "Ping a host (LEGACY)", {"host": {"type": "string"}}, ["host"]),
    
    # Clipboard
    _tool("copy_to_clipboard", "Copy text to clipboard (LEGACY)", {"text": {"type": "string"}}, ["text"]),
    _tool("paste_from_clipboard", "Get clipboard contents (LEGACY)", {}),
    
    # Misc utilities
    _tool("calculate", "Evaluate math expression (LEGACY)", {"expression": {"type": "string"}}, ["expression"]),
    _tool("wait", "Pause for N seconds (LEGACY)", {"seconds": {"type": "integer"}}, ["seconds"]),
    _tool("lock_pc", "Lock PC (LEGACY)", {}),
    _tool("sleep_pc", "Sleep PC (LEGACY)", {}),
    _tool("restart_pc", "Restart PC (LEGACY - requires confirmation)", {}),
    _tool("shutdown_pc", "Shutdown PC (LEGACY - requires confirmation)", {}),
    _tool("set_brightness", "Set brightness 0-100 (LEGACY)", {"level": {"type": "integer"}}, ["level"]),
    _tool("toggle_dark_mode", "Toggle dark/light mode (LEGACY)", {}),
    _tool("empty_recycle_bin", "Empty recycle bin (LEGACY)", {}),
    _tool("add_note", "Save timestamped note (LEGACY)", {"text": {"type": "string"}}, ["text"]),
    _tool("read_notes", "Read notes from last N days (LEGACY)", {"days": {"type": "integer", "default": 1}}),
    _tool("minimize_windows", "Show desktop (LEGACY)", {}),
    _tool("get_uptime", "Get system uptime (LEGACY)", {}),
    
    # PowerShell/Command execution (USE WITH CAUTION - prefer dynamic scripts)
    _tool(
        "run_powershell_capture",
        "Run PowerShell and capture output (ADVANCED - prefer dynamic scripts)",
        {
            "script": {"type": "string", "description": "PowerShell command"},
            "timeout": {"type": "integer", "default": 30}
        },
        ["script"],
    ),
    _tool(
        "run_terminal_capture",
        "Run cmd command and capture output (ADVANCED - prefer dynamic scripts)",
        {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 30}
        },
        ["command"],
    ),
]


def get_tools() -> list:
    """Return the full tool list for Ollama."""
    return TOOLS


# Helper to identify primary vs legacy tools
PRIMARY_TOOLS = {"execute_dynamic_script"}
QUICK_TOOLS = {"get_time", "get_date", "screenshot"}
LEGACY_TOOLS = {t["function"]["name"] for t in TOOLS} - PRIMARY_TOOLS - QUICK_TOOLS


def is_primary_tool(name: str) -> bool:
    """Check if tool is the primary dynamic scripting method."""
    return name in PRIMARY_TOOLS


def is_quick_tool(name: str) -> bool:
    """Check if tool is a quick action for simple queries."""
    return name in QUICK_TOOLS


def is_legacy_tool(name: str) -> bool:
    """Check if tool is a legacy hardcoded tool."""
    return name in LEGACY_TOOLS
