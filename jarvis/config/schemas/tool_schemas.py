"""
Tool Schemas Configuration

Centralized schema definitions for all JARVIS tools.
Used for LLM function calling validation.
"""

from typing import Dict, List, Any


# Base schema template
TOOL_SCHEMA_TEMPLATE = {
    "type": "function",
    "function": {
        "name": "",
        "description": "",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


def create_schema(name: str, description: str, 
                 properties: Dict[str, Any],
                 required: List[str] = None) -> Dict:
    """
    Create a tool schema from components.
    
    Args:
        name: Tool name
        description: Tool description
        properties: Parameter properties dict
        required: List of required parameter names
        
    Returns:
        Complete tool schema dict
    """
    schema = TOOL_SCHEMA_TEMPLATE.copy()
    schema["function"]["name"] = name
    schema["function"]["description"] = description
    schema["function"]["parameters"]["properties"] = properties
    schema["function"]["parameters"]["required"] = required or []
    return schema


# System Tools Schemas

POWER_SCHEMAS = {
    "lock_computer": create_schema(
        name="lock_computer",
        description="Lock the computer immediately",
        properties={},
        required=[]
    ),
    "sleep_computer": create_schema(
        name="sleep_computer",
        description="Put the computer to sleep",
        properties={},
        required=[]
    ),
    "restart_computer": create_schema(
        name="restart_computer",
        description="Restart the computer",
        properties={
            "force": {
                "type": "boolean",
                "description": "Force restart without waiting for apps to close"
            }
        },
        required=[]
    ),
    "shutdown_computer": create_schema(
        name="shutdown_computer",
        description="Shut down the computer",
        properties={
            "force": {
                "type": "boolean",
                "description": "Force shutdown without waiting for apps to close"
            }
        },
        required=[]
    )
}

SYSTEM_INFO_SCHEMAS = {
    "get_battery_status": create_schema(
        name="get_battery_status",
        description="Get current battery status and charge level",
        properties={},
        required=[]
    ),
    "get_system_info": create_schema(
        name="get_system_info",
        description="Get detailed system information including CPU, RAM, OS",
        properties={},
        required=[]
    ),
    "get_processes": create_schema(
        name="get_processes",
        description="List running processes with optional filter",
        properties={
            "filter": {
                "type": "string",
                "description": "Filter processes by name substring"
            }
        },
        required=[]
    ),
    "get_uptime": create_schema(
        name="get_uptime",
        description="Get system uptime since last boot",
        properties={},
        required=[]
    )
}

DISPLAY_SCHEMAS = {
    "set_brightness": create_schema(
        name="set_brightness",
        description="Set screen brightness level",
        properties={
            "level": {
                "type": "integer",
                "description": "Brightness level 0-100",
                "minimum": 0,
                "maximum": 100
            }
        },
        required=["level"]
    ),
    "toggle_dark_mode": create_schema(
        name="toggle_dark_mode",
        description="Toggle Windows dark/light mode",
        properties={
            "enable": {
                "type": "boolean",
                "description": "True to enable dark mode, false for light mode"
            }
        },
        required=[]
    )
}

# App Tools Schemas

APP_SCHEMAS = {
    "open_app": create_schema(
        name="open_app",
        description="Open/launch an application",
        properties={
            "app_name": {
                "type": "string",
                "description": "Name of the application to open"
            }
        },
        required=["app_name"]
    ),
    "close_app": create_schema(
        name="close_app",
        description="Close an application by name",
        properties={
            "app_name": {
                "type": "string",
                "description": "Name of the application to close"
            },
            "force": {
                "type": "boolean",
                "description": "Force close if not responding"
            }
        },
        required=["app_name"]
    )
}

WINDOW_SCHEMAS = {
    "minimize_window": create_schema(
        name="minimize_window",
        description="Minimize the active window",
        properties={},
        required=[]
    ),
    "maximize_window": create_schema(
        name="maximize_window",
        description="Maximize the active window",
        properties={},
        required=[]
    ),
    "restore_window": create_schema(
        name="restore_window",
        description="Restore a minimized/maximized window",
        properties={},
        required=[]
    ),
    "focus_window": create_schema(
        name="focus_window",
        description="Bring a window to foreground by title",
        properties={
            "window_title": {
                "type": "string",
                "description": "Title or partial title of the window"
            }
        },
        required=["window_title"]
    ),
    "get_window_list": create_schema(
        name="get_window_list",
        description="List all open windows with titles and positions",
        properties={},
        required=[]
    )
}

# Audio Tools Schemas

AUDIO_SCHEMAS = {
    "set_volume": create_schema(
        name="set_volume",
        description="Set master volume level",
        properties={
            "level": {
                "type": "integer",
                "description": "Volume level 0-100",
                "minimum": 0,
                "maximum": 100
            }
        },
        required=["level"]
    ),
    "mute_volume": create_schema(
        name="mute_volume",
        description="Mute or unmute the audio",
        properties={
            "mute": {
                "type": "boolean",
                "description": "True to mute, false to unmute"
            }
        },
        required=[]
    )
}

# File Tools Schemas

FILE_SCHEMAS = {
    "read_file": create_schema(
        name="read_file",
        description="Read contents of a file",
        properties={
            "path": {
                "type": "string",
                "description": "Path to the file"
            }
        },
        required=["path"]
    ),
    "create_file": create_schema(
        name="create_file",
        description="Create a new file with content",
        properties={
            "path": {
                "type": "string",
                "description": "Path where to create the file"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            }
        },
        required=["path", "content"]
    ),
    "delete_file": create_schema(
        name="delete_file",
        description="Delete a file",
        properties={
            "path": {
                "type": "string",
                "description": "Path to the file to delete"
            }
        },
        required=["path"]
    ),
    "list_files": create_schema(
        name="list_files",
        description="List files in a directory",
        properties={
            "directory": {
                "type": "string",
                "description": "Directory path to list"
            },
            "pattern": {
                "type": "string",
                "description": "Optional file pattern filter (e.g., *.txt)"
            }
        },
        required=["directory"]
    )
}

# Web Tools Schemas

WEB_SCHEMAS = {
    "search_web": create_schema(
        name="search_web",
        description="Search the web using default search engine",
        properties={
            "query": {
                "type": "string",
                "description": "Search query"
            }
        },
        required=["query"]
    ),
    "open_url": create_schema(
        name="open_url",
        description="Open a URL in the default browser",
        properties={
            "url": {
                "type": "string",
                "description": "URL to open"
            }
        },
        required=["url"]
    )
}

# Time Tools Schemas

TIME_SCHEMAS = {
    "get_time": create_schema(
        name="get_time",
        description="Get current time",
        properties={},
        required=[]
    ),
    "get_date": create_schema(
        name="get_date",
        description="Get current date",
        properties={},
        required=[]
    ),
    "set_timer": create_schema(
        name="set_timer",
        description="Set a countdown timer",
        properties={
            "minutes": {
                "type": "integer",
                "description": "Timer duration in minutes"
            }
        },
        required=["minutes"]
    )
}

# Input Tools Schemas

INPUT_SCHEMAS = {
    "type_text": create_schema(
        name="type_text",
        description="Type text into the active window",
        properties={
            "text": {
                "type": "string",
                "description": "Text to type"
            }
        },
        required=["text"]
    ),
    "press_key": create_schema(
        name="press_key",
        description="Press a key or keyboard shortcut",
        properties={
            "key": {
                "type": "string",
                "description": "Key to press (e.g., 'enter', 'Win+D')"
            }
        },
        required=["key"]
    ),
    "click_at": create_schema(
        name="click_at",
        description="Click at specific screen coordinates",
        properties={
            "x": {
                "type": "integer",
                "description": "X coordinate"
            },
            "y": {
                "type": "integer",
                "description": "Y coordinate"
            },
            "button": {
                "type": "string",
                "description": "Mouse button: left, right, middle",
                "enum": ["left", "right", "middle"]
            }
        },
        required=["x", "y"]
    ),
    "copy_to_clipboard": create_schema(
        name="copy_to_clipboard",
        description="Copy text to clipboard",
        properties={
            "text": {
                "type": "string",
                "description": "Text to copy"
            }
        },
        required=["text"]
    ),
    "paste_from_clipboard": create_schema(
        name="paste_from_clipboard",
        description="Get current clipboard contents",
        properties={},
        required=[]
    )
}

# Screen Tools Schemas

SCREEN_SCHEMAS = {
    "take_screenshot": create_schema(
        name="take_screenshot",
        description="Take a screenshot of the entire screen",
        properties={},
        required=[]
    ),
    "analyze_screen": create_schema(
        name="analyze_screen",
        description="Analyze current screen content using vision AI",
        properties={
            "prompt": {
                "type": "string",
                "description": "Specific question about the screen"
            }
        },
        required=[]
    ),
    "find_on_screen": create_schema(
        name="find_on_screen",
        description="Find something on screen using vision AI",
        properties={
            "description": {
                "type": "string",
                "description": "Description of what to find"
            }
        },
        required=["description"]
    )
}

# Data Tools Schemas

DATA_SCHEMAS = {
    "add_todo": create_schema(
        name="add_todo",
        description="Add a todo item",
        properties={
            "task": {
                "type": "string",
                "description": "Task description"
            },
            "priority": {
                "type": "string",
                "description": "Priority level",
                "enum": ["low", "medium", "high"]
            }
        },
        required=["task"]
    ),
    "get_todos": create_schema(
        name="get_todos",
        description="Get list of todos",
        properties={},
        required=[]
    ),
    "add_note": create_schema(
        name="add_note",
        description="Add a note",
        properties={
            "content": {
                "type": "string",
                "description": "Note content"
            },
            "title": {
                "type": "string",
                "description": "Optional note title"
            }
        },
        required=["content"]
    ),
    "calculate": create_schema(
        name="calculate",
        description="Evaluate a mathematical expression",
        properties={
            "expression": {
                "type": "string",
                "description": "Math expression to evaluate"
            }
        },
        required=["expression"]
    )
}

# Memory Tools Schemas

MEMORY_SCHEMAS = {
    "remember": create_schema(
        name="remember",
        description="Store a fact in long-term memory",
        properties={
            "fact": {
                "type": "string",
                "description": "Fact to remember"
            },
            "category": {
                "type": "string",
                "description": "Optional category for the fact"
            }
        },
        required=["fact"]
    ),
    "recall": create_schema(
        name="recall",
        description="Recall memories related to a query",
        properties={
            "query": {
                "type": "string",
                "description": "Search query for relevant memories"
            }
        },
        required=["query"]
    )
}

# Script Tools Schemas

SCRIPT_SCHEMAS = {
    "run_command": create_schema(
        name="run_command",
        description="Run a PowerShell command",
        properties={
            "command": {
                "type": "string",
                "description": "PowerShell command to execute"
            }
        },
        required=["command"]
    ),
    "run_python": create_schema(
        name="run_python",
        description="Execute Python code",
        properties={
            "code": {
                "type": "string",
                "description": "Python code to execute"
            }
        },
        required=["code"]
    )
}

# Notification Schema

NOTIFICATION_SCHEMAS = {
    "send_notification": create_schema(
        name="send_notification",
        description="Show a Windows toast notification",
        properties={
            "title": {
                "type": "string",
                "description": "Notification title"
            },
            "message": {
                "type": "string",
                "description": "Notification message content"
            }
        },
        required=["title", "message"]
    )
}

# Network Schemas

NETWORK_SCHEMAS = {
    "get_wifi_info": create_schema(
        name="get_wifi_info",
        description="Get WiFi connection information",
        properties={},
        required=[]
    ),
    "get_public_ip": create_schema(
        name="get_public_ip",
        description="Get the public IP address",
        properties={},
        required=[]
    ),
    "ping_host": create_schema(
        name="ping_host",
        description="Ping a host to check connectivity",
        properties={
            "host": {
                "type": "string",
                "description": "Hostname or IP to ping"
            }
        },
        required=["host"]
    )
}


def get_all_schemas() -> List[Dict]:
    """
    Get all tool schemas combined.
    
    Returns:
        List of all tool schema dicts
    """
    all_schemas = []
    
    # Collect all schema groups
    schema_groups = [
        POWER_SCHEMAS,
        SYSTEM_INFO_SCHEMAS,
        DISPLAY_SCHEMAS,
        APP_SCHEMAS,
        WINDOW_SCHEMAS,
        AUDIO_SCHEMAS,
        FILE_SCHEMAS,
        WEB_SCHEMAS,
        TIME_SCHEMAS,
        INPUT_SCHEMAS,
        SCREEN_SCHEMAS,
        DATA_SCHEMAS,
        MEMORY_SCHEMAS,
        SCRIPT_SCHEMAS,
        NOTIFICATION_SCHEMAS,
        NETWORK_SCHEMAS
    ]
    
    for group in schema_groups:
        all_schemas.extend(group.values())
    
    return all_schemas


def get_schema_by_name(name: str) -> Dict:
    """
    Get a specific tool schema by name.
    
    Args:
        name: Tool name
        
    Returns:
        Tool schema dict or None if not found
    """
    all_schemas = get_all_schemas()
    for schema in all_schemas:
        if schema["function"]["name"] == name:
            return schema
    return None
