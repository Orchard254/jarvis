"""
The ReAct tool-calling loop. Pure reasoning layer.
Executes tools via injected callbacks to maintain strict layer boundaries.
"""

import concurrent.futures
import json
import logging
import threading

from settings import (
    ITERATION_CAPS,
    MAX_CONTEXT_TOKENS,
    TOOL_LOOP_HISTORY_MESSAGES,
)
from verification.vision_summary import summarize_screen

from brain import ollama_client
from brain.context_manager import prune_history
from brain.prompt_builder import build_system_prompt, get_pruned_schemas
from brain.response_parser import parse_batch_plan, format_batch_result, validate_tool_calls
from brain.tool_result_cache import get_cache, ToolResultCache

logger = logging.getLogger(__name__)


# Temperature/effort is now determined by the LLM's own reasoning.
# No hardcoded keyword detection — the model decides whether a request
# is a chat response or a tool-calling task based on full context.


def _execution_policy(plan: dict) -> tuple[str, list[int]]:
    """Resolve execution order: ('sequential'|'parallel', ordered call indices)."""
    calls = plan["calls"]
    policy = plan.get("execution_policy", "auto")
    if policy == "parallel":
        return "parallel", [c["call_idx"] for c in calls]
    if policy in ("sequential", "abort_on_fail"):
        return "sequential", [c["call_idx"] for c in calls]
    # auto: parallel if no dependencies, sequential otherwise
    correlations = {c.get("correlation") for c in calls if c.get("correlation")}
    has_deps = False
    params_blob = " ".join(json.dumps(c.get("params", {}), default=str) for c in calls)
    for corr in correlations:
        if corr and corr in params_blob:
            has_deps = True
            break
    return ("parallel" if not has_deps else "sequential"), [c["call_idx"] for c in calls]


def _call_by_idx(plan: dict, idx: int) -> dict | None:
    """Look up a plan call by its call_idx."""
    for c in plan["calls"]:
        if c["call_idx"] == idx:
            return c
    return None


def _execute_single_call(
    call: dict,
    execute_fn,
    verify_fn,
    user_input: str,
    cache,
    tool_log: list,
    fail_counts: dict,
    pc_state_fn,
    iteration: int,
) -> dict:
    """
    Execute one planned call. Returns a result dict for BATCH_TOOL_RESULT.
    Side-effects: appends to tool_log, mutates fail_counts, updates cache.
    """
    tool_name = call["tool"]
    args = call.get("params", {})
    call_idx = call["call_idx"]
    logger.info(f"Batch {iteration}: calling {tool_name} (call_idx={call_idx})")

    truncated_call_idx = min(call_idx, 9999)  # for stable call_id generation

    # Check cache for read-only tools
    cached_result = cache.get(tool_name, args)
    if cached_result is not None:
        logger.info(f"  \u2713 {tool_name} (cached)")
        result = cached_result
        tool_log.append({"tool": tool_name, "args": args, "result": result,
                         "call_id": f"batch_{truncated_call_idx}", "cached": True})
        verification = verify_fn(tool_name, result, user_input)
        if tool_log:
            tool_log[-1]["verification"] = verification.get("status", "")
        return {
            "call_idx": call_idx,
            "call_id": f"call_{truncated_call_idx}",
            "status": "ok",
            "output_summary": _summarize_output(tool_name, result),
            "cached": True,
        }

    print(f"  \U0001f527 {tool_name}...", end="", flush=True)
    result = execute_fn(tool_name, args)
    ok_str = "\u2713" if result.get("success") else "\u2717"
    print(f"\r  \U0001f527 {tool_name} {ok_str}" + " " * 10, flush=True)
    tool_log.append({"tool": tool_name, "args": args, "result": result,
                     "call_id": f"batch_{truncated_call_idx}", "cached": False})

    cache.set(tool_name, args, result)

    verification = verify_fn(tool_name, result, user_input)
    if tool_log:
        tool_log[-1]["verification"] = verification.get("status", "")

    if tool_name in ToolResultCache.WRITE_TOOLS:
        cache.invalidate_tool(tool_name)
        if tool_name == "execute_code":
            cache.clear()

    # Fail-loop guard
    if not result.get("success"):
        fail_counts[tool_name] = fail_counts.get(tool_name, 0) + 1
    else:
        fail_counts[tool_name] = 0

    v_status = verification.get("status", "")
    if v_status == "FAILED":
        verification["retry_directive"] = (
            "Verification FAILED \u2014 the action did not produce the expected "
            "outcome. Do NOT repeat the same approach. Try a different "
            "tool, a different path, or ask the user for clarification."
        )

    if not result.get("success") and tool_name != "read_pc_state" and pc_state_fn is not None:
        try:
            state = pc_state_fn()
            if state.get("success"):
                verification["state_snapshot"] = {
                    "focused_window": state.get("focused_window"),
                    "open_windows_count": len(state.get("windows", [])),
                    "running_processes_count": len(state.get("processes", [])),
                }
        except Exception:
            pass

    status = "ok" if result.get("success") else "error"
    return {
        "call_idx": call_idx,
        "call_id": f"call_{truncated_call_idx}",
        "status": status,
        "output_summary": _summarize_output(tool_name, result),
        **({} if result.get("success") else {"error": result.get("error", "unknown error")}),
    }


