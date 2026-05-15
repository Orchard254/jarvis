"""
Executor agent — validates tool calls with a small LLM before execution.
Bridge between the Jarvis planner and the OS/tool runtime.
"""
import json
import logging

from settings import EXECUTOR_MODEL
from brain import ollama_client
from brain.executor_prompt import build_executor_prompt
from brain.response_parser import format_batch_result

logger = logging.getLogger(__name__)


def validate_tool_call(tool_name: str, args: dict) -> str | None:
    """
    Validate a single tool call's parameters against its schema using executor LLM.
    Returns None if valid, or an error string if invalid.
    """
    messages = [
        {"role": "system", "content": build_executor_prompt()},
        {
            "role": "user",
            "content": (
                f"Validate this tool call against its schema:\n"
                f"Tool: {tool_name}\n"
                f"Arguments: {json.dumps(args, indent=2)}\n\n"
                f"Return VALIDATED if parameters are correct, "
                f"or TOOL_VALIDATION_ERROR with specific field-level errors."
            ),
        },
    ]

    try:
        result = ollama_client.chat(
            messages,
            model=EXECUTOR_MODEL,
            temperature=0.1,
            max_retries=1,
        )
        content = result.get("content", "")
        if content:
            logger.info(f"Executor: {tool_name} -> {content[:150]}")
    except Exception as e:
        logger.warning(f"Executor LLM call failed: {e}")
        return f"Validation skipped due to LLM error: {e}"

    if "TOOL_VALIDATION_ERROR" in content:
        logger.warning(f"Executor rejected {tool_name}")
        return content

    return None


def execute_plan(
    plan: dict,
    execute_fn,
    verify_fn,
    user_input: str,
    cache,
    tool_log: list,
    fail_counts: dict,
    pc_state_fn,
    iteration: int,
) -> str:
    """Execute a BATCH_TOOL_PLAN using the runtime."""
    from brain.tool_loop import _execute_batch_plan
    results = _execute_batch_plan(
        plan, execute_fn, verify_fn, user_input,
        cache, tool_log, fail_counts, pc_state_fn, iteration,
    )
    return format_batch_result(plan.get("plan_id", "unknown"), results)
