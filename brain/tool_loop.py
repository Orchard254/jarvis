"""
The ReAct tool-calling loop. Pure reasoning layer.
Executes tools via injected callbacks to maintain strict layer boundaries.

Supports two execution modes:
  1. Plan mode (default) — uses brain/planner.py to generate a structured plan,
     then executes steps in dependency order with parallel batching.
  2. ReAct mode (fallback) — the original iterative loop, used when planning
     fails or for chat-only responses.
"""

import json
import logging
import time as _time

from settings import (
    ITERATION_CAPS,
    MAX_CONTEXT_TOKENS,
    TOOL_LOOP_HISTORY_MESSAGES,
)
from verification.vision_summary import summarize_screen

from brain import ollama_client
from brain.context_manager import prune_history
from brain.prompt_builder import build_system_prompt, get_pruned_schemas
from brain.response_parser import validate_tool_calls
from brain.tool_result_cache import get_cache

logger = logging.getLogger(__name__)


# Temperature/effort is now determined by the LLM's own reasoning.
# No hardcoded keyword detection — the model decides whether a request
# is a chat response or a tool-calling task based on full context.


def _execute_step(
    step: dict,
    execute_fn,
    verify_fn,
    cache,
    tool_log: list,
    pc_state_fn,
    user_input: str,
):
    """Execute a single plan step and return the result."""
    name = step["tool"]
    args = step.get("args", {})

    cached_result = cache.get(name, args)
    if cached_result is not None:
        result = cached_result
        tool_log.append({"tool": name, "args": args, "result": result, "cached": True})
        verification = verify_fn(name, result, user_input)
    else:
        print(f"  [{name}]...", end="", flush=True)
        result = execute_fn(name, args)
        ok_str = "OK" if result.get("success") else "FAIL"
        print(f"\r  [{name}] {ok_str}" + " " * 10, flush=True)
        tool_log.append({"tool": name, "args": args, "result": result, "cached": False})
        cache.set(name, args, result)
        verification = verify_fn(name, result, user_input)

    # Attach verification
    if tool_log:
        tool_log[-1]["verification"] = verification.get("status", "")

    # Invalidate cache on writes
    from brain.tool_result_cache import ToolResultCache
    if name in ToolResultCache.WRITE_TOOLS:
        cache.invalidate_tool(name)

    # State snapshot on failure
    if not result.get("success") and name != "read_pc_state" and pc_state_fn is not None:
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

    return {"step": step, "result": result, "verification": verification}