def _summarize_output(tool_name: str, result: dict) -> str:
    """Produce a short summary of a tool result for BATCH_TOOL_RESULT."""
    if not result.get("success"):
        return f"{tool_name} failed"
    content = result.get("output") or result.get("result") or result.get("content") or ""
    if isinstance(content, str):
        content = content[:500]
    elif isinstance(content, dict):
        content = json.dumps(content, default=str)[:120]
    return f"{tool_name}: {content}" if content else f"{tool_name} succeeded"


def _execute_batch_plan(
    plan: dict,
    execute_fn,
    verify_fn,
    user_input: str,
    cache,
    tool_log: list,
    fail_counts: dict,
    pc_state_fn,
    iteration: int,
) -> list[dict]:
    """Execute all calls in a BATCH_TOOL_PLAN. Returns list of result dicts."""
    mode, order = _execution_policy(plan)
    calls = plan["calls"]
    plan_id = plan["plan_id"]
    results: list[dict] = []

    _tool_log_lock = threading.Lock()
    _fail_lock = threading.Lock()

    def _run_one(call: dict) -> dict:
        with _tool_log_lock, _fail_lock:
            return _execute_single_call(
                call, execute_fn, verify_fn, user_input,
                cache, tool_log, fail_counts, pc_state_fn, iteration,
            )

    if mode == "parallel":
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls)) as pool:
            fut_map = {pool.submit(_run_one, c): c for c in calls}
            for fut in concurrent.futures.as_completed(fut_map):
                try:
                    results.append(fut.result())
                except Exception as e:
                    c = fut_map[fut]
                    results.append({
                        "call_idx": c["call_idx"],
                        "call_id": f"call_{c['call_idx']}",
                        "status": "error",
                        "error": str(e),
                    })
    else:
        abort = False
        for call_idx in order:
            if abort:
                results.append({
                    "call_idx": call_idx,
                    "call_id": f"call_{call_idx}",
                    "status": "skipped",
                    "error": "aborted by previous failure",
                })
                continue
            call = _call_by_idx(plan, call_idx)
            if call is None:
                results.append({
                    "call_idx": call_idx,
                    "call_id": f"call_{call_idx}",
                    "status": "error",
                    "error": f"call_idx {call_idx} not found in plan",
                })
                continue

            if call.get("risk_tier") == "high" and call.get("preexec_required"):
                results.append({
                    "call_idx": call_idx,
                    "call_id": f"call_{call_idx}",
                    "status": "pending_approval",
                    "error": "high-risk call requires approval before execution",
                })
                continue

            r = _run_one(call)
            results.append(r)
            if r["status"] != "ok" and plan.get("execution_policy") == "abort_on_fail":
                abort = True

    results.sort(key=lambda r: r.get("call_idx", 0))
    return results


