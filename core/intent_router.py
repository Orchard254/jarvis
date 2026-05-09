"""
intent_router.py — Unified intent routing for JARVIS.

Design philosophy
-----------------
The main LLM (tool_loop) already has the full system prompt, all tool schemas,
and explicit decision rules.  It is the single source of truth for deciding:
  • Is this a chat reply or a tool call?
  • Which tool fits?
  • How much reasoning is needed?

A separate routing layer that second-guesses this decision adds latency, can
conflict with the main model, and — because LLM_TOOL_SCHEMA_LIMIT=0 means all
schemas are always sent — only ever reorders the schema list.  Wrong routing
pushes the wrong tool to the top and biases the main LLM into using it.

What this module does
---------------------
1. Checks the learned route cache (intent_learner) for exact / near-duplicate
   commands seen before.  If found, we return the tools that actually worked
   last time — a zero-LLM-call fast path for repeated identical commands.

2. Everything else → suggested_tools=[] so get_pruned_schemas() sends all
   schemas in the natural TOOL_SELECTION_PRIORITY order (our carefully tuned
   hierarchy: system_settings first, execute_code last).  The main LLM decides.

Layer boundary
--------------
core/ must NOT import from tools/ or brain/ at module level.
intent_learner is imported lazily inside the function.
"""

import logging

logger = logging.getLogger(__name__)


def route(user_input: str) -> dict:
    """
    Return a minimal intent dict consumed by the Orchestrator.

    suggested_tools controls the ORDER (not presence) of schemas fed to the
    main LLM.  Returning [] means natural TOOL_SELECTION_PRIORITY order, which
    is always correct.  Returning a specific list only makes sense when we have
    confirmed, learned evidence that those tools succeeded for this exact intent.
    """
    text = user_input.strip()

    # ── Tier 1: learned route cache ──────────────────────────────────────────
    # Instant lookup — no LLM call.  Confidence-gated and stale-aware.
    # Only fires on exact-normalised or embedding-similar matches (>=0.78).
    try:
        from core.intent_learner import lookup_route

        cached_tools = lookup_route(text)
        if cached_tools:
            logger.info(
                "intent_router [LEARNED]: tools=%s input=%r",
                cached_tools,
                text[:80],
            )
            return {
                "raw_input": user_input,
                "goal": user_input,
                "primary_tool": cached_tools[0],
                "suggested_tools": cached_tools,
                "confidence": 0.90,
                "requires_confirmation": False,
                "routing_source": "learned",
            }
    except Exception as _e:
        logger.debug("intent_router: learned lookup failed (%s) — continuing", _e)

    # ── Tier 2: direct to main LLM ───────────────────────────────────────────
    # suggested_tools=[] → get_pruned_schemas returns all schemas in the
    # natural TOOL_SELECTION_PRIORITY order.  The main LLM decides everything.
    logger.info("intent_router [DIRECT]: input=%r", text[:80])
    return {
        "raw_input": user_input,
        "goal": user_input,
        "primary_tool": "",
        "suggested_tools": [],
        "confidence": 1.0,
        "requires_confirmation": False,
        "routing_source": "llm_direct",
    }
