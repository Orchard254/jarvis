"""
Jarvis agent — conversation, reasoning, memory context, high-level planning.
Delegates all tool execution to agents.execution.
"""

from __future__ import annotations

import json
import logging
from typing import Callable

from settings import ITERATION_CAPS, MAX_CONTEXT_TOKENS, TOOL_LOOP_HISTORY_MESSAGES
from brain import ollama_client
from brain.context_manager import prune_history
from brain.prompt_builder import build_system_prompt, build_state_context, get_pruned_schemas
from brain.response_parser import parse_batch_plan, validate_tool_calls
from brain.structured_log import (
    loop_complete as _log_complete,
    loop_iteration as _log_iteration,
)
from brain.tool_result_cache import get_cache
from agents.execution import run_native_tool_calls, run_plan

logger = logging.getLogger(__name__)


def _build_auto_memory_context(user_input: str) -> str:
    """
    Automatically surface relevant memories for the current user request.

    Pulls:
      - All stored semantic preferences (what the user has told FRIDAY explicitly)
      - Recent episodic episodes that share keywords with the user's request

    Returns a compact system-message block, or "" if nothing relevant found.
    This runs on every turn so FRIDAY always "knows" the user without being asked.
    """
    lines: list[str] = []

    # ── Semantic preferences ────────────────────────────────────────────────
    try:
        from memory import semantic
        prefs = semantic.get_all()
        if prefs:
            pref_lines = []
            for key, value in list(prefs.items())[:20]:  # cap at 20 to save tokens
                if key.startswith("insight:"):
                    continue  # handled separately
                pref_lines.append(f"  • {key}: {str(value)[:120]}")
            if pref_lines:
                lines.append("## What I know about the user")
                lines.extend(pref_lines)
    except Exception as e:
        logger.debug(f"auto_memory: semantic fetch failed — {e}")

    # ── Episodic search — find past episodes relevant to this request ───────
    try:
        from memory import episodic
        # Extract keywords: non-trivial words from user input
        stop_words = {"the", "a", "an", "is", "it", "in", "of", "to", "and",
                      "or", "my", "me", "i", "you", "what", "how", "can", "do",
                      "please", "hey", "friday", "jarvis"}
        keywords = [
            w.lower().strip(".,?!;:'\"")
            for w in user_input.split()
            if len(w) > 3 and w.lower() not in stop_words
        ]

        if keywords:
            # Search by each keyword and collect unique episodes
            seen_ids: set = set()
            relevant_episodes: list[dict] = []
            for kw in keywords[:5]:  # limit to 5 keywords
                try:
                    results = episodic.search(kw, limit=3)
                    for ep in results or []:
                        ep_id = ep.get("id") or id(ep)
                        if ep_id not in seen_ids:
                            seen_ids.add(ep_id)
                            relevant_episodes.append(ep)
                except Exception:
                    pass

            if relevant_episodes:
                lines.append("\n## Relevant past episodes")
                for ep in relevant_episodes[:5]:
                    cmd = ep.get("command_text", "")[:80]
                    result = ep.get("tool_result", "")
                    if isinstance(result, str):
                        result = result[:100]
                    ok = "✓" if ep.get("success") else "✗"
                    lines.append(f"  {ok} {cmd}")
                    if result:
                        lines.append(f"    → {result}")
    except Exception as e:
        logger.debug(f"auto_memory: episodic search failed — {e}")

    if not lines:
        return ""

    return "\n".join(lines)


def _directive_for_plan_result(
    result_msg: str,
    deferred: list[dict],
    has_failures: bool,
    validation_errors: list[dict],
) -> str:
    if validation_errors:
        return (
            f"Execution could not run the plan:\n{result_msg}\n\n"
            "Fix parameters and output a corrected BATCH_TOOL_PLAN."
        )
    if deferred:
        tools = ", ".join(c["tool"] for c in deferred)
        return (
            f"The execution agent ran your plan and returned:\n{result_msg}\n\n"
            f"Interaction tool(s) ({tools}) were deferred — perception must finish first. "
            "Analyze the perception output, then issue a new BATCH_TOOL_PLAN with "
            "only the interaction call(s) and correct coordinates."
        )
    if has_failures:
        return (
            f"The execution agent ran your plan and returned:\n{result_msg}\n\n"
            "Some calls failed after internal retries. Try a different tool, "
            "different parameters, or ask the user for clarification."
        )
    return (
        f"The execution agent ran your plan and returned:\n{result_msg}\n\n"
        "Summarize results for the user. Cite specific findings, errors, and next steps."
    )


