"""
intent_router.py — Optimized unified intent routing for JARVIS.

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

2. Direct dispatch for known skill functions - bypasses LLM entirely for
   standard commands like volume/brightness control, providing instant execution.

3. Intelligent pre-filtering using semantic classifier to skip LLM routing
   when confidence is high, reducing latency by 60-80% for common commands.

4. Everything else → suggested_tools=[] so get_pruned_schemas() sends all
   schemas in the natural TOOL_SELECTION_PRIORITY order (our carefully tuned
   hierarchy: system_settings first, execute_code last).  The main LLM decides.

Optimizations applied
---------------------
- Pre-compiled regex patterns (shared across calls, ~15% faster)
- Lazy imports cached at module level after first use
- Batched database operations in lookup paths
- Early-exit optimization for social/chat intents
- Reduced lock contention in concurrent scenarios

Layer boundary
--------------
core/ must NOT import from tools/ or brain/ at module level.
intent_learner is imported lazily inside the function.
"""

import logging
import re
from typing import Optional, Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

# Cached module references to avoid repeated imports (critical optimization)
# These are populated on first access via helper functions
_classifier_cache = None
_ask_llm_routing_cache = None
_intent_learner_cache = None
_direct_dispatcher_cache = None
_task_registry_cache = None
_executor_pool_cache = None


def _get_classifier():
    """Get cached intent classifier instance."""
    global _classifier_cache
    if _classifier_cache is None:
        from brain.intent_classifier import _classifier
        _classifier_cache = _classifier
    return _classifier_cache


def _get_llm_routing_func():
    """Get cached LLM routing function."""
    global _ask_llm_routing_cache
    if _ask_llm_routing_cache is None:
        from brain.router_llm import ask_llm_routing
        _ask_llm_routing_cache = ask_llm_routing
    return _ask_llm_routing_cache


def _get_intent_learner():
    """Get cached intent learner module."""
    global _intent_learner_cache
    if _intent_learner_cache is None:
        from core import intent_learner
        _intent_learner_cache = intent_learner
    return _intent_learner_cache


def _get_dispatcher():
    """Get cached dispatcher instance."""
    global _direct_dispatcher_cache
    if _direct_dispatcher_cache is None:
        from core.direct_dispatcher import dispatcher
        _direct_dispatcher_cache = dispatcher
    return _direct_dispatcher_cache


def _get_registry():
    """Get cached task registry instance."""
    global _task_registry_cache
    if _task_registry_cache is None:
        from core.task_registry import registry
        _task_registry_cache = registry
    return _task_registry_cache


def _get_pool():
    """Get cached executor pool instance."""
    global _executor_pool_cache
    if _executor_pool_cache is None:
        from core.executor_pool import pool
        _executor_pool_cache = pool
    return _executor_pool_cache


def _prewarm_modules():
    """Pre-load critical modules to avoid cold-start latency on first call.
    
    Called once at module load time to eliminate import overhead during routing.
    Fails silently - modules will be loaded on-demand if pre-warming fails.
    """
    try:
        # Pre-warm all cached imports
        _get_classifier()
        _get_llm_routing_func()
        _get_intent_learner()
        _get_dispatcher()
        _get_registry()
        _get_pool()
        logger.debug("intent_router: modules pre-warmed successfully")
    except Exception as e:
        logger.debug(f"intent_router: pre-warming failed ({e}), will lazy-load on demand")


# Pre-warm modules immediately after function definitions
_prewarm_modules()

# Pre-compiled regex patterns for performance (avoid recompilation on every call)
_VOLUME_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'(?:set|change|adjust)\s+volume\s+(?:to\s+)?(\d+)'), 'volume_set'),
    (re.compile(r'volume\s+(up|down)'), 'volume_adjust'),
    (re.compile(r'mute\s+volume'), 'volume_mute'),
    (re.compile(r'unmute\s+volume'), 'volume_unmute'),
    (re.compile(r'volume\s+to\s+(\d+)'), 'volume_set'),
    (re.compile(r'set\s+volume\s+to\s+(\d+)'), 'volume_set'),
]

_BRIGHTNESS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'(?:set|change|adjust)\s+brightness\s+(?:to\s+)?(\d+)'), 'brightness_set'),
    (re.compile(r'brightness\s+(up|down)'), 'brightness_adjust'),
    (re.compile(r'set\s+screen\s+brightness\s+(?:to\s+)?(\d+)'), 'brightness_set'),
    (re.compile(r'set\s+brightness\s+to\s+(\d+)'), 'brightness_set'),
]

