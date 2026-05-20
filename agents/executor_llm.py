import json
import logging
from dataclasses import dataclass
from typing import Callable

from brain import ollama_client
from brain.executor_prompt import build_executor_prompt
from settings import llm as llm_settings

logger = logging.getLogger(__name__)

MAX_CALL_RETRIES = 2

@dataclass
class ExecutorDecision:
    action: str        # PASS, PASS_WITH, RETRY, RETRY_WITH, ABORT
    params: dict | None = None
    reason: str = ""


def _build_call_context(call: dict, plan: dict) -> dict:
    return {
        "tool": call["tool"],
        "params": call.get("params", {}),
        "call_idx": call["call_idx"],
    }


def _build_result_summary(result: dict) -> dict:
    return {
        "call_idx": result.get("call_idx"),
        "status": result.get("status"),
        "success": result.get("success"),
        "output_summary": result.get("output_summary", ""),
        "error": result.get("error", ""),
        "tool": result.get("tool", ""),
    }


def _ask_executor_llm(
    call: dict,
    previous_result: dict | None,
    plan: dict,
) -> ExecutorDecision:
    try:
        prompt = build_executor_prompt()
    except Exception as e:
        logger.warning(f"Executor prompt build failed: {e}")
        return ExecutorDecision("PASS")

    context = {
        "CURRENT_CALL": _build_call_context(call, plan),
        "PREVIOUS_RESULT": _build_result_summary(previous_result) if previous_result else "none",
        "PLAN": {
            "plan_id": plan.get("plan_id", "unknown"),
            "total_calls": len(plan.get("calls", [])),
        },
    }

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(context, indent=2)},
    ]

    for attempt in range(2):
        try:
            llm_result = ollama_client.chat(
                messages=messages,
                model=llm_settings.EXECUTOR_MODEL,
                temperature=0.1,
                max_retries=1,
                timeout=5,
            )
            content = (llm_result.get("content", "") or "").strip()
            decision = _parse_decision(content, call)
            if decision:
                return decision
        except Exception as e:
            logger.warning(f"Executor LLM call failed (attempt {attempt+1}): {e}")

    return ExecutorDecision("PASS")


def _parse_decision(content: str, call: dict) -> ExecutorDecision | None:
    if not content:
        return None
    upper = content.upper()

    if upper.startswith("ABORT"):
        reason = content[len("ABORT"):].strip().strip("\"'")
        return ExecutorDecision("ABORT", reason=reason or "executor aborted")

    if upper.startswith("RETRY_WITH"):
        json_part = content[len("RETRY_WITH"):].strip()
        params = _try_extract_json(json_part)
        if params is not None:
            return ExecutorDecision("RETRY_WITH", params=params)
        return ExecutorDecision("RETRY_WITH", params=call.get("params", {}))

    if upper.startswith("RETRY"):
        return ExecutorDecision("RETRY")

    if upper.startswith("PASS_WITH"):
        json_part = content[len("PASS_WITH"):].strip()
        params = _try_extract_json(json_part)
        if params is not None:
            return ExecutorDecision("PASS_WITH", params=params)
        return ExecutorDecision("PASS_WITH", params=call.get("params", {}))

    if upper.startswith("PASS"):
        return ExecutorDecision("PASS")

    return None


def _try_extract_json(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            if "params" in parsed:
                return parsed["params"]
            return parsed
    except json.JSONDecodeError:
        pass
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
        if isinstance(parsed, dict):
            if "params" in parsed:
                return parsed["params"]
            return parsed
    except (ValueError, json.JSONDecodeError):
        pass
    return None


def _build_skipped(call: dict, reason: str) -> dict:
    return {
        "call_idx": call["call_idx"],
        "call_id": f"call_{call['call_idx']}",
        "status": "skipped",
        "error": reason,
    }


from agents.execution import (
    _execute_single_call,
    _summarize_output,
    validate_tool_call,
    format_batch_result,
)


def execute_plan_with_llm(
    plan: dict,
    execute_fn: Callable,
    verify_fn: Callable,
    user_input: str,
    cache,
    tool_log: list,
    fail_counts: dict,
    pc_state_fn,
    iteration: int,
) -> tuple[list[dict], bool]:
    """Execute plan one call at a time with LLM verification between each step."""
    calls = plan.get("calls", [])
    results = []
    previous_result = None
    i = 0
    aborted = False

    while i < len(calls) and not aborted:
        call = calls[i]
        succeeded = False

        for attempt in range(1, MAX_CALL_RETRIES + 1):
            decision = _ask_executor_llm(call, previous_result, plan)

            if decision.action == "ABORT":
                logger.info(f"Executor ABORT at call_idx={call['call_idx']}: {decision.reason}")
                for j in range(i, len(calls)):
                    results.append(_build_skipped(calls[j], decision.reason))
                aborted = True
                break

            if decision.action in ("RETRY", "RETRY_WITH"):
                adjusted_call = {**call, "params": decision.params or call.get("params", {})}
            else:
                adjusted_call = {**call, "params": decision.params or call.get("params", {})}

            logger.info(
                f"Executor: call_idx={adjusted_call['call_idx']} "
                f"tool={adjusted_call['tool']} "
                f"decision={decision.action} "
                f"attempt={attempt}"
            )

            result = _execute_single_call(
                adjusted_call,
                execute_fn,
                verify_fn,
                user_input,
                cache,
                tool_log,
                fail_counts,
                pc_state_fn,
                iteration,
            )

            previous_result = result

            if result.get("status") == "ok":
                results.append(result)
                succeeded = True
                break

            if attempt >= MAX_CALL_RETRIES:
                results.append(result)

        if not succeeded and not aborted:
            i += 1
        elif succeeded and not aborted:
            i += 1

    results.sort(key=lambda r: r.get("call_idx", 0))
    return results, aborted
