
"""
Validates LLM tool calls. Falls back to notify_user on malformed output.
Supports both native tool_calls and BATCH_TOOL_PLAN text format.
"""
import json
import logging
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


def _parse_json_object(content: str, start: int = 0):
    """Try to decode a JSON object from *start* position. Returns (plan, end) or None."""
    decoder = json.JSONDecoder()
    while start < len(content) and content[start] in (' ', '\t', '\n', '\r'):
        start += 1
    if start < len(content) and content[start] == '{':
        try:
            return decoder.raw_decode(content, start)
        except json.JSONDecodeError:
            return None
    return None


def _looks_like_batch_plan(obj) -> bool:
    """Check if *obj* has the minimum BATCH_TOOL_PLAN structure."""
    if not isinstance(obj, dict):
        return False
    calls = obj.get("calls")
    if not isinstance(calls, list) or not calls:
        return False
    if not isinstance(calls[0], dict):
        return False
    # Must have at least a tool name
    if not isinstance(calls[0].get("tool"), str):
        return False
    return True


def _validate_batch_plan(plan: dict, valid_tool_names: set) -> tuple:
    """Validate a parsed plan dict. Returns (plan, None) or (None, error_str)."""
    # Validate plan_id
    plan_id = plan.get("plan_id")
    if not plan_id or not isinstance(plan_id, str):
        plan["plan_id"] = str(uuid.uuid4())

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
        call["risk_tier"] = risk_tier

        if "correlation" not in call:
            call["correlation"] = f"c{call_idx}"

    # Validate execution_policy
    ep = plan.get("execution_policy", "auto")
    if ep not in ("auto", "sequential", "parallel", "abort_on_fail"):
        return None, f"Invalid execution_policy '{ep}'"
    plan.setdefault("execution_policy", "auto")

    return plan, None


def _validate_intent_plan(plan: dict) -> tuple:
    """Validate a parsed INTENT_PLAN dict. Returns (plan, None) or (None, error_str)."""
    intents = plan.get("intents", [])
    if not intents or not isinstance(intents, list):
        return None, "INTENT_PLAN missing 'intents' array"

    for i, intent in enumerate(intents):
        if not isinstance(intent, dict):
            return None, f"intents[{i}] is not an object"
        action = intent.get("action")
        if not isinstance(action, str) or not action.strip():
            return None, f"intents[{i}]: missing or empty 'action'"
        params = intent.get("params", {})
        if not isinstance(params, dict):
            return None, f"intents[{i}]: 'params' must be an object"

    plan.setdefault("execution_policy", "sequential")
    return plan, None


def _looks_like_intent_plan(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    intents = obj.get("intents")
    if not isinstance(intents, list) or not intents:
        return False
    if not isinstance(intents[0], dict):
        return False
    if not isinstance(intents[0].get("action"), str):
        return False
    return True


def parse_intent_plan(content: str) -> tuple:
    """
    Extract and validate an INTENT_PLAN from LLM response text.

    Format: INTENT_PLAN {"intents": [{"action": "...", "params": {...}}], "execution": "sequential"}

    Returns (plan_dict | None, error_str | None).
    """
    if not content:
        return None, None

    idx = content.find("INTENT_PLAN")
    if idx >= 0:
        json_start = idx + len("INTENT_PLAN")
        while json_start < len(content) and content[json_start] in (' ', '\t', '\n', '\r'):
            json_start += 1
        parsed = _parse_json_object(content, json_start)
        if parsed:
            plan, _ = parsed
            return _validate_intent_plan(plan)
        return None, "Invalid INTENT_PLAN JSON"

    search_start = 0
    while search_start < len(content):
        brace_pos = content.find('{', search_start)
        if brace_pos < 0:
            break
        parsed = _parse_json_object(content, brace_pos)
        if parsed is not None:
            plan, end = parsed
            if _looks_like_intent_plan(plan):
                return _validate_intent_plan(plan)
            search_start = end
        else:
            search_start = brace_pos + 1

    return None, None


def parse_batch_plan(content: str, valid_tool_names: set) -> tuple:
    """
    Extract and validate a BATCH_TOOL_PLAN from LLM response text.

    Supports two formats:
      - ``BATCH_TOOL_PLAN {"plan_id":..., "calls":[...]}`` (tagged)
      - Bare ``{"plan_id":..., "calls":[...]}`` (untagged)

    Returns (plan_dict | None, error_str | None).
    - None, None means no BATCH_TOOL_PLAN found (fall back to native tool_calls).
    - None, err means BATCH_TOOL_PLAN found but invalid.
    - plan, None means valid plan ready for execution.
    """
    if not content:
        return None, None

    # Try tagged format first: BATCH_TOOL_PLAN {...}
    idx = content.find("BATCH_TOOL_PLAN")
    if idx >= 0:
        decoder = json.JSONDecoder()
        json_start = idx + len("BATCH_TOOL_PLAN")
        while json_start < len(content) and content[json_start] in (' ', '\t', '\n', '\r'):
            json_start += 1
        parsed = _parse_json_object(content, json_start)
        if parsed:
            plan, _ = parsed
            return _validate_batch_plan(plan, valid_tool_names)
        return None, f"Invalid BATCH_TOOL_PLAN JSON"

    # Try bare JSON format: {...} without tag
    # Scan for JSON objects starting at each '{' position
    search_start = 0
    while search_start < len(content):
        # Find the next '{' character
        brace_pos = content.find('{', search_start)
        if brace_pos < 0:
            break
        parsed = _parse_json_object(content, brace_pos)
        if parsed is not None:
            plan, end = parsed
            if _looks_like_batch_plan(plan):
                return _validate_batch_plan(plan, valid_tool_names)
            search_start = end
        else:
            search_start = brace_pos + 1

    return None, None


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
