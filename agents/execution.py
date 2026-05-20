"""
Execution agent — tool orchestration, validation, verification, retries.
Does not converse with the user. Returns BATCH_TOOL_RESULT / validation errors only.
"""

from __future__ import annotations

import contextlib
import concurrent.futures
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from brain.response_parser import format_batch_result
from brain.structured_log import (
    guard_triggered as _log_guard,
    tool_call as _log_tool_call,
)
from brain.tool_result_cache import ToolResultCache
from safety.reflexes import wrap as wrap_reflex

logger = logging.getLogger(__name__)

# Per-call execution retries before reporting failure to Jarvis
MAX_CALL_RETRIES = 2

PERCEPTION_TOOLS = frozenset(
    {"vision_query", "read_screen", "detect_ui_elements", "screenshot"}
)
INTERACTION_TOOLS = frozenset(
    {
        "click",
        "double_click",
        "right_click",
        "move_mouse",
        "drag",
        "type_text",
        "press_keys",
        "scroll",
        "set_volume",
        "set_brightness",
        "click_element",
        "type_in_element",
    }
)

VISUAL_VERIFY_TOOLS = frozenset(
    {
        "click",
        "double_click",
        "right_click",
        "type_text",
        "press_keys",
        "click_element",
        "type_in_element",
    }
)


@dataclass
class PlanRunResult:
    """Outcome of executing one BATCH_TOOL_PLAN."""

    result_msg: str
    deferred_calls: list[dict] = field(default_factory=list)
    has_failures: bool = False
    validation_errors: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fast schema-based tool validator (replaces the LLM-based validator).
#
# The original implementation called an executor LLM to validate every tool
# call before executing it.  This added 1-3 seconds of latency per tool and
# provided no meaningful safety benefit beyond what the safety funnel already
# does via AST checks and schema validation in safety/executor.py.
#
# This replacement:
#   1. Loads the tool schema from tools/schemas.json (the single source of truth)
#   2. Checks required fields are present and non-empty
#   3. Checks field types for known properties
#   4. Checks enum constraints
#   5. Returns None (valid) or an error string — same contract as before
#
# Zero LLM calls. Typical latency: <1 ms.
# ---------------------------------------------------------------------------

_SCHEMA_CACHE: dict = {}
_SCHEMA_LOCK = threading.Lock()


def _load_schemas() -> dict:
    global _SCHEMA_CACHE
    with _SCHEMA_LOCK:
        if _SCHEMA_CACHE:
            return _SCHEMA_CACHE
        try:
            from tools import ALL_SCHEMAS
            _SCHEMA_CACHE = ALL_SCHEMAS
        except Exception as e:
            logger.warning(f"Could not load tool schemas from tools module: {e}")
            # Fallback: read schemas.json directly (custom tools won't be validated)
            from pathlib import Path
            schemas_path = Path(__file__).parent.parent / "tools" / "schemas.json"
            try:
                with open(schemas_path, encoding="utf-8") as f:
                    raw = json.load(f)
                raw.pop("$schema", None)
                _SCHEMA_CACHE = raw
            except Exception as e2:
                logger.warning(f"Could not load tool schemas from file: {e2}")
                _SCHEMA_CACHE = {}
        return _SCHEMA_CACHE