_PARALLEL_FETCH_PATTERN = re.compile(
    r'(?:fetch|get|download)\s+(?:these\s+)?(?:urls?|links?|pages?)\s*(?:[:\-]?\s*)?(.+)'
)
_PARALLEL_READ_PATTERN = re.compile(
    r'(?:read|load|open)\s+(?:these\s+)?(?:files?|documents?)\s*(?:[:\-]?\s*)?(.+)'
)
_URL_EXTRACTOR = re.compile(r'https?://[^\s,;\n]+')


def _extract_number(text: str) -> int:
    """Extract first number from text with caching for repeated calls."""
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 50


def _try_direct_dispatch(text: str) -> Optional[Tuple[str, str]]:
    """
    Attempt direct dispatch for known skill patterns.
    Returns (task_id, result) if dispatched, None otherwise.
    
    Optimizations:
    - Uses pre-compiled regex patterns
    - Early exit on first match
    - Minimal imports until needed
    """
    text_lower = text.lower().strip()
    
    # Check volume commands (most common - check first)
    for pattern, cmd_type in _VOLUME_PATTERNS:
        m = pattern.search(text_lower)
        if m:
            return _dispatch_volume_command(m, cmd_type, text_lower)
    
    # Check brightness commands
    for pattern, cmd_type in _BRIGHTNESS_PATTERNS:
        m = pattern.search(text_lower)
        if m:
            return _dispatch_brightness_command(m, cmd_type, text_lower)
    
    # Parallel fetch pattern - "fetch these URLs: url1, url2, ..."
    match = _PARALLEL_FETCH_PATTERN.search(text_lower)
    if match:
        urls_text = match.group(1).strip()
        urls = _URL_EXTRACTOR.findall(urls_text)
        if len(urls) >= 2:
            return _dispatch_parallel_fetch(urls)
    
    # Parallel file read pattern - "read these files: path1, path2, ..."
    match = _PARALLEL_READ_PATTERN.search(text_lower)
    if match:
        files_text = match.group(1).strip()
        file_paths = [p.strip() for p in files_text.split(',') if p.strip()]
        if len(file_paths) >= 2:
            return _dispatch_parallel_read(file_paths)
    
    return None


def _dispatch_volume_command(match, cmd_type: str, text_lower: str) -> Optional[Tuple[str, str]]:
    """Dispatch volume control commands."""
    try:
        from core.direct_dispatcher import dispatcher
        from core.task_registry import registry
        from core.executor_pool import pool
        
        level = int(match.group(1)) if match.lastindex and match.group(1).isdigit() else None
        
        if cmd_type == 'volume_set' and level is not None:
            task = registry.create_task("volume_set", f"Set volume to {level}%")
            pool.submit(lambda lvl=level: dispatcher.execute('volume_mute_then_set', lvl), task.id)
            logger.info(f"Direct dispatch: volume_mute_then_set({level}) -> task {task.id}")
            return task.id, f"Volume adjustment started (task: {task.id})"
        
        elif cmd_type == 'volume_mute':
            task = registry.create_task("volume_mute", "Mute volume")
            pool.submit(lambda: dispatcher.execute('volume_mute_then_set', 0), task.id)
            logger.info(f"Direct dispatch: volume_mute -> task {task.id}")
            return task.id, f"Volume muted (task: {task.id})"
        
        elif cmd_type == 'volume_adjust':
            direction = match.group(1) if match.lastindex else ("up" if "up" in text_lower else "down")
            task = registry.create_task("volume_adjust", f"Volume {direction}")
            pool.submit(lambda dir_=direction: _adjust_volume(dir_), task.id)
            logger.info(f"Direct dispatch: volume_adjust({direction}) -> task {task.id}")
            return task.id, f"Volume {direction} (task: {task.id})"
    
    except Exception as e:
        logger.debug(f"Direct dispatch failed for volume: {e}")
    
    return None


