"""
Intent Engine — maps INTENT_PLANs to skill procedures.

Replaces run_plan() for intent-based execution.
Integrates with the skill DB for auto-learning.
"""

from __future__ import annotations

import json
import logging
from typing import Callable

from skills import procedures
from skills.skill_store import search_by_intent, get_skill, save_candidate, promote_skill, record_run
from safety.reflexes import reset_session, wrap as wrap_reflex

logger = logging.getLogger(__name__)


class IntentResult:
    def __init__(self, success: bool, summary: str, data: dict | None = None, raw: str = ""):
        self.success = success
        self.summary = summary
        self.data = data or {}
        self.raw = raw

    def __repr__(self):
        return f"IntentResult(success={self.success}, summary={self.summary[:80]})"


def run_intents(
    intents: list[dict],
    execute_fn: Callable,
    verify_fn: Callable,
    user_input: str,
    tool_log: list,
) -> IntentResult:
    """Execute an INTENT_PLAN through the procedural brain."""
    reset_session()
    reflex_execute = wrap_reflex(execute_fn)
    step_log = []
    all_ok = True

    for i, intent in enumerate(intents):
        action = intent.get("action", "")
        params = intent.get("params", {})
        logger.info(f"Intent Engine [{i}]: {action} params={json.dumps(params, default=str)[:200]}")

        result = _resolve_and_run(action, params, reflex_execute, tool_log)
        # Propagate error from steps if top-level missing
        if not result.get("success") and not result.get("error"):
            for s in (result.get("steps") or []):
                if isinstance(s, dict) and not s.get("success") and s.get("error"):
                    result["error"] = s["error"]
                    break
        step_log.append({"intent_index": i, "action": action, "params": params, "result": result})

        if not result.get("success"):
            all_ok = False
            logger.warning(f"Intent Engine [{i}]: {action} failed — {result.get('error', '?')[:120]}")
            break

    ok_count = sum(1 for s in step_log if s["result"].get("success"))
    summary = f"Executed {ok_count}/{len(intents)} intent(s)"
    if not all_ok:
        failed = step_log[-1] if step_log else {}
        summary += f" — failed at intent {failed.get('intent_index', 0)}: {failed.get('action', '?')}"

    raw = json.dumps({"intents": step_log}, default=str)
    return IntentResult(success=all_ok, summary=summary, data={"steps": step_log}, raw=raw)


def _resolve_and_run(
    action: str,
    params: dict,
    tool_fn: Callable,
    tool_log: list,
) -> dict:
    # 0. Ambient-aware adjustments — check computer state before acting
    adjusted = _ambient_adjust(action, params)
    if adjusted:
        action, params = adjusted
        logger.info(f"Intent Engine: ambient-adjusted '{action}' with params={params}")

    # 1. Try skill DB (learned from past)
    skill = search_by_intent(action)
    if skill:
        logger.info(f"Intent Engine: executing skill '{skill['skill_id']}' for '{action}'")
        result = _run_skill(skill, params, tool_fn, tool_log)
        record_run(skill["skill_id"], result.get("success", False))
        return result

    # 2. Try decomposition first — compound intents (e.g., manage_app) must decompose
    #    before fuzzy matching can incorrectly grab a similar-sounding procedure.
    sub_intents = procedures.decompose(action, params)
    if sub_intents:
        logger.info(f"Intent Engine: decomposed '{action}' into {len(sub_intents)} sub-intents")
        for sub in sub_intents:
            r = _resolve_and_run(sub["action"], sub["params"], tool_fn, tool_log)
            if not r.get("success"):
                return r
        return {"success": True, "steps": sub_intents}

    # 3. Try built-in procedure
    proc, confidence = procedures.match(action)
    if proc:
        logger.info(f"Intent Engine: procedure '{proc.name}' (confidence={confidence:.2f}) for '{action}'")
        params = _fill_params(proc, params)
        result = proc.execute(params, tool_fn)
        _log_tool_calls(tool_log, action, result)

        if result.get("success"):
            _save_candidate(action, proc, params, result)

        return result

    return {"success": False, "error": f"No procedure or skill matches intent '{action}'"}