def validate_tool_call(tool_name: str, args: dict) -> str | None:
    """
    Fast schema-based validation. Returns None if valid, error string if not.

    Replaces the old LLM-based validator — same contract, zero latency.
    """
    schemas = _load_schemas()
    entry = schemas.get(tool_name)

    if entry is None:
        # Unknown tool — let the safety funnel catch it; don't block here
        return None

    schema = entry.get("input", {})
    props = schema.get("properties", {})
    required = schema.get("required", [])

    # 1. Required fields must be present and non-empty
    for key in required:
        val = args.get(key)
        if val is None or val == "":
            return f"Missing required parameter '{key}' for tool '{tool_name}'"

    # 2. Type checks and enum constraints for provided fields
    for key, value in args.items():
        prop = props.get(key)
        if prop is None:
            continue  # Extra fields are allowed

        ptype = prop.get("type", "")
        if ptype == "integer" and not isinstance(value, int):
            # Allow int-valued floats (e.g. 5.0 → ok for integer fields)
            if isinstance(value, float) and value.is_integer():
                continue
            return f"Parameter '{key}' must be integer for tool '{tool_name}', got {type(value).__name__}"
        if ptype == "boolean" and not isinstance(value, bool):
            return f"Parameter '{key}' must be boolean for tool '{tool_name}', got {type(value).__name__}"
        if ptype == "string" and not isinstance(value, str):
            return f"Parameter '{key}' must be string for tool '{tool_name}', got {type(value).__name__}"
        if ptype == "array" and not isinstance(value, list):
            return f"Parameter '{key}' must be array for tool '{tool_name}', got {type(value).__name__}"
        if ptype == "number" and not isinstance(value, (int, float)):
            return f"Parameter '{key}' must be number for tool '{tool_name}', got {type(value).__name__}"

        enum_vals = prop.get("enum")
        if enum_vals and value not in enum_vals:
            return f"Parameter '{key}' must be one of {enum_vals} for tool '{tool_name}', got {value!r}"

    return None


def validate_plan_calls(plan: dict) -> list[dict]:
    """Validate every call in a plan. Returns list of {call_idx, error}."""
    errors = []
    for call in plan.get("calls", []):
        tool_name = call.get("tool", "")
        args = call.get("params", {})
        err = validate_tool_call(tool_name, args)
        if err:
            errors.append({"call_idx": call.get("call_idx"), "tool": tool_name, "error": err})
    return errors


def split_perception_interaction(plan: dict) -> tuple[dict, list[dict]]:
    """
    If plan mixes perception + interaction, run perception only this round.
    Returns (plan_to_run, deferred_interaction_calls).
    """
    calls = plan.get("calls", [])
    has_perception = any(c.get("tool") in PERCEPTION_TOOLS for c in calls)
    has_interaction = any(c.get("tool") in INTERACTION_TOOLS for c in calls)
    if not (has_perception and has_interaction):
        return plan, []

    deferred = [c for c in calls if c.get("tool") in INTERACTION_TOOLS]
    plan = {
        **plan,
        "calls": [c for c in calls if c.get("tool") not in INTERACTION_TOOLS],
        "execution_policy": "sequential",
    }
    logger.info(
        "Execution auto-split: deferring %d interaction call(s) (%s)",
        len(deferred),
        ", ".join(c["tool"] for c in deferred),
    )
    return plan, deferred


def _execution_policy(plan: dict) -> tuple[str, list[int]]:
    calls = plan["calls"]
    policy = plan.get("execution_policy", "auto")
    if policy == "parallel":
        return "parallel", [c["call_idx"] for c in calls]
    if policy in ("sequential", "abort_on_fail"):
        return "sequential", [c["call_idx"] for c in calls]
    correlations = {c.get("correlation") for c in calls if c.get("correlation")}
    params_blob = " ".join(json.dumps(c.get("params", {}), default=str) for c in calls)
    has_deps = any(corr and corr in params_blob for corr in correlations)
    return ("parallel" if not has_deps else "sequential"), [c["call_idx"] for c in calls]


def _call_by_idx(plan: dict, idx: int) -> dict | None:
    for c in plan["calls"]:
        if c["call_idx"] == idx:
            return c
    return None


def _summarize_output(tool_name: str, result: dict) -> str:
    if not result.get("success"):
        err = result.get("message", "unknown error")
        return f"{tool_name} failed: {str(err)[:200]}"
    data = result.get("data", {})
    content = data.get("output") or data.get("result") or data.get("content") or ""
    if isinstance(content, str):
        content = content[:500]
    elif isinstance(content, dict):
        content = json.dumps(content, default=str)[:200]
    return f"{tool_name}: {content}" if content else f"{tool_name} succeeded"


