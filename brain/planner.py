"""
Pre-execution planner.  Asks the LLM to decompose a complex user request
into an ordered list of sub-steps *before* the tool loop starts.

Returns None for simple / short requests and whenever planning is disabled —
planning is optional and fully non-blocking; a failure here must never
prevent the task from running.
"""

from __future__ import annotations

import logging
import re

from settings import ENABLE_PLANNING, ITERATION_CAPS

from brain.ollama_client import chat
from brain.prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Plan depth is bounded at 8 and must stay within the agent's own iteration
# budget so every step in the plan can actually be executed.
_MAX_STEPS: int = min(8, ITERATION_CAPS.get("interactive_cloud", 10))

# Focused planner instruction injected as a second system message (after the
# full situational-awareness prompt so the LLM knows which tools are available).
_PLANNER_INSTRUCTION = (
    "You are a task-planner sub-routine for an AI desktop agent.\n"
    "Given the user request below, decide:\n"
    "  • ONE action only → reply with exactly the single word: SIMPLE\n"
    "  • MULTIPLE ordered steps where each step's OUTPUT is the INPUT for the next → "
    "reply with a numbered list (maximum {max_steps} items).\n"
    "\n"
    "Default to SIMPLE for: greetings, any single-tool action (open app, check setting, "
    "close window, set volume, take screenshot, arrange windows, list processes, "
    "read/write a file, web search). These are ALL single-step — never plan them.\n"
    "\n"
    "Use a numbered list ONLY when step N produces data that step N+1 strictly needs. "
    "Example: find a file path THEN open it with that path.\n"
    "\n"
    "NEVER include capture_screen, read_pc_state, or query_pc_index as verification "
    "or confirmation steps — the agent handles its own error recovery.\n"
    "\n"
    "Good multi-step example (each step feeds the next):\n"
    "  1. query_pc_index to find the VLC executable path\n"
    "  2. execute_code to launch VLC using that exact path\n"
    "\n"
    "Bad example (do NOT do this — these are all SIMPLE):\n"
    "  1. execute_code to open VLC\n"
    "  2. capture_screen to confirm VLC opened   ← WRONG: never add verification steps\n"
    "\n"
    "Output ONLY 'SIMPLE' or the numbered list — no preamble, no commentary."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def plan(
    user_input: str,
    history: list[dict],
    memory_context: str = "",
) -> list[str] | None:
    """
    Ask the LLM to break a complex request into ordered sub-steps.

    Returns:
        list[str] — ordered list of sub-task strings, e.g.:
            ["query_pc_index to find VLC path",
             "execute_code to open VLC with found path"]
        None — if the request is simple enough to execute directly
               (no plan needed), or if the LLM is unavailable
    """
    if not ENABLE_PLANNING:
        logger.debug("planner: ENABLE_PLANNING=False — skipping")
        return None

    try:
        instruction = _PLANNER_INSTRUCTION.format(max_steps=_MAX_STEPS)

        # Build message list:
        #   [0] full situational-awareness prompt  → LLM knows which tools exist
        #   [1] focused planner instruction        → LLM knows the output format
        #   [2..5] last few history turns           → handles follow-up commands
        #   [optional] memory context
        #   [-1] the actual user request
        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "system", "content": instruction},
        ]

        if history:
            # Include at most 4 most-recent turns for follow-up command context
            messages.extend(history[-4:])

        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        messages.append({"role": "user", "content": user_input})

        llm_result = chat(messages=messages, tools=[], temperature=0.2)
        raw = (llm_result.get("content") or "").strip()

        if not raw:
            logger.debug("planner: empty LLM response — skipping plan")
            return None

        # LLM classified the task as atomic
        if raw.upper().startswith("SIMPLE"):
            logger.info("planner: LLM classified request as SIMPLE — no plan generated")
            return None

        # Parse numbered list lines: "1. text", "1) text", or "- text" bullets
        steps: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?:\d+[.)]\s*|-\s+)(.+)", line)
            if match:
                step_text = match.group(1).strip()
                if step_text:
                    steps.append(step_text)

        if not steps:
            logger.debug(
                "planner: could not parse steps from LLM response — skipping plan"
            )
            return None

        # Enforce the hard step cap
        steps = steps[:_MAX_STEPS]

        logger.info(
            "planner: %d-step plan for %r → %s",
            len(steps),
            user_input[:60],
            steps,
        )
        return steps

    except Exception as exc:
        # Planning is non-blocking — swallow every error and let the agent
        # proceed without a pre-computed plan.
        logger.warning("planner: planning failed (non-blocking) — %s", exc)
        return None
