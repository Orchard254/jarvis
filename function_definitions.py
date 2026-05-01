# function_definitions.py — Core tools for autonomous agent (Google Assistant-like for Windows)

FUNCTION_DEFINITIONS = {
    # === CORE PC AUTOMATION ===
    "run_powershell": {
        "name": "run_powershell",
        "description": "Execute PowerShell commands. PRIMARY tool for Windows PC automation - control settings, manage files, system operations, etc.",
        "parameters": {"script": "string (required) - PowerShell script or command(s)"},
    },
    "run_command": {
        "name": "run_command",
        "description": "Execute a Windows command (cmd.exe). For simple commands like dir, type, ipconfig.",
        "parameters": {"command": "string (required) - Command to execute"},
    },
    # === FILE MANAGEMENT ===
    "search_web": {
        "name": "search_web",
        "description": "Open a web search in the default browser",
        "parameters": {"query": "string (required) - Search query"},
    },
    "read_file": {
        "name": "read_file",
        "description": "Read contents of a text file. Use 'speak' parameter to read aloud.",
        "parameters": {
            "path": "string (required) - Full file path",
            "speak": "boolean (optional) - If true, read content aloud using TTS",
        },
    },
    "create_file": {
        "name": "create_file",
        "description": "Create a new file with content",
        "parameters": {
            "path": "string (required) - Full file path",
            "content": "string (optional) - File content",
        },
    },
    "open_file": {
        "name": "open_file",
        "description": "Open a file with default application",
        "parameters": {"path": "string (required) - File path"},
    },
    # === BASIC INFO (Natural responses) ===
    "get_time": {
        "name": "get_time",
        "description": "Get current time - respond naturally",
        "parameters": {},
    },
    "get_date": {
        "name": "get_date",
        "description": "Get current date - respond naturally",
        "parameters": {},
    },
    # === SCREEN & CAPTURE ===
    "screenshot": {
        "name": "screenshot",
        "description": "Take a screenshot and save to Pictures/Screenshots",
        "parameters": {"path": "string (optional) - Custom save path"},
    },
    "screen_capture": {
        "name": "screen_capture",
        "description": "Capture the current screen and describe what's visible. Use to verify UI state, check errors.",
        "parameters": {},
    },
    "start_realtime_screen": {
        "name": "start_realtime_screen",
        "description": "Start real-time screen capture at intervals (saves latest screenshot for reference).",
        "parameters": {"interval": "integer (optional) - Seconds between captures, default 5"},
    },
    "stop_realtime_screen": {
        "name": "stop_realtime_screen",
        "description": "Stop real-time screen capture.",
        "parameters": {},
    },
    "get_latest_screen": {
        "name": "get_latest_screen",
        "description": "Get the most recent screenshot from real-time capture (path).",
        "parameters": {},
    },
    # === UTILITIES ===
    "calculate": {
        "name": "calculate",
        "description": "Evaluate a mathematical expression",
        "parameters": {
            "expression": "string (required) - Math expression like '2+2' or 'sqrt(16)'"
        },
    },
    "wait": {
        "name": "wait",
        "description": "Wait for specified seconds (useful in multi-step tasks)",
        "parameters": {"seconds": "integer (required) - Seconds to wait"},
    },
    # === TIMERS & REMINDERS ===
    "set_timer": {
        "name": "set_timer",
        "description": "Set a timer that will remind you after X minutes",
        "parameters": {"minutes": "integer (required) - Minutes until reminder"},
    },
    "set_alarm": {
        "name": "set_alarm",
        "description": "Set an alarm at specific time",
        "parameters": {"time": "string (required) - Time like '7:00 AM'"},
    },
    # === SHORTCUTS & MACROS ===
    "execute_shortcut": {
        "name": "execute_shortcut",
        "description": "Execute a saved shortcut/macro (work_mode, break_time, focus_mode, relax)",
        "parameters": {"name": "string (required) - Shortcut name"},
    },
    "create_shortcut": {
        "name": "create_shortcut",
        "description": "Create a new shortcut/macro that combines multiple actions",
        "parameters": {
            "name": "string (required) - Shortcut name",
            "actions": "array (required) - List of actions like ['open_app:Chrome', 'set_timer:25']",
        },
    },
    "list_shortcuts": {
        "name": "list_shortcuts",
        "description": "List all available shortcuts",
        "parameters": {},
    },
    # === USER PROFILE ===
    "get_profile": {
        "name": "get_profile",
        "description": "Get user profile summary - name, preferences, etc.",
        "parameters": {},
    },
    "set_preference": {
        "name": "set_preference",
        "description": "Set a user preference (name, response_length, favorite_apps, etc.)",
        "parameters": {
            "key": "string (required) - Preference key",
            "value": "any (required) - Preference value",
        },
    },
    # === SYSTEM STATUS (like Google Assistant) ===
    "battery_status": {
        "name": "battery_status",
        "description": "Get current battery level and charging status",
        "parameters": {},
    },
    "system_info": {
        "name": "system_info",
        "description": "Get system information (CPU, RAM, disk, battery)",
        "parameters": {
            "type": "string (optional) - Type: 'cpu', 'ram', 'disk', 'battery', or 'all'"
        },
    },
    "system_health": {
        "name": "system_health",
        "description": "Check overall system health (CPU, memory, disk, battery, processes). Returns status and warnings.",
        "parameters": {},
    },
    "get_top_processes": {
        "name": "get_top_processes",
        "description": "Get top processes by CPU and memory usage",
        "parameters": {"limit": "integer (optional, default 5) - Number of processes to return"},
    },
    "get_uptime": {
        "name": "get_uptime",
        "description": "Get system uptime in human-readable format",
        "parameters": {},
    },
    # === NETWORK & CONNECTIVITY ===
    "get_wifi": {
        "name": "get_wifi",
        "description": "Get current Wi-Fi network name",
        "parameters": {},
    },
    "get_ip": {
        "name": "get_ip",
        "description": "Get current IP address",
        "parameters": {},
    },
    "ping": {
        "name": "ping",
        "description": "Ping a website or IP address to check connectivity",
        "parameters": {"host": "string (required) - Website or IP to ping"},
    },
    "internet_speed": {
        "name": "internet_speed",
        "description": "Test internet connection speed",
        "parameters": {},
    },
    # === VOLUME & MEDIA ===
    "volume_up": {
        "name": "volume_up",
        "description": "Increase system volume",
        "parameters": {"amount": "integer (optional) - Percentage to increase (default 5)"},
    },
    "volume_down": {
        "name": "volume_down",
        "description": "Decrease system volume",
        "parameters": {"amount": "integer (optional) - Percentage to decrease (default 5)"},
    },
    "mute_volume": {
        "name": "mute_volume",
        "description": "Mute or unmute system volume",
        "parameters": {},
    },
    "get_volume": {
        "name": "get_volume",
        "description": "Get current volume level",
        "parameters": {},
    },
    "set_volume": {
        "name": "set_volume",
        "description": "Set system volume to a specific level (0-100)",
        "parameters": {"level": "integer (required) - Volume level 0-100"},
    },
    # === APPLICATION MANAGEMENT ===
    "open_app": {
        "name": "open_app",
        "description": "Open an application by name (chrome, notepad, calculator, spotify, etc.)",
        "parameters": {"app_name": "string (required) - Name of app to open"},
    },
    "close_app": {
        "name": "close_app",
        "description": "Close an application by name",
        "parameters": {"app_name": "string (required) - Name of app to close"},
    },
    "list_running_apps": {
        "name": "list_running_apps",
        "description": "List currently running applications",
        "parameters": {},
    },
    # === NOTES & TODO ===
    "add_note": {
        "name": "add_note",
        "description": "Add a voice note with timestamp",
        "parameters": {"text": "string (required) - Note content"},
    },
    "read_notes": {
        "name": "read_notes",
        "description": "Read saved notes from the last X days",
        "parameters": {"days": "integer (default 1) - Days back to read"},
    },
    "create_todo": {
        "name": "create_todo",
        "description": "Create a new todo task with subtasks for tracking multi-step tasks",
        "parameters": {
            "task": "string (required) - Main task description",
            "subtasks": "array (optional) - List of subtask descriptions",
        },
    },
    "mark_done": {
        "name": "mark_done",
        "description": "Mark a subtask as completed in the current todo",
        "parameters": {"subtask": "string (required) - Subtask text to mark as done"},
    },
    "complete_todo": {
        "name": "complete_todo",
        "description": "Mark the current todo as completed with a summary",
        "parameters": {"summary": "string (required) - Summary of what was accomplished"},
    },
    "list_todos": {
        "name": "list_todos",
        "description": "List all active todos",
        "parameters": {},
    },
    # === INFORMATION (External) ===
    "weather": {
        "name": "weather",
        "description": "Get current weather for a location",
        "parameters": {"location": "string (optional) - City name"},
    },
    "wikipedia": {
        "name": "wikipedia",
        "description": "Search Wikipedia for information",
        "parameters": {"query": "string (required) - Search topic"},
    },
    "stock_price": {
        "name": "stock_price",
        "description": "Get current stock price",
        "parameters": {"symbol": "string (required) - Stock symbol like AAPL"},
    },
    "news": {
        "name": "news",
        "description": "Get latest news headlines",
        "parameters": {"topic": "string (optional) - Topic for news"},
    },
    "define": {
        "name": "define",
        "description": "Define a word",
        "parameters": {"word": "string (required) - Word to define"},
    },
    "translate": {
        "name": "translate",
        "description": "Translate text to another language",
        "parameters": {
            "text": "string (required) - Text to translate",
            "target": "string (optional) - Target language code like 'es', 'fr'",
        },
    },
    # === CLIPBOARD ===
    "copy_to_clipboard": {
        "name": "copy_to_clipboard",
        "description": "Copy text to clipboard",
        "parameters": {"text": "string (required) - Text to copy"},
    },
    "paste_from_clipboard": {
        "name": "paste_from_clipboard",
        "description": "Get text from clipboard",
        "parameters": {},
    },
    # === WINDOWS SETTINGS ===
    "open_settings": {
        "name": "open_settings",
        "description": "Open Windows Settings app",
        "parameters": {
            "section": "string (optional) - Settings section like 'display', 'sound', 'network'"
        },
    },
    "open_control_panel": {
        "name": "open_control_panel",
        "description": "Open Windows Control Panel",
        "parameters": {"item": "string (optional) - Control panel item"},
    },
    "set_brightness": {
        "name": "set_brightness",
        "description": "Set display brightness (0-100)",
        "parameters": {"level": "integer (required) - Brightness level 0-100"},
    },
    "toggle_dark_mode": {
        "name": "toggle_dark_mode",
        "description": "Toggle Windows Dark Mode",
        "parameters": {},
    },
    # === WINDOW MANAGEMENT ===
    "minimize_windows": {
        "name": "minimize_windows",
        "description": "Minimize all open windows (show desktop). Use when user asks to minimise all windows or show desktop.",
        "parameters": {},
    },
    "maximize_window": {
        "name": "maximize_window",
        "description": "Maximize the current active window",
        "parameters": {},
    },
    "restore_window": {
        "name": "restore_window",
        "description": "Restore the current active window",
        "parameters": {},
    },
    "close_window": {
        "name": "close_window",
        "description": "Close the current active window",
        "parameters": {},
    },
    # === QUICK ACTIONS ===
    "lock_pc": {
        "name": "lock_pc",
        "description": "Lock the PC",
        "parameters": {},
    },
    "sleep_pc": {
        "name": "sleep_pc",
        "description": "Put PC to sleep",
        "parameters": {},
    },
    "restart_pc": {
        "name": "restart_pc",
        "description": "Restart the PC",
        "parameters": {},
    },
    "shutdown_pc": {
        "name": "shutdown_pc",
        "description": "Shutdown the PC",
        "parameters": {},
    },
    "empty_recycle_bin": {
        "name": "empty_recycle_bin",
        "description": "Empty the Recycle Bin",
        "parameters": {},
    },
    "task_start": {
        "name": "task_start",
        "description": "Start a background task - returns immediately with task_id. Use for long-running tasks",
        "parameters": {
            "command": "string (required) - Command to run in background",
            "name": "string (optional) - Friendly name for the task",
            "shell": "string (optional) - 'cmd' or 'powershell', default 'cmd'",
        },
    },
    "task_status": {
        "name": "task_status",
        "description": "Get status of a running or completed task. Omit task_id to get all tasks",
        "parameters": {
            "task_id": "string (optional) - Task ID from task_start. If omitted, returns all tasks",
        },
    },
    "task_output": {
        "name": "task_output",
        "description": "Get full output from a background task (running or completed)",
        "parameters": {
            "task_id": "string (required) - Task ID from task_start",
            "lines": "integer (optional) - Get last N lines only",
        },
    },
    "task_check": {
        "name": "task_check",
        "description": "Quick check if a task has produced output (lighter than task_output)",
        "parameters": {
            "task_id": "string (required) - Task ID from task_start",
        },
    },
    "task_kill": {
        "name": "task_kill",
        "description": "Kill a running background task",
        "parameters": {
            "task_id": "string (required) - Task ID from task_start",
        },
    },
    "task_wait": {
        "name": "task_wait",
        "description": "Wait for a background task to complete and get final output",
        "parameters": {
            "task_id": "string (required) - Task ID from task_start",
            "timeout": "integer (optional) - Max wait time in seconds, default 60",
        },
    },
    "task_clear": {
        "name": "task_clear",
        "description": "Clear old completed tasks from memory",
        "parameters": {
            "older_than_hours": "integer (optional) - Clear tasks older than N hours, default 24",
        },
    },
}


def get_function_docs() -> str:
    """Generate documentation for all available functions."""
    docs = "# Core Tools\n\nUse these tools to accomplish tasks. When you need something not listed, use run_powershell to generate a script.\n\n"
    for func_name, func_info in FUNCTION_DEFINITIONS.items():
        docs += f"## {func_info['name']}\n"
        docs += f"{func_info['description']}\n"
        if func_info["parameters"]:
            docs += "Parameters:\n"
            for param_name, param_desc in func_info["parameters"].items():
                docs += f"  - {param_name}: {param_desc}\n"
        else:
            docs += "Parameters: None\n"
        docs += "\n"
    docs += "\n# Special Commands (not functions - respond with these directly)\n\n"
    docs += "## CREATE_TODO\n"
    docs += 'Create a todo with subtasks: CREATE_TODO:{"task": "...", "subtasks": ["step1", "step2"]}\n\n'
    docs += "## MARK_DONE\n"
    docs += 'Mark subtask done: MARK_DONE:{"subtask": "step1"}\n\n'
    docs += "## COMPLETE_TODO\n"
    docs += 'Complete todo: COMPLETE_TODO:{"summary": "Task completed successfully"}\n\n'
    return docs