def _resolve_value(val, path: str):
    if not path:
        return val
    parts = re.split(r"\.|\[|\]", path)
    parts = [p for p in parts if p]
    current = val
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return None
        elif isinstance(current, list):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _resolve_template(value: str, prior_results: list[dict], corr_to_result: dict) -> object:
    m = re.fullmatch(r"\$\{last_result\.(.+?)\}", value)
    if m:
        last = prior_results[-1] if prior_results else None
        if last:
            full = last.get("full_output", "{}")
            try:
                obj = json.loads(full)
            except (json.JSONDecodeError, TypeError):
                return value
            resolved = _resolve_value(obj, m.group(1))
            return resolved if resolved is not None else value

    m = re.fullmatch(r"\{\{(\w+)\.(.+?)\}\}", value)
    if m:
        pr = corr_to_result.get(m.group(1))
        if pr:
            full = pr.get("full_output", "{}")
            try:
                obj = json.loads(full)
            except (json.JSONDecodeError, TypeError):
                return value
            resolved = _resolve_value(obj, m.group(2))
            return resolved if resolved is not None else value

    def _replace_last(match):
        last = prior_results[-1] if prior_results else None
        if last is None:
            return match.group(0)
        full = last.get("full_output", "{}")
        try:
            obj = json.loads(full)
        except (json.JSONDecodeError, TypeError):
            return match.group(0)
        resolved = _resolve_value(obj, match.group(1))
        return str(resolved) if resolved is not None else match.group(0)

    value = re.sub(r"\$\{last_result\.(.+?)\}", _replace_last, value)

    def _replace_corr(match):
        corr_id = match.group(1)
        path = match.group(2)
        pr = corr_to_result.get(corr_id)
        if pr is None:
            return match.group(0)
        full = pr.get("full_output", "{}")
        try:
            obj = json.loads(full)
        except (json.JSONDecodeError, TypeError):
            return match.group(0)
        resolved = _resolve_value(obj, path)
        return str(resolved) if resolved is not None else match.group(0)

    return re.sub(r"\{\{(\w+)\.(.+?)\}\}", _replace_corr, value)


def _resolve_params(params: dict, prior_results: list[dict], calls: list[dict]) -> dict:
    corr_to_result: dict[str, dict] = {}
    for c in calls:
        corr = c.get("correlation")
        if corr:
            for pr in prior_results:
                if pr.get("call_idx") == c.get("call_idx"):
                    corr_to_result[corr] = pr
                    break

    resolved = {}
    for key, value in params.items():
        if isinstance(value, str):
            resolved[key] = _resolve_template(value, prior_results, corr_to_result)
        else:
            resolved[key] = value
    return resolved