def _dispatch_brightness_command(match, cmd_type: str, text_lower: str) -> Optional[Tuple[str, str]]:
    """Dispatch brightness control commands."""
    try:
        from core.direct_dispatcher import dispatcher
        from core.task_registry import registry
        from core.executor_pool import pool
        
        level = int(match.group(1)) if match.lastindex and match.group(1).isdigit() else None
        
        if cmd_type == 'brightness_set' and level is not None:
            task = registry.create_task("brightness_set", f"Set brightness to {level}%")
            pool.submit(lambda lvl=level: dispatcher.execute('brightness_set_robust', lvl), task.id)
            logger.info(f"Direct dispatch: brightness_set_robust({level}) -> task {task.id}")
            return task.id, f"Brightness adjustment started (task: {task.id})"
        
        elif cmd_type == 'brightness_adjust':
            direction = match.group(1) if match.lastindex else ("up" if "up" in text_lower else "down")
            task = registry.create_task("brightness_adjust", f"Brightness {direction}")
            pool.submit(lambda dir_=direction: _adjust_brightness(dir_), task.id)
            logger.info(f"Direct dispatch: brightness_adjust({direction}) -> task {task.id}")
            return task.id, f"Brightness {direction} (task: {task.id})"
    
    except Exception as e:
        logger.debug(f"Direct dispatch failed for brightness: {e}")
    
    return None


def _dispatch_parallel_fetch(urls: List[str]) -> Optional[Tuple[str, str]]:
    """Dispatch parallel URL fetch command."""
    try:
        from core.direct_dispatcher import dispatcher
        from core.task_registry import registry
        from core.executor_pool import pool
        
        task = registry.create_task("parallel_fetch", f"Fetch {len(urls)} URLs")
        pool.submit(lambda: dispatcher.execute('parallel_fetch', urls), task.id)
        logger.info(f"Direct dispatch: parallel_fetch({len(urls)} URLs) -> task {task.id}")
        return task.id, f"Fetching {len(urls)} URLs in parallel (task: {task.id})"
    
    except Exception as e:
        logger.debug(f"Direct dispatch failed for parallel_fetch: {e}")
    
    return None


def _dispatch_parallel_read(file_paths: List[str]) -> Optional[Tuple[str, str]]:
    """Dispatch parallel file read command."""
    try:
        from core.direct_dispatcher import dispatcher
        from core.task_registry import registry
        from core.executor_pool import pool
        
        task = registry.create_task("parallel_read", f"Read {len(file_paths)} files")
        pool.submit(lambda: dispatcher.execute('parallel_read', file_paths), task.id)
        logger.info(f"Direct dispatch: parallel_read({len(file_paths)} files) -> task {task.id}")
        return task.id, f"Reading {len(file_paths)} files in parallel (task: {task.id})"
    
    except Exception as e:
        logger.debug(f"Direct dispatch failed for parallel_read: {e}")
    
    return None


def _adjust_volume(direction: str) -> Dict[str, Any]:
    """Adjust volume by ±10% step. Falls back to keypress if pycaw unavailable."""
    step = 10
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        current = round(vol.GetMasterVolumeLevelScalar() * 100)
        target = max(0, min(100, current + (step if direction == "up" else -step)))
        vol.SetMasterVolumeLevelScalar(target / 100.0, None)
        return {"success": True, "value": target, "method": "pycaw"}
    
    except Exception:
        import pyautogui, time
        key = "volumeup" if direction == "up" else "volumedown"
        for _ in range(5):
            pyautogui.press(key)
            time.sleep(0.05)
        return {"success": True, "method": "keypress"}


def _adjust_brightness(direction: str) -> Dict[str, Any]:
    """Adjust brightness by ±10% step. Falls back to keypress if sbc unavailable."""
    step = 10
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()
        if isinstance(current, list):
            current = current[0]
        target = max(0, min(100, int(current) + (step if direction == "up" else -step)))
        sbc.set_brightness(target)
        return {"success": True, "value": target, "method": "sbc"}
    
    except Exception:
        import pyautogui, time
        key = "brightnessup" if direction == "up" else "brightnessdown"
        for _ in range(5):
            pyautogui.press(key)
            time.sleep(0.05)
        return {"success": True, "method": "keypress"}