def run(
    user_input: str,
    history: list[dict],
    execute_fn,
    verify_fn,
    mode: str = "interactive_cloud",
    tools: list = None,
    memory_context: str = "",
    valid_tool_names: set = None,
    pc_state_fn=None,
) -> dict:
    cache = get_cache()
    _tool_names = valid_tool_names or set()
    cap = ITERATION_CAPS.get(mode, 4)

    # System prompt only on first interaction — LLM retains role from there
    if not history:
        messages = [{"role": "system", "content": build_system_prompt()}]
    else:
        messages = []
    if memory_context:
        messages.append({"role": "system", "content": memory_context})
    messages.extend(history[-TOOL_LOOP_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_input})

    tool_log = []
    valid_tools = set()
    _fail_counts: dict[str, int] = {}  # persists across iterations for fail-loop guard

    for iteration in range(1, cap + 1):
        if len(json.dumps(messages)) > (MAX_CONTEXT_TOKENS * 4):
            messages = prune_history(messages)

        print("\r\U0001f914 Thinking...", end="", flush=True)

        # ── Dynamic temperature + reasoning effort ────────────────────────────
        # Iteration 1, chat input  → warm temp + low effort (fast, no tools needed)
        # Iteration 1, action input → cool temp + medium effort immediately.
        #   Rationale: effort="low" forces the cloud model to derive complex
        #   WinAPI/Python code from scratch through the 13k system prompt without
        #   structured reasoning chains — this is SLOWER for code tasks, not faster.
        #   Action detection is a cheap keyword scan, zero LLM calls.
        # Iteration 2  → always cool temp + medium effort (tool results are in context)
        # Iteration 3+ → maximally deterministic (deep in tool loop)
        if iteration == 1 and not tool_log:
            # Let the LLM decide: use moderate defaults that work for both
            # chat and tool tasks. The model's own reasoning determines
            # whether to call tools or respond directly.
            _temperature = 0.3
            _effort = "medium"
        elif iteration <= 2:
            _temperature = 0.2
            _effort = "medium"
        else:
            _temperature = 0.1   # deep in tool loop → maximize determinism
            _effort = "high"     # complex task → use full reasoning budget

        # ── Streaming control ─────────────────────────────────────────────────
        # Only stream chunks on chat-only requests (no tools suggested).  When
        # tools are available the LLM may generate raw XML / code-like text in
        # its first-pass reasoning which pollutes the terminal.  The reporter's
        # formatted output is what the user should see.
        _print_chunks = (iteration == 1 and not tools)

        try:
            try:
                llm_result = ollama_client.chat_stream(
                    messages=messages,
                    tools=get_pruned_schemas(tools or []),
                    temperature=_temperature,
                    reasoning_effort=_effort,
                    print_chunks=_print_chunks,
                )
            except (AttributeError, Exception) as _stream_err:
                logger.debug(
                    f"Streaming unavailable ({_stream_err}), using standard chat"
                )
                llm_result = ollama_client.chat(
                    messages=messages,
                    tools=get_pruned_schemas(tools or []),
                    temperature=_temperature,
                    reasoning_effort=_effort,
                )
        except ollama_client.OllamaError as e:
            logger.error(f"LLM error: {e}")
            return {
                "response": f"LLM unavailable: {e}",
                "tool_calls": tool_log,
                "iterations": iteration,
                "success": False,
                "error": str(e),
            }

        print("\r" + " " * 25 + "\r", end="", flush=True)
        content = llm_result.get("content", "")

        # ── Check for BATCH_TOOL_PLAN in text response ───────────────────────
        batch_plan, plan_err = parse_batch_plan(content, _tool_names)
        if batch_plan:
            messages.append({"role": "assistant", "content": content})
            batch_results = _execute_batch_plan(
                batch_plan, execute_fn, verify_fn, user_input,
                cache, tool_log, _fail_counts, pc_state_fn, iteration,
            )
            result_msg = format_batch_result(batch_plan["plan_id"], batch_results)
            # If any call failed, tell the LLM to retry differently
            has_failures = any(
                r.get("status") in ("error", "skipped") for r in batch_results
            )
            if has_failures:
                directive = (
                    f"The runtime executed your batch plan and returned:\n"
                    f"{result_msg}\n\n"
                    f"Some calls failed. Do NOT repeat the same approach — try a "
                    f"different tool, different parameters, or ask the user for "
                    f"clarification before retrying."
                )
            else:
                directive = (
                    f"The runtime executed your batch plan and returned:\n"
                    f"{result_msg}\n\n"
                    f"Please analyze these results and provide a clear summary "
                    f"to the user. Cite specific findings, errors, and suggested "
                    f"next steps."
                )
            messages.append({"role": "user", "content": directive})
            continue

        if plan_err:
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": (
                    f"Your BATCH_TOOL_PLAN could not be parsed: {plan_err}\n\n"
                    f"Fix the JSON syntax and output a corrected BATCH_TOOL_PLAN "
                    f"with validated parameters matching the tool schemas exactly."
                ),
            })
            continue

        # ── Fallback: native tool_calls (backward compat) ─────────────────────
        tool_calls = llm_result.get("tool_calls") or []

        if not tool_calls:
            return {
                "response": content or "Task complete.",
                "tool_calls": tool_log,
                "iterations": iteration,
                "success": True,
                "error": None,
            }

        valid_tools.update(tc["function"]["name"] for tc in tool_calls)
        is_valid, err = validate_tool_calls(tool_calls, _tool_names)
        if not is_valid:
            messages.append({"role": "assistant", "content": err})
            continue

        messages.append(
            {"role": "assistant", "content": content, "tool_calls": tool_calls}
        )

        tool_results = []
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            logger.info(f"Loop {iteration}: calling {name}")

            cached_result = cache.get(name, args)
            if cached_result is not None:
                logger.info(f"  \u2713 {name} (cached)")
                result = cached_result
                tool_log.append(
                    {"tool": name, "args": args, "result": result, "call_id": tc["id"], "cached": True}
                )
                verification = verify_fn(name, result, user_input)
            else:
                print(f"  \U0001f527 {name}...", end="", flush=True)
                result = execute_fn(name, args)
                ok_str = "\u2713" if result.get("success") else "\u2717"
                print(f"\r  \U0001f527 {name} {ok_str}" + " " * 10, flush=True)
                tool_log.append(
                    {"tool": name, "args": args, "result": result, "call_id": tc["id"], "cached": False}
                )
                cache.set(name, args, result)
                verification = verify_fn(name, result, user_input)

            if tool_log:
                tool_log[-1]["verification"] = verification.get("status", "")

            if name in ToolResultCache.WRITE_TOOLS:
                cache.invalidate_tool(name)
                if name == "execute_code":
                    cache.clear()

            if not result.get("success"):
                _fail_counts[name] = _fail_counts.get(name, 0) + 1
                if _fail_counts[name] >= 2:
                    stop_msg = (
                        f"FAIL-LOOP GUARD: '{name}' failed twice in a row "
                        f"({result.get('error', 'unknown error')}). "
                        f"STOP \u2014 do not retry. Notify the user."
                    )
                    logger.warning(stop_msg)
                    messages.append({"role": "user", "content": stop_msg})
                    continue
            else:
                _fail_counts[name] = 0

            safe_result = dict(result)

            v_status = verification.get("status", "")
            if v_status == "FAILED":
                verification["retry_directive"] = (
                    "Verification FAILED \u2014 the action did not produce the expected "
                    "outcome. Do NOT repeat the same approach. Try a different "
                    "tool, a different path, or ask the user for clarification."
                )

            if not result.get("success") and name != "read_pc_state" and pc_state_fn is not None:
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

        messages.extend(tool_results)

    logger.warning(f"Hit iteration cap ({cap})")
    result = {
        "response": "Task hit complexity limit. I've logged progress for review.",
        "tool_calls": tool_log,
        "iterations": cap,
        "success": False,
        "error": "ITERATION_CAP_EXCEEDED",
    }

    return result