def _execute_single_call(
    call: dict,
    execute_fn: Callable,
    verify_fn: Callable,
    user_input: str,
    cache,
    tool_log: list,
    fail_counts: dict,
    pc_state_fn,
    iteration: int,
    log_lock=None,
    fail_lock=None,
) -> dict:
    tool_name = call["tool"]
    args = call.get("params", {})
    call_idx = call["call_idx"]
    truncated_call_idx = min(call_idx, 9999)
    # Null-safe context managers — callers in parallel mode pass real locks;
    # sequential callers get no-op contexts with zero overhead.
    _log_ctx = log_lock if log_lock is not None else contextlib.nullcontext()
    _fail_ctx = fail_lock if fail_lock is not None else contextlib.nullcontext()

    # Fast schema validation (no LLM)
    validation_error = validate_tool_call(tool_name, args)
    if validation_error:
        logger.warning(f"Execution rejected {tool_name}: {validation_error[:200]}")
        _log_entry = {
            "tool": tool_name,
            "args": args,
            "result": {"success": False, "error": f"schema rejected: {validation_error}"},
            "call_id": f"batch_{truncated_call_idx}",
            "cached": False,
        }
        with _log_ctx:
            tool_log.append(_log_entry)
        return {
            "call_idx": call_idx,
            "call_id": f"call_{truncated_call_idx}",
            "status": "error",
            "error": validation_error,
            "output_summary": f"{tool_name} validation failed: {validation_error}",
        }

    cached_result = cache.get(tool_name, args)
    if cached_result is not None:
        logger.info(f"  ✓ {tool_name} (cached)")
        result = cached_result
        # Run verify_fn *outside* the lock — it may block on I/O.
        _log_tool_call(iteration, tool_name, args, True, 0, cached=True)
        verification = verify_fn(tool_name, result, user_input)
        _log_entry = {
            "tool": tool_name,
            "args": args,
            "result": result,
            "call_id": f"batch_{truncated_call_idx}",
            "cached": True,
        }
        with _log_ctx:
            tool_log.append(_log_entry)
            _log_entry["verification"] = verification.get("status", "")
        return {
            "call_idx": call_idx,
            "call_id": f"call_{truncated_call_idx}",
            "status": "ok",
            "output_summary": _summarize_output(tool_name, result),
            "cached": True,
        }

    result = None
    verification = {}
    last_error = None

    _reflex_execute = wrap_reflex(execute_fn)
    for attempt in range(1, MAX_CALL_RETRIES + 1):
        logger.info(f"Batch {iteration}: calling {tool_name} (call_idx={call_idx}, attempt={attempt})")
        
        pre_img = None
        if tool_name in VISUAL_VERIFY_TOOLS:
            try:
                from verification.visual_verifier import capture_screenshot
                pre_img = capture_screenshot()
            except Exception:
                pass

        _t0 = time.time()
        print(f"  🔧 {tool_name}...", end="", flush=True)
        result = _reflex_execute(tool_name, args)
        _elapsed = (time.time() - _t0) * 1000
        ok_str = "✓" if result.get("success") else "✗"
        print(f"\r  🔧 {tool_name} {ok_str}" + " " * 10, flush=True)

        post_img = None
        if tool_name in VISUAL_VERIFY_TOOLS and result.get("success"):
            try:
                time.sleep(0.15)
                from verification.visual_verifier import capture_screenshot
                post_img = capture_screenshot()
            except Exception:
                pass

        import inspect
        sig = inspect.signature(verify_fn)
        verify_kwargs = {}
        if "pre_img" in sig.parameters:
            verify_kwargs["pre_img"] = pre_img
        if "post_img" in sig.parameters:
            verify_kwargs["post_img"] = post_img
        verification = verify_fn(tool_name, result, user_input, **verify_kwargs)
        v_ok = verification.get("status") != "FAILED"
        if result.get("success") and v_ok:
            _log_tool_call(
                iteration, tool_name, args, True, _elapsed, error=None, cached=False
            )
            break

        # Capture error for structured retry feedback
        last_error = result.get("message") or result.get("error") or verification.get("summary", "verification failed")

        if attempt < MAX_CALL_RETRIES and tool_name != "delegate_to_subagent":
            logger.info(f"  retry {tool_name} ({attempt}/{MAX_CALL_RETRIES}): {last_error}")
            if tool_name in ("execute_code", "run_python") and "code" in args:
                data = result.get("data", {})
                stderr = result.get("message", "") or data.get("stderr", "")
                stdout = data.get("output", "") or data.get("result", "") or data.get("content", "")
                hint = (
                    f"\n# --- Previous attempt failed ---\n"
                    f"# stderr: {stderr[:300]}\n"
                    f"# stdout: {stdout[:200]}\n"
                    f"# Fix the error above and retry.\n"
                )
                args = {**args, "_retry_hint": hint}
            time.sleep(0.3)
        else:
            _log_tool_call(
                iteration,
                tool_name,
                args,
                False,
                _elapsed,
                error=last_error,
                cached=False,
            )

    cache.set(tool_name, args, result)
    if tool_name in ToolResultCache.WRITE_TOOLS:
        cache.invalidate_tool(tool_name)
        if tool_name == "execute_code":
            cache.clear()

    tool_failed = not result.get("success") or verification.get("status") == "FAILED"

    # Use a direct dict reference so we never rely on tool_log[-1] across threads.
    _log_entry = {
        "tool": tool_name,
        "args": args,
        "result": result,
        "call_id": f"batch_{truncated_call_idx}",
        "cached": False,
    }
    with _log_ctx:
        tool_log.append(_log_entry)
        _log_entry["verification"] = verification.get("status", "")

    _hit_guard = False
    with _fail_ctx:
        if tool_failed:
            fail_counts[tool_name] = fail_counts.get(tool_name, 0) + 1
        else:
            fail_counts[tool_name] = 0
        # Capture guard flag inside the lock so the read is atomic with the write.
        _hit_guard = tool_failed and fail_counts[tool_name] >= 2

    if _hit_guard:
        _log_guard(tool_name, iteration, f"FAIL-LOOP GUARD: '{tool_name}' failed twice in a row")
        _log_entry["blocked"] = "fail-loop_guard"
        return {
            "call_idx": call_idx,
            "call_id": f"call_{truncated_call_idx}",
            "status": "error",
            "error": f"FAIL-LOOP GUARD: '{tool_name}' failed twice in a row",
            "output_summary": f"{tool_name} blocked by fail-loop guard",
        }

    res: dict = {
        "call_idx": call_idx,
        "call_id": f"call_{truncated_call_idx}",
        "status": "ok" if result.get("success") and verification.get("status") != "FAILED" else "error",
        "output_summary": _summarize_output(tool_name, result),
        "full_output": json.dumps(result, default=str)[:3000],  # increased from 1000
    }

    if verification.get("status") == "FAILED":
        res["verification"] = "FAILED"
        if verification.get("method") == "visual_diff":
            res["retry_directive"] = (
                "Visual verification detected no screen changes. Target element may have been obscured or coordinate was wrong. "
                "Recovery Recommendation: Backtrack or try alternative keyboard/mouse navigation (e.g., press Alt/Tab to change focus, or use press_keys with shortcut keys, or click_element on parent menu first)."
            )
        else:
            res["retry_directive"] = (
                "Verification FAILED — try a different tool or parameters."
            )

    if not result.get("success"):
        res["error"] = result.get("error", last_error or "unknown error")

    if tool_failed and tool_name != "read_pc_state" and pc_state_fn is not None:
        try:
            state = pc_state_fn()
            if state.get("success"):
                res["state_snapshot"] = {
                    "focused_window": state.get("focused_window"),
                    "open_windows_count": len(state.get("windows", [])),
                    "running_processes_count": len(state.get("processes", [])),
                }
        except Exception:
            pass

    return res


