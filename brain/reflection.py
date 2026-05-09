"""
Post-task reflection engine.  After each task (success or failure) the agent
reflects on what happened, extracts a learnable insight via the LLM, and
writes it to semantic memory so future tasks can benefit.

Reflection is entirely non-blocking — any failure silently returns None and
the calling code proceeds normally.

Layer boundary note
-------------------
brain/ → memory/ is NOT a direct import in this codebase.
The MemoryManager instance is injected as a parameter (typed Any) to avoid
circular imports.  Do NOT add a direct `from memory import ...` here.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from settings import ENABLE_REFLECTION

from brain.ollama_client import chat

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hard cap on the tool-log summary passed to the LLM to avoid token waste.
_MAX_SUMMARY_CHARS: int = 300

# Focused reflection instruction.  Kept short so this stays a cheap LLM call.
_REFLECTION_SYSTEM = (
    "You are a learning component of an AI desktop agent. "
    "You will receive a compact summary of a just-completed task: "
    "which tools were called, whether each succeeded, and the overall outcome. "
    "Reply with 1-2 sentences describing what can be learned for future similar requests. "
    "Focus on: what tool sequence worked, any app path or file that was resolved, "
    "or repeatable patterns worth remembering. "
    "Output ONLY the insight — no preamble, no closing remarks."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reflect(
    user_input: str,
    tool_log: list[dict],
    success: bool,
    memory_manager: Any,
) -> str | None:
    """
    Reflect on the completed task and extract patterns to remember.

    Args:
        user_input:     The original user command.
        tool_log:       List of {"tool": str, "args": dict, "result": dict} entries.
        success:        Whether the task ultimately succeeded.
        memory_manager: MemoryManager instance for writing insights.
                        Typed as Any to avoid a brain → memory circular import.

    Returns:
        A short insight string (logged and stored), or None on failure.
    """
    if not ENABLE_REFLECTION:
        logger.debug("reflection: ENABLE_REFLECTION=False — skipping")
        return None

    try:
        # ── Build a compact tool-log summary ─────────────────────────────────
        tool_lines: list[str] = []
        tools_succeeded: list[str] = []

        for entry in tool_log:
            tool_name = entry.get("tool", "unknown")
            result = entry.get("result") or {}
            # Treat a missing "success" key as success — some tools don't set it.
            ok = bool(result.get("success", True))
            tool_lines.append(f"{tool_name}:{'OK' if ok else 'FAIL'}")
            if ok:
                tools_succeeded.append(tool_name)

        outcome_label = "SUCCESS" if success else "FAILURE"
        summary_raw = (
            f"Task: {user_input}\n"
            f"Outcome: {outcome_label}\n"
            f"Tools: {', '.join(tool_lines) if tool_lines else 'none'}"
        )

        # Cap to _MAX_SUMMARY_CHARS to avoid token waste on long tool logs
        summary = summary_raw[:_MAX_SUMMARY_CHARS]

        # ── Ask the LLM for a learnable insight ──────────────────────────────
        messages: list[dict] = [
            {"role": "system", "content": _REFLECTION_SYSTEM},
            {"role": "user", "content": summary},
        ]

        llm_result = chat(messages=messages, tools=[], temperature=0.3)
        insight = (llm_result.get("content") or "").strip()

        if not insight:
            logger.debug("reflection: empty LLM response — nothing to store")
            return None

        # ── Persist the insight to semantic memory ────────────────────────────
        # ── Persist the insight to semantic memory ────────────────────────────────────────
        memory_key = (
            "insight:"
            + hashlib.md5(user_input.encode("utf-8", errors="replace")).hexdigest()[:16]
        )

        # Deduplication: skip store if insight is identical to what's already saved
        existing = memory_manager.get_preference(memory_key)
        if existing and existing == insight:
            logger.debug("reflection: duplicate insight, skipping store")
            return insight

        memory_manager.set_preference(
            memory_key, insight, confidence=0.6, source="reflection"
        )
        logger.info(
            "reflection: insight stored for %r → %s",
            user_input[:60],
            insight[:120],
        )

        # ── Record the last-successful-tool pattern for future routing ────────
        if success and tools_succeeded:
            last_tool = tools_succeeded[-1]
            memory_manager.observe_pattern("last_successful_tool", last_tool)
            logger.debug("reflection: observed last_successful_tool=%r", last_tool)

        return insight

    except Exception as exc:
        # Reflection is non-blocking — swallow every error so the agent is
        # never blocked by a post-task learning step.
        logger.warning("reflection: reflection failed (non-blocking) — %s", exc)
        return None
