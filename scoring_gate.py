# scoring_gate.py — Tool execution scoring and gate decision logic

from typing import Any, Dict, List, Tuple

# Severity thresholds for safety gates
SEVERITY_BLOCK_THRESHOLD = 5
SEVERITY_DEGRADE_THRESHOLD = 2
MAX_SEVERITY = 10


def _has_duplicate_tools(tool_calls: List[dict]) -> int:
    """Check for duplicate tool calls. Returns severity if found."""
    names = [tc.get("name", "") for tc in tool_calls]
    if len(names) != len(set(names)):
        return 5  # Elevate to BLOCK threshold
    return 0


def _has_conflicting_tools(tool_calls: List[dict]) -> int:
    """Check for conflicting tool pairs. Returns severity if found."""

    def _get_args(tc):
        return tc.get("args", {}) or tc.get("function", {}).get("arguments", {})

    open_apps = {_get_args(tc).get("app_name") for tc in tool_calls if tc.get("name") == "open_app"}
    close_apps = {
        _get_args(tc).get("app_name") for tc in tool_calls if tc.get("name") == "close_app"
    }
    if open_apps & close_apps:
        return 5

    if any(tc.get("name") == "lock_pc" for tc in tool_calls):
        if any(tc.get("name") == "shutdown_pc" for tc in tool_calls):
            return 5

    return 0


def _count_tool_calls(tool_calls: List[dict]) -> int:
    """Count number of tool calls. Returns severity if excessive."""
    count = len(tool_calls)
    if count <= 2:
        return 0
    if count == 3:
        return 1
    return 2


def score_agent_round(tool_calls: List[dict], logs: List[str] = None) -> Dict[str, Any]:
    """
    Score a round of tool calls for execution safety.
    Returns dict with:
        - severity: int (0-10, higher = more problematic)
        - issues: list of issue descriptions
    """
    issues = []
    severity = 0

    if not tool_calls:
        return {"severity": 0, "issues": []}

    dup_severity = _has_duplicate_tools(tool_calls)
    if dup_severity:
        severity += dup_severity
        issues.append("duplicate_tool_calls")

    conflict_severity = _has_conflicting_tools(tool_calls)
    if conflict_severity:
        severity += conflict_severity
        issues.append("conflicting_tools")

    count_severity = _count_tool_calls(tool_calls)
    if count_severity:
        severity += count_severity
        issues.append(f"excessive_tool_calls:{len(tool_calls)}")

    return {"severity": min(severity, 10), "issues": issues}


def apply_execution_gate(tool_calls: List[dict], score: Dict[str, Any]) -> Tuple[str, List[dict]]:
    """
    Apply gate decision based on severity score.
    Returns (decision, filtered_tool_calls):
        - PASS: execute all tools (severity 0-1)
        - DEGRADE: execute only safe tools (severity 2-4)
        - BLOCK: execute no tools (severity 5+)
    """
    severity = score.get("severity", 0)

    if severity >= 5:
        return "BLOCK", []
    elif severity >= 2:
        safe_tools = [
            "get_time",
            "get_date",
            "battery_status",
            "system_info",
            "system_health",
            "get_uptime",
            "get_volume",
            "get_wifi",
            "get_ip",
            "list_running_apps",
        ]
        filtered = [tc for tc in tool_calls if tc.get("name") in safe_tools]
        return "DEGRADE", filtered
    else:
        return "PASS", tool_calls