def execute_batch_plan(
    plan: dict,
    execute_fn: Callable,
    verify_fn: Callable,
    user_input: str,
    cache,
    tool_log: list,
    fail_counts: dict,
    pc_state_fn,
    iteration: int,
) -> list[dict]:
    mode, order = _execution_policy(plan)
    calls = plan["calls"]
    results: list[dict] = []

    _tool_log_lock = threading.Lock()
    _fail_lock = threading.Lock()

    def _run_one(call: dict) -> dict:
        # Do NOT hold locks here — that would serialise all "parallel" threads
        # for the entire duration of the blocking tool call.  Instead, pass the
        # locks into _execute_single_call so only the tiny critical sections
        # (tool_log.append and fail_counts update) are gated.
        return _execute_single_call(
            call,
            execute_fn,
            verify_fn,
            user_input,
            cache,
            tool_log,
            fail_counts,
            pc_state_fn,
            iteration,
            log_lock=_tool_log_lock,
            fail_lock=_fail_lock,
        )

    if mode == "parallel":
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(calls), 1)) as pool:
            fut_map = {pool.submit(_run_one, c): c for c in calls}
            for fut in concurrent.futures.as_completed(fut_map):
                try:
                    results.append(fut.result())
                except Exception as e:
                    c = fut_map[fut]
                    results.append(
                        {
                            "call_idx": c["call_idx"],
                            "call_id": f"call_{c['call_idx']}",
                            "status": "error",
                            "error": str(e),
                        }
                    )
    else:
        abort = False
        for call_idx in order:
            if abort:
                results.append(
                    {
                        "call_idx": call_idx,
                        "call_id": f"call_{call_idx}",
                        "status": "skipped",
                        "error": "aborted by previous failure",
                    }
                )
                continue
            call = _call_by_idx(plan, call_idx)
            if call is None:
                results.append(
                    {
                        "call_idx": call_idx,
                        "call_id": f"call_{call_idx}",
                        "status": "error",
                        "error": f"call_idx {call_idx} not found in plan",
                    }
                )
                continue

            if call.get("risk_tier") == "high" and call.get("preexec_required"):
                results.append(
                    {
                        "call_idx": call_idx,
                        "call_id": f"call_{call_idx}",
                        "status": "pending_approval",
                        "error": "high-risk call requires approval before execution",
                    }
                )
                continue

            resolved_params = _resolve_params(call.get("params", {}), results, calls)
            if resolved_params != call.get("params"):
                call = {**call, "params": resolved_params}

            r = _run_one(call)
            results.append(r)
            if r["status"] != "ok" and plan.get("execution_policy") == "abort_on_fail":
                abort = True

    results.sort(key=lambda r: r.get("call_idx", 0))
    return results


