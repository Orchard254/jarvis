# control_plane.py
import re
from typing import Dict, Tuple, Any

from logger import get_logger

log = get_logger("control_plane")

# TODO: Populate with your actual pc_control tools
# Per-tool format:
# "tool_name": {
#     "required_params": ["param1"],
#     "param_types": {"param1": str},
#     "unsafe_patterns": [r"blocked_regex"]
# }
TOOL_REGISTRY = {
    # DYNAMIC SCRIPTING: Primary execution method
    "execute_dynamic_script": {
        "required_params": ["script", "description"],
        "param_types": {"script": str, "description": str, "timeout": int},
        "unsafe_patterns": [
            r"__import__", r"eval\(", r"exec\(", r"compile\(",
            r"socket\.", r"requests\.", r"urllib\.request",
            r"os\.system", r"subprocess\.Popen.*shell\s*=\s*True"
        ],
    },
    
    "run_powershell": {
        "required_params": ["script"],
        "param_types": {"script": str, "timeout": int},
        "unsafe_patterns": [r"rm -rf", r"del /[a-z] /", r"Format-Volume", r"Clear-Disk"],
    },
    "run_command": {
        "required_params": ["command"],
        "param_types": {"command": str},
        "unsafe_patterns": [r"rmdir /s", r"del /s", r"format ", r"shutdown /r /t 0"],
    },
    "get_time": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "get_date": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "battery_status": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "system_info": {"required_params": [], "param_types": {"type": str}, "unsafe_patterns": []},
    "system_health": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "get_top_processes": {
        "required_params": [],
        "param_types": {"limit": int},
        "unsafe_patterns": [],
    },
    "get_uptime": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "open_app": {
        "required_params": ["app_name"],
        "param_types": {"app_name": str},
        "unsafe_patterns": [],
    },
    "close_app": {
        "required_params": ["app_name"],
        "param_types": {"app_name": str},
        "unsafe_patterns": [],
    },
    "list_running_apps": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "set_volume": {
        "required_params": ["level"],
        "param_types": {"level": int},
        "unsafe_patterns": [],
    },
    "volume_up": {"required_params": [], "param_types": {"amount": int}, "unsafe_patterns": []},
    "volume_down": {"required_params": [], "param_types": {"amount": int}, "unsafe_patterns": []},
    "mute_volume": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "get_volume": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "screen_capture": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "read_file": {
        "required_params": ["path"],
        "param_types": {"path": str},
        "unsafe_patterns": [r"C:\\Windows", r"C:\\Program Files"],
    },
    "create_file": {
        "required_params": ["path", "content"],
        "param_types": {"path": str, "content": str},
        "unsafe_patterns": [r"C:\\Windows", r"C:\\Program Files"],
    },
    "open_file": {
        "required_params": ["path"],
        "param_types": {"path": str},
        "unsafe_patterns": [r"C:\\Windows", r"C:\\Program Files"],
    },
    "get_wifi": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "get_ip": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "ping": {"required_params": ["host"], "param_types": {"host": str}, "unsafe_patterns": []},
    "search_web": {
        "required_params": ["query"],
        "param_types": {"query": str},
        "unsafe_patterns": [],
    },
    "set_timer": {
        "required_params": [],
        "param_types": {"minutes": int, "seconds": int, "message": str},
        "unsafe_patterns": [],
    },
    "minimize_windows": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "add_note": {"required_params": ["text"], "param_types": {"text": str}, "unsafe_patterns": []},
    "read_notes": {"required_params": [], "param_types": {"days": int}, "unsafe_patterns": []},
    "copy_to_clipboard": {
        "required_params": ["text"],
        "param_types": {"text": str},
        "unsafe_patterns": [],
    },
    "paste_from_clipboard": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "calculate": {
        "required_params": ["expression"],
        "param_types": {"expression": str},
        "unsafe_patterns": [],
    },
    "wait": {
        "required_params": ["seconds"],
        "param_types": {"seconds": int},
        "unsafe_patterns": [],
    },
    "lock_pc": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "sleep_pc": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "restart_pc": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "shutdown_pc": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "set_brightness": {
        "required_params": ["level"],
        "param_types": {"level": int},
        "unsafe_patterns": [],
    },
    "toggle_dark_mode": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "empty_recycle_bin": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
    "open_settings": {
        "required_params": [],
        "param_types": {"section": str},
        "unsafe_patterns": [],
    },
    "open_control_panel": {
        "required_params": [],
        "param_types": {"item": str},
        "unsafe_patterns": [],
    },
    "run_in_terminal": {
        "required_params": ["command"],
        "param_types": {"command": str},
        "unsafe_patterns": [r"rm -rf", r"del /[a-z] /"],
    },
    "run_terminal_capture": {
        "required_params": ["command"],
        "param_types": {"command": str, "timeout": int},
        "unsafe_patterns": [r"rm -rf", r"del /[a-z] /"],
    },
    "run_powershell_bg": {
        "required_params": ["script"],
        "param_types": {"script": str},
        "unsafe_patterns": [r"rm -rf", r"del /[a-z] /", r"Format-Volume"],
    },
    "run_powershell_capture": {
        "required_params": ["script"],
        "param_types": {"script": str, "timeout": int},
        "unsafe_patterns": [r"rm -rf", r"del /[a-z] /", r"Format-Volume"],
    },
    "run_script": {
        "required_params": ["path"],
        "param_types": {"path": str, "wait": bool, "timeout": int},
        "unsafe_patterns": [r"C:\\Windows", r"C:\\Program Files"],
    },
    "chain_commands": {
        "required_params": ["commands"],
        "param_types": {"commands": list, "stop_on_failure": bool},
        "unsafe_patterns": [r"rm -rf", r"del /[a-z] /"],
    },
    "task_start": {
        "required_params": ["command"],
        "param_types": {"command": str, "name": str, "shell": str},
        "unsafe_patterns": [r"rm -rf", r"del /[a-z] /", r"Format-Volume"],
    },
    "task_output": {
        "required_params": ["task_id"],
        "param_types": {"task_id": str, "lines": int},
        "unsafe_patterns": [],
    },
    "task_kill": {
        "required_params": ["task_id"],
        "param_types": {"task_id": str},
        "unsafe_patterns": [],
    },
    "task_wait": {
        "required_params": ["task_id"],
        "param_types": {"task_id": str, "timeout": int},
        "unsafe_patterns": [],
    },
    "task_check": {
        "required_params": ["task_id"],
        "param_types": {"task_id": str},
        "unsafe_patterns": [],
    },
    "task_clear": {
        "required_params": [],
        "param_types": {"older_than_hours": int},
        "unsafe_patterns": [],
    },
    "create_todo": {
        "required_params": ["task"],
        "param_types": {"task": str, "subtasks": list},
        "unsafe_patterns": [],
    },
    "mark_done": {
        "required_params": ["subtask"],
        "param_types": {"subtask": str},
        "unsafe_patterns": [],
    },
    "complete_todo": {
        "required_params": [],
        "param_types": {"summary": str},
        "unsafe_patterns": [],
    },
    "list_todos": {"required_params": [], "param_types": {}, "unsafe_patterns": []},
}
# FIX 6 & 14: Add Windows-specific destructive patterns AND critical processes
GLOBAL_BLOCKED = [
    r"sudo ",
    r"curl .* \| sh",
    r"rm -rf /",
    # Windows-specific dangerous patterns
    r"Remove-Item\s+-Recurse\s*-Force",
    r"Clear-Disk\s+-RemoveData",
    r"Format-Volume\s+-FileSystem",
    r"shutdown\s+/s\s+/t\s+0",
    r"shutdown\s+/r\s+/t\s+0",
    r"taskkill\s+/F\s+/IM\s+explorer\.exe",
    r"reg\s+delete\s+.*\/f",
    r"del\s+/F\s+/Q\s+.*\\.*\.\*",
    # FIX 6: Critical Windows processes that should never be killed
    r"Stop-Process\s+-Name\s+['\"]?System Idle Process['\"]?",
    r"Stop-Process\s+-Name\s+['\"]?csrss['\"]?",
    r"Stop-Process\s+-Name\s+['\"]?wininit['\"]?",
    r"Stop-Process\s+-Name\s+['\"]?services['\"]?",
    r"Stop-Process\s+-Name\s+['\"]?lsass['\"]?",
    r"taskkill\s+/F\s+/IM\s+csrss\.exe",
    r"taskkill\s+/F\s+/IM\s+wininit\.exe",
    r"taskkill\s+/F\s+/IM\s+services\.exe",
    r"taskkill\s+/F\s+/IM\s+lsass\.exe",
]