def _ambient_adjust(action: str, params: dict) -> tuple[str, dict] | None:
    """Check current computer state and adjust intent before execution.

    Returns (adjusted_action, adjusted_params) or None if no adjustment needed.
    """
    try:
        from core.ambient_state import get_state
        ambient = get_state()
        state = ambient.snapshot()
    except Exception:
        return None

    # ── open_app: if already running, focus instead ────────────────────────
    if action in ("open_app",) and params.get("name"):
        target = (params.get("name") or "").lower()
        running = state.get("running_apps") or []
        if any(target in (a or "").lower() for a in running):
            logger.info(f"Ambient: '{target}' already running — auto-redirect to focus_window")
            return ("focus_window", {"target": params["name"]})

    # ── close_app: if not running, skip ────────────────────────────────────
    if action in ("close_app", "close_window"):
        target = (params.get("name") or params.get("target") or "").lower()
        if target:
            running = state.get("running_apps") or []
            if not any(target in (a or "").lower() for a in running):
                logger.info(f"Ambient: '{target}' not running — skip close")
                return ("wait", {"seconds": 0})

    # ── type_text / press_keys: ensure a text target is focused ───────────
    if action in ("type_text", "press_keys"):
        target = (params.get("target") or "").lower()
        active = (state.get("active_window_title") or "").lower()
        if not target:
            # No target specified — auto-focus the active window if it's text-capable
            if active and active != "unknown":
                logger.info(f"Ambient: type_text with no target — using active window '{active}'")
                params["target"] = active
                return (action, params)
        elif target and target not in active:
            logger.info(f"Ambient: '{target}' is not the active window ('{active}') — auto-focus first")
            return (action, params)

    # ── focus_window: log the current active window for transparency ───────
    if action == "focus_window":
        active = state.get("active_window_title") or "unknown"
        logger.info(f"Ambient: current active window is '{active}', focusing '{params.get('target', '?')}'")

    return None


def _run_skill(skill: dict, params: dict, tool_fn: Callable, tool_log: list) -> dict:
    code = skill.get("code", "")
    if code.startswith("procedure:"):
        proc_name = code.split(":", 1)[1]
        proc = procedures.get(proc_name)
        if proc:
            params = _fill_params(proc, params)
            result = proc.execute(params, tool_fn)
            _log_tool_calls(tool_log, proc.name, result)
            return result
    lang = skill.get("language", "python")
    result = tool_fn("execute_code", {"code": code, "language": lang})
    return result


def _fill_params(proc: procedures.Procedure, params: dict) -> dict:
    """Map common param names to what the procedure expects."""
    filled = dict(params)
    for required in proc.required_params:
        if required not in filled or not filled[required]:
            for alias in ("target", "name", "app", "window", "title"):
                if alias in filled and filled[alias]:
                    filled[required] = filled[alias]
                    break
    return filled


def _save_candidate(intent: str, proc: procedures.Procedure, params: dict, result: dict):
    """Save a successful procedure execution as a candidate skill."""
    try:
        skill_id = save_candidate(
            intent_label=intent,
            code=f"procedure:{proc.name}",
            language="procedure",
        )
        if skill_id and result.get("success"):
            record_run(skill_id, True)
            skill = get_skill(skill_id)
            if skill and skill.get("run_count", 0) >= 3:
                promote_skill(skill_id)
                logger.info(f"Intent Engine: promoted skill '{skill_id}' (3+ successes)")
    except Exception as e:
        logger.debug(f"Intent Engine: candidate save skipped — {e}")


def _log_tool_calls(tool_log: list, action: str, result: dict):
    """Log procedure tool calls to the tool_log for transparency.

    Each entry uses the standard format {"tool": ..., "args": ..., "result": ...}
    so that the orchestrator's verification can correctly parse success/failure.
    """
    steps = result.get("steps", [])
    if not steps:
        tool_log.append({
            "tool": f"intent:{action}",
            "args": {},
            "result": result,
        })
    for step in steps:
        if isinstance(step, dict) and "steps" not in step:
            tool_log.append({
                "tool": action,
                "args": {},
                "result": step,
            })