def run_plan(
    plan: dict,
    execute_fn: Callable,
    verify_fn: Callable,
    user_input: str,
    cache,
    tool_log: list,
    fail_counts: dict,
    pc_state_fn,
    iteration: int,
) -> PlanRunResult:
    """Execute a BATCH_TOOL_PLAN (with auto-split). Returns structured result for Jarvis."""
    plan, deferred = split_perception_interaction(plan)

    validation_errors = validate_plan_calls(plan)
    if validation_errors:
        plan_id = plan.get("plan_id", "unknown")
        msg = (
            f"TOOL_VALIDATION_ERROR plan_id={plan_id} "
            + json.dumps({"errors": validation_errors}, default=str)
        )
        return PlanRunResult(
            result_msg=msg,
            deferred_calls=deferred,
            has_failures=True,
            validation_errors=validation_errors,
        )

    # Execute directly — no executor-LLM pre-call gate.
    # The per-call retry loop inside execute_batch_plan already handles failures;
    # adding a full LLM round-trip *before* every tool call costs 0.5-3 s each
    # and returns PASS almost 100 % of the time.
    results = execute_batch_plan(
        plan,
        execute_fn,
        verify_fn,
        user_input,
        cache,
        tool_log,
        fail_counts,
        pc_state_fn,
        iteration,
    )
    result_msg = format_batch_result(plan.get("plan_id", "unknown"), results)
    has_failures = any(
        r.get("status") in ("error", "skipped", "pending_approval")
        or r.get("verification") == "FAILED"
        for r in results
    )
    return PlanRunResult(
        result_msg=result_msg,
        deferred_calls=deferred,
        has_failures=has_failures,
    )