def run_with_plan(
    plan: dict,
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
    """Execute a pre-generated plan with parallel DAG execution.

    Steps with explicit batch_with dependencies run in dependency order;
    independent steps (empty batch_with) run in parallel via ThreadPoolExecutor.
    Falls back to ReAct (cap 4) if any step fails.
    """
    cache = get_cache()
    steps = plan.get("steps", [])
    tool_log = []
    _valid_tool_names = valid_tool_names or set()

    plan_summary = "; ".join(f"{s['tool']}({list(s.get('args', {}).keys())})" for s in steps)
    logger.info(f"Plan execution: {len(steps)} steps [{plan_summary}]")

    all_succeeded = True
    failed_step = None

    for step_idx, step in enumerate(steps):
        name = step["tool"]
        if name not in _valid_tool_names:
            logger.warning(f"Unknown tool '{name}' — aborting plan")
            all_succeeded = False
            failed_step = step
            break

        step_result = _execute_step(
            step, execute_fn, verify_fn, cache,
            tool_log, pc_state_fn, user_input,
        )

        if not step_result["result"].get("success"):
            all_succeeded = False
            failed_step = step
            logger.warning(
                f"Plan step {step_idx} failed: {name} "
                f"({step_result['result'].get('error', 'unknown')})"
            )
            break

    if all_succeeded:
        return {
            "success": True,
            "tool_calls": tool_log,
            "iterations": len(steps),
            "error": None,
            "plan_executed": True,
        }

    logger.info("Plan execution failed — falling back to ReAct loop for recovery")
    plan_history = list(history)
    plan_history.append({"role": "user", "content": user_input})

    # Inject completed plan steps as proper assistant+tool messages so the
    # ReAct LLM knows what already ran and doesn't duplicate work.
    if tool_log:
        synthetic_calls = []
        for i, tl in enumerate(tool_log):
            name = tl.get("tool", "")
            args = tl.get("args", {})
            call_id = f"plan_{i}"
            synthetic_calls.append({
                "function": {"name": name, "arguments": args},
                "id": call_id,
            })
        if synthetic_calls:
            plan_history.append({
                "role": "assistant",
                "content": "I'll execute the planned steps.",
                "tool_calls": synthetic_calls,
            })
        for i, tl in enumerate(tool_log):
            name = tl.get("tool", "")
            result = tl.get("result", {})
            call_id = f"plan_{i}"

            verification = verify_fn(name, result, user_input)
            v = verification.copy() if isinstance(verification, dict) else {}
            v.pop("method", None)
            tool_feedback = {"tool_name": name, "result": result}
            if v.get("status") not in (None, "CONFIRMED"):
                tool_feedback["verification"] = v

            plan_history.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(tool_feedback, default=str),
            })

    fail_context = (
        f"The plan failed at step '{failed_step['tool']}'. "
        f"The original request is: {user_input}. "
        f"Complete the remaining task."
    )

    return run(
        user_input=fail_context,
        history=plan_history,
        execute_fn=execute_fn,
        verify_fn=verify_fn,
        mode=mode,
        tools=tools,
        memory_context=memory_context,
        valid_tool_names=_valid_tool_names,
        pc_state_fn=pc_state_fn,
        fallback_cap=4,
    )


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
    plan: dict = None,
    fallback_cap: int = None,
) -> dict:
    cache = get_cache()
    _tool_names = valid_tool_names or set()
    cap = fallback_cap if fallback_cap is not None else ITERATION_CAPS.get(mode, 4)
    messages = [{"role": "system", "content": build_system_prompt()}]
    if memory_context:
        messages.append({"role": "system", "content": memory_context})
    messages.extend(history[-TOOL_LOOP_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_input})

    # ── Plan mode: execute pre-generated plan with parallel batching ─────────
    if plan and plan.get("steps"):
        plan_result = run_with_plan(
            plan=plan,
            user_input=user_input,
            history=history,
            execute_fn=execute_fn,
            verify_fn=verify_fn,
            mode=mode,
            tools=tools,
            memory_context=memory_context,
            valid_tool_names=valid_tool_names,
            pc_state_fn=pc_state_fn,
        )
        if not plan_result.get("success"):
            return plan_result
        # Plan succeeded — inject tool results as proper assistant+tool messages
        tool_log = plan_result.get("tool_calls", [])
        if tool_log:
            synthetic_calls = []
            for i, tl in enumerate(tool_log):
                name = tl.get("tool", "")
                args = tl.get("args", {})
                call_id = f"plan_{i}"
                tl["call_id"] = call_id
                synthetic_calls.append({
                    "function": {"name": name, "arguments": args},
                    "id": call_id,
                })

            if synthetic_calls:
                messages.append({
                    "role": "assistant",
                    "content": "I'll execute the planned steps.",
                    "tool_calls": synthetic_calls,
                })

            for tl in tool_log:
                name = tl.get("tool", "")
                args = tl.get("args", {})
                call_id = tl.get("call_id", "")
                result = tl.get("result", {})

                safe_result = dict(result)
                if (name == "capture_screen" or (name == "screen" and args.get("action") == "capture")) and safe_result.get("image_b64"):
                    try:
                        vision_text = summarize_screen(safe_result["image_b64"], user_input)
                        safe_result = {
                            "success": safe_result.get("success", True),
                            "width": safe_result.get("width"),
                            "height": safe_result.get("height"),
                            "vision_description": vision_text,
                        }
                    except Exception:
                        safe_result.pop("image_b64", None)
                        safe_result["vision_description"] = "(screenshot taken, description unavailable)"

                verification = verify_fn(name, safe_result, user_input)
                v = verification.copy() if isinstance(verification, dict) else {}
                v.pop("method", None)
                tool_feedback = {"tool_name": name, "result": safe_result}
                if v.get("status") not in (None, "CONFIRMED"):
                    tool_feedback["verification"] = v

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(tool_feedback, default=str),
                })
    else:
        tool_log = []
    valid_tools = set()
    _circuit: dict[str, dict] = {}  # circuit breaker state per tool
    _loop_aborted = False

    for iteration in range(1, cap + 1):
        if _loop_aborted:
            break
        if len(json.dumps(messages)) > (MAX_CONTEXT_TOKENS * 3):
            messages = prune_history(messages)

        print("\r[thinking]...", end="", flush=True)

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
        tool_calls = llm_result.get("tool_calls") or []

        # ── Early completion: if LLM responded with text (no tools), we're done ──
        if not tool_calls:
            return {
                "response": content or "Task complete.",
                "tool_calls": tool_log,
                "iterations": iteration,
                "success": True,
                "error": None,
            }

        valid_tools.update(tc["function"]["name"] for tc in tool_calls)
        # Validate against ALL registered tools. Schema pruning (when enabled)
        # must never imply only those tools exist — the model may call any name
        # that appears in TOOL_REGISTRY.
        is_valid, err = validate_tool_calls(tool_calls, _tool_names)
        if not is_valid:
            messages.append({"role": "assistant", "content": err})
            continue

        # Deduplicate identical tool calls — LLM sometimes outputs duplicates
        seen: set[str] = set()
        unique_calls: list[dict] = []
        for tc in tool_calls:
            key = json.dumps(tc, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                unique_calls.append(tc)
        if len(unique_calls) < len(tool_calls):
            logger.warning(f"Deduplicated {len(tool_calls) - len(unique_calls)} duplicate tool call(s)")
            tool_calls = unique_calls

        messages.append(
            {"role": "assistant", "content": content, "tool_calls": tool_calls}
        )

        tool_results = []
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            logger.info(f"Loop {iteration}: calling {name}")

            # ── Check cache for read-only tools ────────────────────────────────
            cached_result = cache.get(name, args)
            if cached_result is not None:
                logger.info(f"  ✓ {name} (cached)")
                result = cached_result
                # Mark as cached in tool log for transparency
                tool_log.append(
                    {"tool": name, "args": args, "result": result, "call_id": tc["id"], "cached": True}
                )
                verification = verify_fn(name, result, user_input)
                # Proceed to add to tool_results below
            else:
                print(f"  [{name}]...", end="", flush=True)
                result = execute_fn(name, args)
                ok_str = "OK" if result.get("success") else "FAIL"
                print(f"\r  [{name}] {ok_str}" + " " * 10, flush=True)
                tool_log.append(
                    {"tool": name, "args": args, "result": result, "call_id": tc["id"], "cached": False}
                )

                # Cache successful read-only tool results
                cache.set(name, args, result)

                verification = verify_fn(name, result, user_input)

            # Attach verification status to the tool log entry
            if tool_log:
                tool_log[-1]["verification"] = verification.get("status", "")

            # Invalidate cache on write operations
            from brain.tool_result_cache import ToolResultCache
            if name in ToolResultCache.WRITE_TOOLS:
                cache.invalidate_tool(name)
                # Also invalidate related read caches
                if name in ("write_file", "file_ops"):
                    path = args.get("path")
                    if path:
                        cache.invalidate_pattern("read_file", path=path)
                elif name == "execute_code" or (name == "exec" and args.get("action", "run") == "run"):
                    cache.clear()

            # ── Circuit breaker: track failures with time-based cooldown ─────
            now = _time.time()
            if name not in _circuit:
                _circuit[name] = {"failures": 0, "last_fail": 0.0, "state": "closed"}
            cb = _circuit[name]

            if cb["state"] == "open":
                if now - cb["last_fail"] >= 60.0:
                    cb["state"] = "half_open"
                    logger.info(f"Circuit {name}: OPEN → HALF_OPEN (cooldown expired)")
                else:
                    stop_msg = (
                        f"CIRCUIT OPEN: '{name}' is in cooldown after {cb['failures']} failures. "
                        f"STOP — do not retry. Notify the user."
                    )
                    logger.warning(stop_msg)
                    messages.append({"role": "user", "content": stop_msg})
                    _loop_aborted = True
                    break

            if not result.get("success"):
                cb["failures"] += 1
                cb["last_fail"] = now
                if cb["state"] == "half_open" or cb["failures"] >= 2:
                    cb["state"] = "open"
                    stop_msg = (
                        f"CIRCUIT OPEN: '{name}' failed ({cb['failures']} consecutive). "
                        f"STOP — do not retry. Notify the user."
                    )
                    logger.warning(stop_msg)
                    messages.append({"role": "user", "content": stop_msg})
                    _loop_aborted = True
                    break
            else:
                cb["failures"] = 0
                if cb["state"] == "half_open":
                    cb["state"] = "closed"
                    logger.info(f"Circuit {name}: HALF_OPEN → CLOSED (recovered)")

            # ── Vision: swap raw base64 for a text description ────────────────
            # The main text LLM cannot process raw base64 image data — it just
            # sees thousands of characters of noise, wasting tokens and giving
            # it no visual information. We call the vision model here to convert
            # the screenshot into a plain-text description before feeding it
            # back to the main LLM in the next iteration.
            safe_result = dict(result)
            if (name == "capture_screen" or (name == "screen" and args.get("action") == "capture")) and safe_result.get("image_b64"):
                try:
                    vision_text = summarize_screen(safe_result["image_b64"], user_input)
                    # Replace the base64 blob with the human-readable description
                    safe_result = {
                        "success": safe_result.get("success", True),
                        "width": safe_result.get("width"),
                        "height": safe_result.get("height"),
                        "vision_description": vision_text,
                    }
                    logger.info(
                        f"tool_loop: screenshot converted to vision summary "
                        f"({len(vision_text)} chars)"
                    )
                except Exception as ve:
                    logger.warning(f"tool_loop: vision summary failed — {ve}")
                    # Strip base64 even on failure to avoid token waste
                    safe_result.pop("image_b64", None)
                    safe_result["vision_description"] = (
                        "(screenshot taken, description unavailable)"
                    )

            # ── Verification retry hint ───────────────────────────────────────
            # When verification explicitly FAILS, inject a clear directive so
            # the LLM knows to try a different approach, not repeat the same one.
            v_status = verification.get("status", "")
            if v_status == "FAILED":
                verification["retry_directive"] = (
                    "Verification FAILED — the action did not produce the expected "
                    "outcome. Do NOT repeat the same approach. Try a different "
                    "tool, a different path, or ask the user for clarification."
                )
            
            # ── Pre-execution state snapshot for failed tools ─────────────────
            # When a tool fails, include a snapshot of current PC state to help
            # the LLM diagnose what went wrong and choose a better approach.
            if not result.get("success") and name not in ("read_pc_state", "system") and pc_state_fn is not None:
                try:
                    state_snapshot = pc_state_fn()
                    if state_snapshot.get("success"):
                        verification["state_snapshot"] = {
                            "focused_window": state_snapshot.get("focused_window"),
                            "open_windows_count": len(state_snapshot.get("windows", [])),
                            "running_processes_count": len(state_snapshot.get("processes", [])),
                        }
                except Exception:
                    pass  # State snapshot unavailable — continue without it

            # Omit redundant CONFIRmed verification — the LLM already sees
            # success=True. Only send verification when it has useful info.
            v = verification.copy() if isinstance(verification, dict) else {}
            v.pop("method", None)
            tool_feedback: dict = {"tool_name": name, "result": safe_result}
            if v.get("status") not in (None, "CONFIRMED"):
                tool_feedback["verification"] = v
            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(tool_feedback, default=str),
                }
            )

        messages.extend(tool_results)

    if _loop_aborted:
        return {
            "response": "A tool failed repeatedly. I've stopped to avoid compounding the issue.",
            "tool_calls": tool_log,
            "iterations": cap,
            "success": False,
            "error": "FAIL_LOOP_GUARD",
        }

    logger.warning(f"Hit iteration cap ({cap})")
    return {
        "response": "Task hit complexity limit. I've logged progress for review.",
        "tool_calls": tool_log,
        "iterations": cap,
        "success": False,
        "error": "ITERATION_CAP_EXCEEDED",
    }
