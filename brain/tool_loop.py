"""
The ReAct tool-calling loop. Pure reasoning layer.
Executes tools via injected callbacks to maintain strict layer boundaries.
"""

import json
import logging

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


def run(
    user_input: str,
    history: list[dict],
    execute_fn,
    verify_fn,
    mode: str = "interactive_cloud",
    tools: list = None,
    memory_context: str = "",
    recovery=None,  # optional RecoveryManager instance
) -> dict:
    from tools import TOOL_REGISTRY as _tool_registry

    cache = get_cache()
    cap = ITERATION_CAPS.get(mode, 4)
    messages = [{"role": "system", "content": build_system_prompt()}]
    if memory_context:
        messages.append({"role": "system", "content": memory_context})
    messages.extend(history[-TOOL_LOOP_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_input})

    tool_log = []
    valid_tools = set()
    failed_attempts_summary = []  # Track failed attempts for LLM context

    for iteration in range(1, cap + 1):
        if len(json.dumps(messages)) > (MAX_CONTEXT_TOKENS * 4):
            messages = prune_history(messages)

        # ── Inject failed attempts summary at start of each iteration ───────────
        # This ensures the LLM always sees what has failed before making decisions.
        # We inject it fresh each iteration so pruning doesn't lose this critical context.
        if failed_attempts_summary:
            # Remove any previous summary injection to avoid duplicates
            messages = [m for m in messages if not m.get("content", "").startswith("Previous failed attempts")]
            
            summary_lines = ["Previous failed attempts (do NOT repeat these exact approaches):"]
            for i, attempt in enumerate(failed_attempts_summary[-5:], 1):  # Last 5 failures
                summary_lines.append(
                    f"  {i}. {attempt['tool']}(args={attempt['args']}) → {attempt['error']}"
                )
            summary_lines.append("")
            summary_lines.append("Analyze why these failed and choose a DIFFERENT approach.")
            summary_text = "\n".join(summary_lines)
            messages.append({"role": "system", "content": summary_text})

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
        # Only stream chunks on iteration 1 (may be a chat response the user
        # reads in real time).  On iterations 2+ the LLM generates a completion
        # summary based on what it *expected* to happen — which can differ from
        # the tool's actual stdout.  Suppressing those chunks means the user
        # never sees the inaccurate narration; the reporter's stdout-sourced
        # response is what appears in the final JARVIS: line instead.
        _print_chunks = (iteration == 1)

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

        if not tool_calls:
            result = {
                "response": content or "Task complete.",
                "tool_calls": tool_log,
                "iterations": iteration,
                "success": True,
                "error": None,
            }

            # Auto-promote candidate skills after SKILL_PROMOTION_RUNS successes
            if result.get("success"):
                for entry in tool_log:
                    if entry.get("tool") == "execute_code":
                        from skills.skill_store import (
                            get_candidate_by_intent,
                            promote_skill,
                        )

                        tool_result = entry.get("result", {})
                        if tool_result.get("success"):
                            # search_by_intent only returns *active* skills, so
                            # use get_candidate_by_intent to find pending candidates
                            candidate = get_candidate_by_intent(user_input)
                            from settings import SKILL_PROMOTION_RUNS

                            if (
                                candidate
                                and candidate.get("run_count", 0)
                                >= SKILL_PROMOTION_RUNS
                            ):
                                promote_skill(candidate["skill_id"])
                                logger.info(
                                    f"🎯 Skill promoted: {candidate['skill_id'][:8]}"
                                )

            return result

        valid_tools.update(tc["function"]["name"] for tc in tool_calls)
        # Validate against ALL registered tools. Schema pruning (when enabled)
        # must never imply only those tools exist — the model may call any name
        # that appears in TOOL_REGISTRY.
        is_valid, err = validate_tool_calls(tool_calls, set(_tool_registry.keys()))
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
                print(f"  \U0001f527 {name}...", end="", flush=True)
                result = execute_fn(name, args)
                ok_str = "\u2713" if result.get("success") else "\u2717"
                print(f"\r  \U0001f527 {name} {ok_str}" + " " * 10, flush=True)
                tool_log.append(
                    {"tool": name, "args": args, "result": result, "call_id": tc["id"], "cached": False}
                )

                # Inform recovery manager of outcome so circuit breakers stay accurate
                if recovery is not None:
                    if result.get("success"):
                        recovery.record_success(name)

                # Cache successful read-only tool results
                cache.set(name, args, result)

                verification = verify_fn(name, result, user_input)

            # Invalidate cache on write operations
            from brain.tool_result_cache import ToolResultCache
            if name in ToolResultCache.WRITE_TOOLS:
                cache.invalidate_tool(name)
                # Also invalidate related read caches
                if name in ("write_file", "file_ops"):
                    path = args.get("path")
                    if path:
                        cache.invalidate_pattern("read_file", path=path)
                elif name == "execute_code":
                    # execute_code can mutate any file or system state, so the
                    # entire cache must be cleared. invalidate_pattern("*") was
                    # a no-op — it only removes entries whose tool_name == "*",
                    # which is never set. cache.clear() is the correct call.
                    cache.clear()

            # Recovery cap check — stop if the tool keeps failing
            if recovery is not None and not result.get("success"):
                error_msg = result.get("error", "unknown error")
                # should_retry returns (bool, float) — unpack both values.
                # Treating the tuple directly as a bool is always True (non-empty
                # tuple), which silently disabled the recovery cap entirely.
                should_continue, _backoff_delay = recovery.should_retry(name, error_msg)
                if not should_continue:
                    logger.warning(
                        f"tool_loop: recovery cap hit for {name} — stopping loop"
                    )
                    return {
                        "response": (
                            f"I've tried {name} multiple times without success. "
                            f"{error_msg}"
                        ),
                        "tool_calls": tool_log,
                        "iterations": iteration,
                        "success": False,
                        "error": f"RECOVERY_CAP: {error_msg}",
                    }

            # ── Vision: swap raw base64 for a text description ────────────────
            # The main text LLM cannot process raw base64 image data — it just
            # sees thousands of characters of noise, wasting tokens and giving
            # it no visual information. We call the vision model here to convert
            # the screenshot into a plain-text description before feeding it
            # back to the main LLM in the next iteration.
            safe_result = dict(result)
            if name == "capture_screen" and safe_result.get("image_b64"):
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
            if not result.get("success") and name != "read_pc_state":
                try:
                    from tools.read_pc_state import read_pc_state as _rps
                    state_snapshot = _rps()
                    if state_snapshot.get("success"):
                        verification["state_snapshot"] = {
                            "focused_window": state_snapshot.get("focused_window"),
                            "open_windows_count": len(state_snapshot.get("windows", [])),
                            "running_processes_count": len(state_snapshot.get("processes", [])),
                        }
                except Exception:
                    pass  # State snapshot unavailable — continue without it
                
                # Track this failure for summary injection in next iteration
                failed_attempts_summary.append({
                    "tool": name,
                    "args": args,
                    "error": result.get("error", "unknown error")[:150],
                    "iteration": iteration,
                })

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