def run(
    user_input: str,
    history: list[dict],
    execute_fn: Callable,
    verify_fn: Callable,
    mode: str = "interactive_cloud",
    tools: list = None,
    memory_context: str = "",
    valid_tool_names: set = None,
    pc_state_fn=None,
    state_snapshot_fn=None,
    attach_tool_schemas: bool = False,
) -> dict:
    """
    Jarvis planning loop. Same signature as legacy brain.tool_loop.run for orchestrator/tests.

    ``attach_tool_schemas``: when False (default), Jarvis uses BATCH_TOOL_PLAN in text only;
    full OpenAI tool schemas are not sent (catalog remains in the system prompt).
    """
    cache = get_cache()
    _tool_names = valid_tool_names or set()
    cap = ITERATION_CAPS.get(mode, 4)

    messages = [{"role": "system", "content": build_system_prompt()}]

    # Auto-recall: surface relevant memories without the user having to ask.
    # Merges orchestrator-provided memory_context with auto-recalled content.
    auto_mem = _build_auto_memory_context(user_input)
    combined_memory = "\n\n".join(filter(None, [memory_context, auto_mem]))
    if combined_memory:
        messages.append({"role": "system", "content": combined_memory})
    messages.extend(history[-TOOL_LOOP_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_input})

    tool_log = []
    _fail_counts: dict[str, int] = {}
    llm_tools = get_pruned_schemas(tools or []) if attach_tool_schemas else []

    for iteration in range(1, cap + 1):
        if len(json.dumps(messages)) > (MAX_CONTEXT_TOKENS * 4):
            messages = prune_history(messages)

        if state_snapshot_fn:
            state = state_snapshot_fn()
            state_block = build_state_context(state)
            if state_block:
                prefix = "## Live State\n"
                found = False
                for m in messages:
                    if m.get("role") == "system" and m.get("content", "").startswith(prefix):
                        m["content"] = f"{prefix}{state_block}"
                        found = True
                        break
                if not found:
                    messages.append({"role": "system", "content": f"{prefix}{state_block}"})

        print("\r🤔 Thinking...", end="", flush=True)

        if iteration == 1 and not tool_log:
            _temperature, _effort = 0.3, "medium"
        elif iteration <= 2:
            _temperature, _effort = 0.2, "medium"
        else:
            _temperature, _effort = 0.1, "high"

        _print_chunks = iteration == 1 and not llm_tools

        import time

        _llm_t0 = time.time()
        try:
            try:
                llm_result = ollama_client.chat_stream(
                    messages=messages,
                    tools=llm_tools,
                    temperature=_temperature,
                    reasoning_effort=_effort,
                    print_chunks=_print_chunks,
                )
            except (AttributeError, Exception) as stream_err:
                logger.debug(f"Streaming unavailable ({stream_err}), using chat")
                llm_result = ollama_client.chat(
                    messages=messages,
                    tools=llm_tools,
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
        _llm_latency = (time.time() - _llm_t0) * 1000
        _tool_count_before = len(tool_log)

        if content:
            logger.info(f"Jarvis content (first 300): {content[:300]}")
        if llm_result.get("tool_calls"):
            for tc in llm_result.get("tool_calls") or []:
                fn = tc.get("function", {})
                logger.info(
                    f"Jarvis native tool_call: {fn.get('name')} "
                    f"args={json.dumps(fn.get('arguments', {}))}"
                )
        else:
            logger.info("Jarvis response: no native tool_calls")

        batch_plan, plan_err = parse_batch_plan(content, _tool_names)
        if batch_plan:
            logger.info(
                f"BATCH_TOOL_PLAN: {json.dumps(batch_plan, default=str)[:500]}"
            )
            messages.append({"role": "assistant", "content": content})

            plan_result = run_plan(
                batch_plan,
                execute_fn,
                verify_fn,
                user_input,
                cache,
                tool_log,
                _fail_counts,
                pc_state_fn,
                iteration,
            )

            directive = _directive_for_plan_result(
                plan_result.result_msg,
                plan_result.deferred_calls,
                plan_result.has_failures,
                plan_result.validation_errors,
            )
            messages.append({"role": "user", "content": directive})
            _tool_count = len(tool_log) - _tool_count_before
            _log_iteration(
                iteration, _llm_latency, _tool_count, not plan_result.has_failures
            )
            continue

        if plan_err:
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your BATCH_TOOL_PLAN could not be parsed: {plan_err}\n\n"
                        "Fix the JSON and output a corrected BATCH_TOOL_PLAN."
                    ),
                }
            )
            continue

        tool_calls = llm_result.get("tool_calls") or []
        if not tool_calls:
            _tool_count = len(tool_log) - _tool_count_before
            _log_iteration(iteration, _llm_latency, _tool_count, True)
            _log_complete(iteration, len(tool_log), True)
            return {
                "response": content or "Task complete.",
                "tool_calls": tool_log,
                "iterations": iteration,
                "success": True,
                "error": None,
            }

        is_valid, err = validate_tool_calls(tool_calls, _tool_names)
        if not is_valid:
            messages.append({"role": "assistant", "content": err})
            continue

        messages.append(
            {"role": "assistant", "content": content, "tool_calls": tool_calls}
        )

        tool_results, stop_loop = run_native_tool_calls(
            tool_calls,
            content,
            execute_fn,
            verify_fn,
            user_input,
            cache,
            tool_log,
            _fail_counts,
            pc_state_fn,
            iteration,
        )

        if stop_loop:
            last = tool_log[-1] if tool_log else {}
            name = last.get("tool", "tool")
            stop_msg = (
                f"FAIL-LOOP GUARD: '{name}' failed twice in a row. "
                "STOP — notify the user."
            )
            messages.append({"role": "user", "content": stop_msg})
            _tool_count = len(tool_log) - _tool_count_before
            _log_iteration(iteration, _llm_latency, _tool_count, False)
            continue

        messages.extend(tool_results)
        _tool_count = len(tool_log) - _tool_count_before
        _log_iteration(iteration, _llm_latency, _tool_count, True)

    logger.warning(f"Jarvis hit iteration cap ({cap})")
    _log_complete(cap, len(tool_log), False, "ITERATION_CAP_EXCEEDED")
    return {
        "response": "Task hit complexity limit. I've logged progress for review.",
        "tool_calls": tool_log,
        "iterations": cap,
        "success": False,
        "error": "ITERATION_CAP_EXCEEDED",
    }
