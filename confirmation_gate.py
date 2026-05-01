# confirmation_gate.py — Action-level confirmation and risk classification

from typing import Dict, Any
from logger import get_logger

log = get_logger("confirmation_gate")

# Risk levels: CRITICAL > HIGH > MEDIUM > LOW
ACTION_RISK_LEVELS = {
    # CRITICAL — Requires explicit user confirmation before execution
    "close_app": "CRITICAL",
    "close_window": "CRITICAL",
    "run_powershell": "CRITICAL",
    "run_powershell_bg": "CRITICAL",
    "run_powershell_capture": "CRITICAL",
    "run_in_terminal": "CRITICAL",
    "run_terminal_capture": "CRITICAL",
    "run_script": "CRITICAL",
    "run_script_file": "CRITICAL",
    "empty_recycle_bin": "CRITICAL",
    "open_settings": "CRITICAL",
    "open_control_panel": "CRITICAL",
    "dark_mode": "CRITICAL",  # System-wide setting change
    "shutdown_pc": "CRITICAL",
    "restart_pc": "CRITICAL",
    "lock_pc": "CRITICAL",
    "sleep_pc": "CRITICAL",
    # HIGH — Risky file operations
    "create_file": "HIGH",  # Could overwrite existing files
    "delete_file": "HIGH",  # Destructive
    "open_file": "MEDIUM",  # Opening executables is risky
    # MEDIUM — Should be logged
    "set_volume": "MEDIUM",
    "mute_volume": "MEDIUM",
    "search_web": "MEDIUM",
    "screenshot": "MEDIUM",
    "screen_capture": "MEDIUM",
    # LOW — Generally safe operations
    "open_app": "LOW",
    "read_file": "LOW",
    "get_time": "LOW",
    "get_date": "LOW",
    "calculate": "LOW",
    "battery_status": "LOW",
    "system_info": "LOW",
    "system_health": "LOW",
    "get_top_processes": "LOW",
    "get_volume": "LOW",
}

HUMAN_DESCRIPTIONS = {
    "close_app": "Close the application",
    "run_powershell": "Execute a PowerShell script",
    "run_in_terminal": "Run a command in terminal",
    "empty_recycle_bin": "Empty the recycle bin (permanent deletion)",
    "open_settings": "Open Windows Settings (system configuration)",
    "dark_mode": "Change system dark mode setting",
    "shutdown_pc": "Shut down the computer",
    "restart_pc": "Restart the computer",
    "lock_pc": "Lock the computer",
    "create_file": "Create/overwrite a file",
    "delete_file": "Delete a file",
    "set_volume": "Change system volume",
}


def get_action_risk_level(action: str) -> str:
    """Return the risk level for an action: CRITICAL, HIGH, MEDIUM, LOW."""
    return ACTION_RISK_LEVELS.get(action, "MEDIUM")


def get_human_description(action: str, params: dict) -> str:
    """Generate a human-readable description of the action."""
    base = HUMAN_DESCRIPTIONS.get(action, f"Execute action: {action}")

    # Add parameter details for clarity
    if action == "close_app" and "app_name" in params:
        return f"Close {params['app_name']}"
    elif action == "run_powershell" and "script" in params:
        script = params["script"][:50]
        return f"Execute PowerShell: {script}..."
    elif action == "create_file" and "path" in params:
        return f"Create file: {params['path']}"
    elif action == "open_settings":
        return "Open Windows Settings"
    elif action == "empty_recycle_bin":
        return "Permanently delete all items in recycle bin"
    elif action == "set_volume" and "level" in params:
        return f"Set volume to {params['level']}%"

    return base


def needs_confirmation(action: str) -> bool:
    """Check if an action requires user confirmation."""
    risk = get_action_risk_level(action)
    return risk in ["CRITICAL", "HIGH"]


def classify_action_batch(tool_calls: list) -> Dict[str, Any]:
    """
    Classify a batch of tool calls by risk level.
    Returns dict with:
        - critical: list of CRITICAL actions
        - high: list of HIGH actions
        - medium: list of MEDIUM actions
        - requires_confirmation: bool (True if any CRITICAL/HIGH)
        - summary: human-readable summary
    """
    critical = []
    high = []
    medium = []

    for tc in tool_calls:
        name = tc.get("name") or tc.get("function", {}).get("name", "")
        params = tc.get("params") or tc.get("function", {}).get("arguments", {})
        risk = get_action_risk_level(name)

        item = {"name": name, "params": params}

        if risk == "CRITICAL":
            critical.append(item)
        elif risk == "HIGH":
            high.append(item)
        elif risk == "MEDIUM":
            medium.append(item)

    requires_conf = len(critical) > 0 or len(high) > 0

    # Generate summary
    summary_parts = []
    if critical:
        summary_parts.append(
            f"{len(critical)} critical action(s): "
            + ", ".join(get_human_description(c["name"], c["params"]) for c in critical)
        )
    if high:
        summary_parts.append(
            f"{len(high)} high-risk action(s): "
            + ", ".join(get_human_description(h["name"], h["params"]) for h in high)
        )
    if medium:
        summary_parts.append(f"{len(medium)} medium-risk action(s)")

    summary = " | ".join(summary_parts) if summary_parts else "Safe operations"

    return {
        "critical": critical,
        "high": high,
        "medium": medium,
        "requires_confirmation": requires_conf,
        "summary": summary,
    }


def build_confirmation_prompt(tool_calls: list) -> str:
    """Build a user-friendly confirmation prompt."""
    classification = classify_action_batch(tool_calls)

    if not classification["requires_confirmation"]:
        return None

    prompt_lines = [
        "⚠️  CONFIRMATION REQUIRED",
        "",
        "The LLM is about to execute potentially dangerous actions:",
        "",
    ]

    for i, action in enumerate(classification["critical"], 1):
        desc = get_human_description(action["name"], action["params"])
        prompt_lines.append(f"  {i}. [CRITICAL] {desc}")

    for i, action in enumerate(classification["high"], 1):
        desc = get_human_description(action["name"], action["params"])
        prompt_lines.append(f"  {i}. [HIGH] {desc}")

    prompt_lines.extend(
        [
            "",
            "Do you approve? (yes/no)",
        ]
    )

    return "\n".join(prompt_lines)
