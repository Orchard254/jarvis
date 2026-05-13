"""
Unified safety funnel. All tool calls pass through here.
"""

import logging

from core.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
from safety import audit_log
from safety.confidence_gate import check as confidence_check
from safety.plan_validator import validate as plan_validate
from safety.tool_guard import check_paths

logger = logging.getLogger(__name__)

# Global circuit breaker registry — one breaker per tool name
# Opens after 3 consecutive failures, auto-recovers after 60s cooldown
circuit_breakers = CircuitBreakerRegistry()


def execute(tool_name: str, tool_fn, args: dict, plan: dict = None):
    allowed, reason = check_paths(args)
    if not allowed:
        audit_log.log_blocked(tool_name, args, reason)
        return {"success": False, "blocked": True, "error": reason}

    language = args.get("language", "python")
    if tool_name == "execute_code":
        from safety.tool_guard import check_imports

        allowed, reason = check_imports(args.get("code", ""), language)
        if not allowed:
            audit_log.log_blocked(tool_name, args, reason)
            return {"success": False, "blocked": True, "error": reason}
        if language not in ("python", "powershell"):
            audit_log.log_blocked(tool_name, args, f"Unsupported language: {language}")
            return {
                "success": False,
                "blocked": True,
                "error": f"Unsupported language: {language}",
            }

    logger.info(
        f"Executing {tool_name} (lang={language}) with confidence={plan.get('confidence') if plan else None}"
    )

    if plan:
        proceed, reason = confidence_check(plan)
        if not proceed:
            from tools.notify_user import notify_user

            notify_user(f"Action paused: {reason}", urgency="normal")
            audit_log.log_blocked(tool_name, args, reason)
            return {"success": False, "blocked": True, "error": reason, "paused": True}

    # Validate plan for destructive patterns (plan_validator was imported but never called)
    validate_plan = {**(plan or {}), **args}
    valid, reason = plan_validate(validate_plan)
    if not valid:
        audit_log.log_blocked(tool_name, args, reason)
        return {"success": False, "blocked": True, "error": reason}

    # Strip empty/whitespace keys — LLM occasionally emits {"": null} which
    # causes TypeError when splatted: f(**{"": x}) → unexpected keyword ""
    clean_args = {k: v for k, v in args.items() if k and k.strip()}

    # Circuit breaker check — prevents cascading failures when a tool
    # consistently fails (opens after 3 consecutive failures, auto-recovers
    # after 60s). The breaker records success/failure automatically.
    cb = circuit_breakers.get_or_create(tool_name, failure_threshold=3)
    try:
        result = cb.sync_call(tool_fn, **clean_args)
    except CircuitOpenError:
        audit_log.log_blocked(tool_name, clean_args, "circuit_breaker_open")
        return {
            "success": False,
            "blocked": True,
            "error": f"Tool '{tool_name}' is temporarily unavailable due to recent failures. Try again later or use a different approach.",
        }

    audit_log.log_call(tool_name, clean_args, result)
    if isinstance(result, list):
        return {"success": True, "results": result}
    return result
