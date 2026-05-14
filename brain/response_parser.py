
"""
Validates LLM tool calls. Falls back to notify_user on malformed output.
Supports both native tool_calls and BATCH_TOOL_PLAN text format.
"""
import json
import logging
import re
import uuid

logger = logging.getLogger(__name__)


def validate_tool_calls(tool_calls: list[dict], valid_tools: set) -> tuple:
    if not tool_calls:
        return True, ""
    for tc in tool_calls:
        name = tc.get("function", {}).get("name", "")
        args = tc.get("function", {}).get("arguments", {})
        if name not in valid_tools:
            return False, f"Unknown tool requested: {name}"
        if not isinstance(args, dict):
            return False, f"Tool '{name}' arguments must be a JSON object"
    return True, ""


def parse_batch_plan(content: str, valid_tool_names: set) -> tuple:
    """
    Extract and validate a BATCH_TOOL_PLAN from LLM response text.

    Returns (plan_dict | None, error_str | None).
    - None, None means no BATCH_TOOL_PLAN found (fall back to native tool_calls).
    - None, err means BATCH_TOOL_PLAN found but invalid.
    - plan, None means valid plan ready for execution.
    """
    if not content:
        return None, None

    match = re.search(r'BATCH_TOOL_PLAN\s*(\{.*\})', content, re.DOTALL)
    if not match:
        return None, None

    try:
        plan = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        return None, f"Invalid BATCH_TOOL_PLAN JSON: {e}"

    # Validate plan_id
    plan_id = plan.get("plan_id")
    if not plan_id or not isinstance(plan_id, str):
        plan["plan_id"] = str(uuid.uuid4())

    # Validate calls
    calls = plan.get("calls", [])
    if not calls or not isinstance(calls, list):
        return None, "BATCH_TOOL_PLAN missing 'calls' array"

    for i, call in enumerate(calls):
        if not isinstance(call, dict):
            return None, f"calls[{i}] is not an object"

        call_idx = call.get("call_idx")
        if not isinstance(call_idx, int) or call_idx < 1:
            return None, f"call {i}: missing or invalid 'call_idx' (must be int >= 1)"

        tool_name = call.get("tool")
        if not isinstance(tool_name, str) or tool_name not in valid_tool_names:
            return None, f"call {call_idx}: unknown or missing tool '{tool_name}'"

        params = call.get("params", {})
        if not isinstance(params, dict):
            return None, f"call {call_idx}: 'params' must be a JSON object"

        risk_tier = call.get("risk_tier", "low")
        if risk_tier not in ("low", "medium", "high"):
            return None, f"call {call_idx}: invalid risk_tier '{risk_tier}'"

        if "correlation" not in call:
            call["correlation"] = f"c{call_idx}"

    # Validate execution_policy
    ep = plan.get("execution_policy", "auto")
    if ep not in ("auto", "sequential", "parallel", "abort_on_fail"):
        return None, f"Invalid execution_policy '{ep}'"
    plan.setdefault("execution_policy", "auto")

    return plan, None


def format_batch_result(plan_id: str, results: list) -> str:
    """Format execution results into a BATCH_TOOL_RESULT string for the LLM."""
    statuses = [r.get("status", "error") for r in results]
    if all(s == "ok" for s in statuses):
        overall = "success"
    elif all(s in ("error", "skipped") for s in statuses):
        overall = "failure"
    else:
        overall = "partial_failure"

    payload = {
        "plan_id": plan_id,
        "results": results,
        "overall_status": overall,
    }
    return f"BATCH_TOOL_RESULT {json.dumps(payload, default=str)}"
