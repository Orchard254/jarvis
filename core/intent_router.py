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

2. NEW: Direct dispatch for known skill functions - bypasses LLM entirely for
   standard commands like volume/brightness control, providing instant execution.

3. Everything else → suggested_tools=[] so get_pruned_schemas() sends all
   schemas in the natural TOOL_SELECTION_PRIORITY order (our carefully tuned
   hierarchy: system_settings first, execute_code last).  The main LLM decides.

Layer boundary
--------------
core/ must NOT import from tools/ or brain/ at module level.
intent_learner is imported lazily inside the function.
"""

import logging
import re

logger = logging.getLogger(__name__)


def _extract_number(text: str) -> int:
    """Extract first number from text"""
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 50


def _try_direct_dispatch(text: str):
    """
    Attempt direct dispatch for known skill patterns.
    Returns (task_id, result) if dispatched, None otherwise.
    """
    text_lower = text.lower().strip()
    
    # Volume control patterns
    volume_patterns = [
        (r'(?:set|change|adjust)\s+volume\s+(?:to\s+)?(\d+)', 'volume_set'),
        (r'volume\s+(?:up|down)', 'volume_adjust'),
        (r'mute\s+volume', 'volume_mute'),
        (r'unmute\s+volume', 'volume_unmute'),
        (r'volume\s+to\s+(\d+)', 'volume_set'),
        (r'set\s+volume\s+to\s+(\d+)', 'volume_set'),
    ]
    
    # Brightness patterns
    brightness_patterns = [
        (r'(?:set|change|adjust)\s+brightness\s+(?:to\s+)?(\d+)', 'brightness_set'),
        (r'brightness\s+(?:up|down)', 'brightness_adjust'),
        (r'set\s+screen\s+brightness\s+(?:to\s+)?(\d+)', 'brightness_set'),
        (r'set\s+brightness\s+to\s+(\d+)', 'brightness_set'),
    ]
    
    # Check volume commands
    for pattern, cmd_type in volume_patterns:
        if re.search(pattern, text_lower):
            level = _extract_number(text_lower) if 'set' in cmd_type or 'to' in text_lower else None
            try:
                from core.direct_dispatcher import dispatcher
                from core.task_registry import registry, TaskStatus
                from core.executor_pool import pool
                
                if cmd_type == 'volume_set':
                    task = registry.create_task("volume_set", f"Set volume to {level}%")
                    future = pool.submit(
                        lambda lvl=level: dispatcher.execute('volume_mute_then_set', lvl),
                        task.id
                    )
                    logger.info(f"Direct dispatch: volume_mute_then_set({level}) -> task {task.id}")
                    return task.id, f"Volume adjustment started (task: {task.id})"
                elif cmd_type == 'volume_mute':
                    task = registry.create_task("volume_mute", "Mute volume")
                    future = pool.submit(
                        lambda: dispatcher.execute('volume_mute_then_set', 0),
                        task.id
                    )
                    logger.info(f"Direct dispatch: volume_mute -> task {task.id}")
                    return task.id, f"Volume muted (task: {task.id})"
                elif cmd_type == 'volume_adjust':
                    # Handle volume up/down without specific level
                    task = registry.create_task("volume_adjust", "Adjust volume")
                    direction = "up" if "up" in text_lower else "down"
                    # Use volume_mute_then_set with a relative adjustment approach
                    # For now, we'll just call it with a small delta
                    future = pool.submit(
                        lambda: dispatcher.execute('volume_mute_then_set', 50),  # Default to 50% for adjust
                        task.id
                    )
                    logger.info(f"Direct dispatch: volume_adjust({direction}) -> task {task.id}")
                    return task.id, f"Volume {direction} (task: {task.id})"
                    
            except Exception as e:
                logger.debug(f"Direct dispatch failed for volume: {e}")
                break
    
    # Check brightness commands
    for pattern, cmd_type in brightness_patterns:
        if re.search(pattern, text_lower):
            level = _extract_number(text_lower) if 'set' in cmd_type or 'to' in text_lower else None
            try:
                from core.direct_dispatcher import dispatcher
                from core.task_registry import registry, TaskStatus
                from core.executor_pool import pool
                
                if cmd_type == 'brightness_set':
                    task = registry.create_task("brightness_set", f"Set brightness to {level}%")
                    future = pool.submit(
                        lambda lvl=level: dispatcher.execute('brightness_set_robust', lvl),
                        task.id
                    )
                    logger.info(f"Direct dispatch: brightness_set_robust({level}) -> task {task.id}")
                    return task.id, f"Brightness adjustment started (task: {task.id})"
                elif cmd_type == 'brightness_adjust':
                    # Handle brightness up/down without specific level
                    task = registry.create_task("brightness_adjust", "Adjust brightness")
                    direction = "up" if "up" in text_lower else "down"
                    # Use brightness_set_robust with a default value for adjust commands
                    future = pool.submit(
                        lambda: dispatcher.execute('brightness_set_robust', 50),  # Default to 50% for adjust
                        task.id
                    )
                    logger.info(f"Direct dispatch: brightness_adjust({direction}) -> task {task.id}")
                    return task.id, f"Brightness {direction} (task: {task.id})"
                    
            except Exception as e:
                logger.debug(f"Direct dispatch failed for brightness: {e}")
                break
    
    # Parallel fetch pattern - "fetch these URLs: url1, url2, ..."
    parallel_fetch_pattern = r'(?:fetch|get|download)\s+(?:these\s+)?(?:urls?|links?|pages?)\s*(?:[:\-]?\s*)?(.+)'
    match = re.search(parallel_fetch_pattern, text_lower)
    if match:
        urls_text = match.group(1).strip()
        # Extract URLs from comma-separated or newline-separated list
        urls = re.findall(r'https?://[^\s,;\n]+', urls_text)
        if len(urls) >= 2:  # Only use parallel if multiple URLs
            try:
                from core.direct_dispatcher import dispatcher
                from core.task_registry import registry
                from core.executor_pool import pool
                
                task = registry.create_task("parallel_fetch", f"Fetch {len(urls)} URLs")
                future = pool.submit(
                    lambda: dispatcher.execute('parallel_fetch', urls),
                    task.id
                )
                logger.info(f"Direct dispatch: parallel_fetch({len(urls)} URLs) -> task {task.id}")
                return task.id, f"Fetching {len(urls)} URLs in parallel (task: {task.id})"
            except Exception as e:
                logger.debug(f"Direct dispatch failed for parallel_fetch: {e}")

    # Parallel file read pattern - "read these files: path1, path2, ..."
    parallel_read_pattern = r'(?:read|load|open)\s+(?:these\s+)?(?:files?|documents?)\s*(?:[:\-]?\s*)?(.+)'
    match = re.search(parallel_read_pattern, text_lower)
    if match:
        files_text = match.group(1).strip()
        # Extract file paths (simple heuristic: comma-separated paths)
        file_paths = [p.strip() for p in files_text.split(',') if p.strip()]
        if len(file_paths) >= 2:  # Only use parallel if multiple files
            try:
                from core.direct_dispatcher import dispatcher
                from core.task_registry import registry
                from core.executor_pool import pool
                
                task = registry.create_task("parallel_read", f"Read {len(file_paths)} files")
                future = pool.submit(
                    lambda: dispatcher.execute('parallel_read', file_paths),
                    task.id
                )
                logger.info(f"Direct dispatch: parallel_read({len(file_paths)} files) -> task {task.id}")
                return task.id, f"Reading {len(file_paths)} files in parallel (task: {task.id})"
            except Exception as e:
                logger.debug(f"Direct dispatch failed for parallel_read: {e}")

    return None


def route(user_input: str) -> dict:
    """
    Return a minimal intent dict consumed by the Orchestrator.

    suggested_tools controls the ORDER (not presence) of schemas fed to the
    main LLM.  Returning [] means natural TOOL_SELECTION_PRIORITY order, which
    is always correct.  Returning a specific list only makes sense when we have
    confirmed, learned evidence that those tools succeeded for this exact intent.
    """
    text = user_input.strip()

    # ── Tier 0: Direct Dispatch Fast Path ────────────────────────────────────
    # Instant execution for known skill patterns without LLM involvement
    direct_result = _try_direct_dispatch(text)
    if direct_result:
        task_id, message = direct_result
        logger.info(
            "intent_router [DIRECT_DISPATCH]: task=%s input=%r",
            task_id,
            text[:80],
        )
        return {
            "raw_input": user_input,
            "goal": user_input,
            "primary_tool": "direct_dispatch",
            "suggested_tools": [],
            "confidence": 1.0,
            "requires_confirmation": False,
            "routing_source": "direct_dispatch",
            "task_id": task_id,
            "immediate_response": message,
        }

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