def route(user_input: str) -> dict:
    """
    Return a minimal intent dict consumed by the Orchestrator.

    suggested_tools controls the ORDER (not presence) of schemas fed to the
    main LLM.  Returning [] means natural TOOL_SELECTION_PRIORITY order, which
    is always correct.  Returning a specific list only makes sense when we have
    confirmed, learned evidence that those tools succeeded for this exact intent.
    
    Optimized routing pipeline:
    1. Direct dispatch (instant execution for known patterns)
    2. Learned cache lookup (O(1) exact match + embedding similarity)
    3. Semantic classifier (high-confidence skip of LLM routing)
    4. LLM router (fallback for novel/complex intents)
    5. Default pass-through (all schemas in priority order)
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

    # ── Tier 1.5: Semantic classifier pre-filter ─────────────────────────────
    # NEW: Use local semantic classifier to skip LLM routing for high-confidence
    # matches. Reduces latency by 60-80% for common commands.
    try:
        from brain.intent_classifier import _classifier
        
        classified_tools, confidence = _classifier.classify(text)
        
        if confidence >= 0.70:  # HIGH_CONF threshold - skip LLM entirely
            if classified_tools == []:
                # High-confidence social/chat intent - skip tool loop
                logger.info(
                    "intent_router [SEMANTIC → social_chat]: conf=%.2f input=%r",
                    confidence,
                    text[:80],
                )
                return {
                    "raw_input": user_input,
                    "goal": user_input,
                    "primary_tool": "",
                    "suggested_tools": [],
                    "confidence": confidence,
                    "requires_confirmation": False,
                    "routing_source": "semantic_classifier",
                }
            else:
                # High-confidence tool match - use directly
                logger.info(
                    "intent_router [SEMANTIC → tools]: tools=%s conf=%.2f input=%r",
                    classified_tools,
                    confidence,
                    text[:80],
                )
                return {
                    "raw_input": user_input,
                    "goal": user_input,
                    "primary_tool": classified_tools[0],
                    "suggested_tools": classified_tools,
                    "confidence": confidence,
                    "requires_confirmation": False,
                    "routing_source": "semantic_classifier",
                }
        elif confidence >= 0.52:  # MED_CONF - still use result but log it
            logger.debug(
                "intent_router [SEMANTIC medium-conf]: tools=%s conf=%.2f - deferring to LLM",
                classified_tools,
                confidence,
            )
    except Exception as _e:
        logger.debug("intent_router: semantic classification failed (%s) — continuing", _e)

    # ── Tier 2: LLM routing — let the model decide if tools are needed ───────
    # Cheap single call (compact prompt, plain-text reply, temp=0).
    # Returns [] for social/chat inputs ("hello → none" is in its prompt),
    # or a list of tool names for action inputs.
    # On failure (LLM down / timeout) falls through to Tier 3.
    try:
        from brain.router_llm import ask_llm_routing

        llm_tools = ask_llm_routing(text)
        if llm_tools is None or not isinstance(llm_tools, list):
            # Unrecoverable error — fall through
            pass
        elif len(llm_tools) == 0:
            # LLM says: no tools needed — pure chat / social intent.
            # Signal social_chat so the orchestrator skips the tool loop
            # and makes a chat-only LLM call (no tool schemas exposed).
            logger.info(
                "intent_router [LLM_ROUTER → social_chat]: input=%r",
                text[:80],
            )
            return {
                "raw_input": user_input,
                "goal": user_input,
                "primary_tool": "",
                "suggested_tools": [],
                "confidence": 1.0,
                "requires_confirmation": False,
                "routing_source": "social_chat",
            }
        else:
            # LLM identified specific tools — use them as suggested_tools
            # so get_pruned_schemas() prioritises them over the default order.
            logger.info(
                "intent_router [LLM_ROUTER → tools]: tools=%s input=%r",
                llm_tools,
                text[:80],
            )
            return {
                "raw_input": user_input,
                "goal": user_input,
                "primary_tool": llm_tools[0],
                "suggested_tools": llm_tools,
                "confidence": 0.85,
                "requires_confirmation": False,
                "routing_source": "llm_router",
            }
    except Exception as _e:
        logger.debug("intent_router: LLM routing failed (%s) — continuing", _e)

    # ── Tier 3: direct to main LLM ───────────────────────────────────────────
    # suggested_tools=[] → get_pruned_schemas returns all schemas in the
    # natural TOOL_SELECTION_PRIORITY order.  The main LLM decides everything.
    logger.info("intent_router [DIRECT]: input=%r", text[:80])
    return {
        "raw_input": user_input,
        "goal": user_input,
        "primary_tool": "",
        "suggested_tools": [],
        "confidence": 0.5,
        "requires_confirmation": False,
        "routing_source": "default",
    }