def _tool_exists(tool: str) -> bool:
    return tool in TOOL_REGISTRY


def _validate_params(tool: str, params: Dict) -> Tuple[bool, str]:
    try:
        spec = TOOL_REGISTRY.get(tool)
        if not spec:
            return False, f"Tool {tool} not found in registry"

        required_params = spec.get("required_params", [])
        missing = [p for p in required_params if p not in params]
        if missing:
            return False, f"Missing required params: {missing}"

        param_types = spec.get("param_types", {})
        for p, t in param_types.items():
            if p not in params:
                continue
            v = params[p]
            # Special handling for bool - bool is subclass of int in Python
            if t is bool:
                if isinstance(v, bool):
                    continue
                # Try to coerce string to bool
                if isinstance(v, str):
                    if v.lower() in ("true", "false", "1", "0", "yes", "no"):
                        params[p] = v.lower() in ("true", "1", "yes")
                        continue
                return False, f"Param '{p}' must be bool, got {type(v).__name__}"
            # For int, don't accept bool (even though bool is subclass of int)
            if t is int and isinstance(v, bool):
                return False, f"Param '{p}' must be int, got bool"
            if not isinstance(v, t):
                # Try type coercion
                try:
                    if t is int and isinstance(v, str):
                        params[p] = int(v)
                    elif t is str and not isinstance(v, str):
                        params[p] = str(v)
                    else:
                        return False, f"Param '{p}' must be {t.__name__}, got {type(v).__name__}"
                except (ValueError, TypeError):
                    return False, f"Param '{p}' must be {t.__name__}, got {type(v).__name__}: {v}"

        # Improve: Add common-sense validation for specific params
        if tool == "set_volume" and "level" in params:
            level = params["level"]
            if not isinstance(level, int) or level < 0 or level > 100:
                return False, f"Volume level must be integer between 0-100, got: {level}"

        if tool == "wait" and "seconds" in params:
            seconds = params["seconds"]
            if not isinstance(seconds, int) or seconds < 1 or seconds > 3600:
                return False, f"Wait seconds must be integer between 1-3600, got: {seconds}"

        if tool == "get_top_processes" and "limit" in params:
            limit = params["limit"]
            if not isinstance(limit, int) or limit < 1 or limit > 50:
                return False, f"Process limit must be integer between 1-50, got: {limit}"

        if tool == "open_app" and "app_name" in params:
            app = params["app_name"]
            if not app or not isinstance(app, str):
                return False, f"App name must be non-empty string, got: {app}"

        if tool in ("run_powershell", "run_command") and (
            "script" in params or "command" in params
        ):
            cmd = params.get("script") or params.get("command", "")
            if not cmd or not isinstance(cmd, str):
                return False, f"Command/script must be non-empty string"
            if len(cmd) > 2000:
                return False, f"Command too long: {len(cmd)} chars (max 2000)"

        return True, ""
    except Exception as e:
        return False, f"Validation error: {e}"