def run_native_tool_calls(
    tool_calls: list[dict],
    content: str,
    execute_fn: Callable,
    verify_fn: Callable,
    user_input: str,
    cache,
    tool_log: list,
    fail_counts: dict,
    pc_state_fn,
    iteration: int,
) -> tuple[list[dict], bool]:
    """
    Execute native LLM tool_calls. Returns (tool_result messages, should_stop_loop).
    should_stop_loop True when fail-loop guard triggers.
    """
    tool_results = []
    stop_loop = False

    for tc in tool_calls:
        name = tc["function"]["name"]
        args = tc["function"]["arguments"]
        logger.info(f"Execution native {iteration}: {name}")

        # Fast schema validation (no LLM)
        validation_error = validate_tool_call(name, args)
        if validation_error:
            tool_log.append(
                {
                    "tool": name,
                    "args": args,
                    "result": {"success": False, "error": f"schema rejected: {validation_error}"},
                    "call_id": tc["id"],
                    "cached": False,
                }
            )
            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(
                        {
                            "result": {
                                "success": False,
                                "error": f"TOOL_VALIDATION_ERROR: {validation_error}",
                            },
                            "verification": {"status": "REJECTED"},
                        },
                        default=str,
                    ),
                }
            )
            continue

        cached_result = cache.get(name, args)
        result = None
        verification = {}

        if cached_result is not None:
            result = cached_result
            tool_log.append(
                {"tool": name, "args": args, "result": result, "call_id": tc["id"], "cached": True}
            )
            _log_tool_call(iteration, name, args, True, 0, cached=True)
            verification = verify_fn(name, result, user_input)
        else:
            for attempt in range(1, MAX_CALL_RETRIES + 1):
                pre_img = None
                if name in VISUAL_VERIFY_TOOLS:
                    try:
                        from verification.visual_verifier import capture_screenshot
                        pre_img = capture_screenshot()
                    except Exception:
                        pass

                _t0 = time.time()
                print(f"  🔧 {name}...", end="", flush=True)
                result = execute_fn(name, args)
                _elapsed = (time.time() - _t0) * 1000
                ok_str = "✓" if result.get("success") else "✗"
                print(f"\r  🔧 {name} {ok_str}" + " " * 10, flush=True)

                post_img = None
                if name in VISUAL_VERIFY_TOOLS and result.get("success"):
                    try:
                        time.sleep(0.15)
                        from verification.visual_verifier import capture_screenshot
                        post_img = capture_screenshot()
                    except Exception:
                        pass

                import inspect
                sig = inspect.signature(verify_fn)
                verify_kwargs = {}
                if "pre_img" in sig.parameters:
                    verify_kwargs["pre_img"] = pre_img
                if "post_img" in sig.parameters:
                    verify_kwargs["post_img"] = post_img
                verification = verify_fn(name, result, user_input, **verify_kwargs)
                if result.get("success") and verification.get("status") != "FAILED":
                    _log_tool_call(iteration, name, args, True, _elapsed, cached=False)
                    break

                last_error = result.get("error", "")
                if attempt < MAX_CALL_RETRIES and name != "delegate_to_subagent":
                    # BUG FIX: align retry hint with _execute_single_call — include
                    # stdout and use the richer message format so the LLM has full
                    # context when rewriting failing code on the next attempt.
                    if name in ("execute_code", "run_python") and "code" in args:
                        data = result.get("data", {})
                        stderr = (
                            result.get("message", "")
                            or data.get("stderr", "")
                            or result.get("error", "")
                        )
                        stdout = (
                            data.get("output", "")
                            or data.get("result", "")
                            or data.get("content", "")
                        )
                        args = {
                            **args,
                            "_retry_hint": (
                                f"\n# --- Previous attempt failed ---\n"
                                f"# stderr: {stderr[:300]}\n"
                                f"# stdout: {stdout[:200]}\n"
                                f"# Fix the error above and retry.\n"
                            ),
                        }
                    time.sleep(0.3)
                else:
                    _log_tool_call(
                        iteration,
                        name,
                        args,
                        False,
                        _elapsed,
                        error=last_error,
                        cached=False,
                    )

            tool_log.append(
                {"tool": name, "args": args, "result": result, "call_id": tc["id"], "cached": False}
            )
            cache.set(name, args, result)

        tool_log[-1]["verification"] = verification.get("status", "")

        if name in ToolResultCache.WRITE_TOOLS:
            cache.invalidate_tool(name)
            if name == "execute_code":
                cache.clear()

        if not result.get("success") or verification.get("status") == "FAILED":
            fail_counts[name] = fail_counts.get(name, 0) + 1
            if fail_counts[name] >= 2:
                _log_guard(
                    name,
                    iteration,
                    f"FAIL-LOOP GUARD: '{name}' failed twice in a row",
                )
                stop_loop = True
        else:
            fail_counts[name] = 0

        safe_result = dict(result)
        for _key in ("image_b64", "screenshot", "image"):
            safe_result.pop(_key, None)
            if isinstance(safe_result.get("data"), dict):
                safe_result["data"].pop(_key, None)

        if verification.get("status") == "FAILED":
            verification["retry_directive"] = (
                "Verification FAILED — try a different tool or parameters."
            )

        if (
            (not result.get("success") or verification.get("status") == "FAILED")
            and name != "read_pc_state"
            and pc_state_fn is not None
        ):
            try:
                state_snapshot = pc_state_fn()
                if state_snapshot.get("success"):
                    verification["state_snapshot"] = {
                        "focused_window": state_snapshot.get("focused_window"),
                        "open_windows_count": len(state_snapshot.get("windows", [])),
                        "running_processes_count": len(state_snapshot.get("processes", [])),
                    }
            except Exception:
                pass

        tool_results.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(
                    {"result": safe_result, "verification": verification},
                    default=str,
                ),
            }
        )

    return tool_results, stop_loop


class ExecutionAgent:
    """Operator agent — orchestrates tools; no user-facing language."""

    def __init__(self, execute_fn: Callable, verify_fn: Callable, pc_state_fn=None):
        self.execute_fn = execute_fn
        self.verify_fn = verify_fn
        self.pc_state_fn = pc_state_fn

    def run_plan(self, plan, user_input, cache, tool_log, fail_counts, iteration) -> PlanRunResult:
        return run_plan(
            plan,
            self.execute_fn,
            self.verify_fn,
            user_input,
            cache,
            tool_log,
            fail_counts,
            self.pc_state_fn,
            iteration,
        )