def _check_safety(tool: str, params: Dict) -> Tuple[bool, str]:
    patterns = TOOL_REGISTRY[tool].get("unsafe_patterns", []) + GLOBAL_BLOCKED

    def _check_value(v: Any, path: str = "") -> Tuple[bool, str]:
        """Recursively check a value for unsafe patterns."""
        if isinstance(v, str):
            for p in patterns:
                if re.search(p, v, re.I):
                    suggestion = _get_safe_alternative(p)
                    return False, f"Unsafe pattern detected in '{path}': '{p}'. {suggestion}"
        elif isinstance(v, dict):
            for k, val in v.items():
                ok, msg = _check_value(val, f"{path}.{k}" if path else k)
                if not ok:
                    return ok, msg
        elif isinstance(v, (list, tuple)):
            for i, val in enumerate(v):
                ok, msg = _check_value(val, f"{path}[{i}]")
                if not ok:
                    return ok, msg
        return True, ""

    for key, value in params.items():
        ok, msg = _check_value(value, key)
        if not ok:
            return False, msg
    return True, ""


def _get_safe_alternative(pattern: str) -> str:
    """Provide safer alternatives for blocked patterns."""
    alternatives = {
        r"rm -rf": "Use file manager or specific delete commands with confirmation.",
        r"del /": "Use specific file deletion with user confirmation.",
        r"Format-Volume": "Use Disk Management GUI for volume formatting.",
        r"Clear-Disk": "Use Disk Management GUI for disk operations.",
        r"shutdown /r /t 0": "Use restart_pc tool instead.",
        r"rmdir /s": "Use specific folder deletion with confirmation.",
        r"curl .* \| sh": "Download files first, then review before executing.",
        r"sudo ": "Administrator privileges should be requested via UAC, not sudo.",
    }
    return alternatives.get(pattern, "Operation blocked for system safety.")


def validate_tool_call(tool_name: str, params: Dict) -> Tuple[bool, str]:
    """
    Validate a tool call (safety + params).
    Returns (is_valid, error_message).
    control_plane.py ONLY validates - does NOT execute.
    """
    if not _tool_exists(tool_name):
        return False, f"Unknown tool: {tool_name}"
    valid, msg = _validate_params(tool_name, params)
    if not valid:
        return False, msg
    safe, msg = _check_safety(tool_name, params)
    if not safe:
        return False, msg

    # FIX 8: Require confirmation for system-modifying operations
    # This should be checked at execution time, but we flag it here
    SYSTEM_MODIFYING_TOOLS = {
        "optimize_system",
        "disable_service",
        "modify_registry",
        "shutdown_pc",
        "restart_pc",
        "run_powershell",
        "run_command",
        "execute_dynamic_script",  # DYNAMIC SCRIPTING: Requires confirmation
    }
    if tool_name in SYSTEM_MODIFYING_TOOLS:
        log.warning(f"[CONTROL_PLANE] System-modifying tool requested: {tool_name}")
        # In production, this should trigger user confirmation prompt

    return True, ""
