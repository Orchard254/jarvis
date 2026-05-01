# intent_classifier.py — Semantic intent classification via LLM
import json
import time

import requests

import config
from logger import get_logger

log = get_logger("intent_classifier")

# FIX 9: Add simple cache for intent classification
_intent_cache = {}
_cache_timestamps = {}
_CACHE_TTL = 300  # 5 minutes

SUPPORTED_INTENTS = [
    "screenshot",
    "time",
    "open",
    "close",
    "volume",
    "brightness",
    "search",
    "shutdown",
    "lock",
]

INTENT_SYSTEM_PROMPT = """You are a deterministic intent classification engine.

SUPPORTED INTENTS:
- screenshot: capture screen
- time: get system time
- open: open application
- close: close application
- volume: adjust system volume
- brightness: adjust screen brightness
- search: web search
- shutdown: shut down system
- lock: lock system

RULES:
1. Interpret FINAL intention (apply corrections: "actually", "wait", "no", "instead", "don't", "forget")
2. Extract ALL valid intents in final meaning
3. Assign confidence: clear=0.90-1.0, implicit=0.60-0.89, weak=0.30-0.59, rejected<=0.20
4. NEVER output only one intent unless only one truly present
5. NEVER drop secondary valid intents

OUTPUT FORMAT (JSON array only):
[{"intent": "<name>", "confidence": <float>}]

NO explanations. NO markdown. JSON only."""


def _extract_llm_content(data: object) -> str:
    """Extract plain assistant content from varied Ollama response shapes."""
    if isinstance(data, dict):
        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message") or first
                if isinstance(message, dict):
                    content = message.get("content") or message.get("text")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                text = first.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()

    if isinstance(data, str) and data.strip():
        return data.strip()

    return ""


def classify_intents(user_text: str) -> list[dict]:
    """
    Classify user text into structured intents with confidence scores.
    Uses LLM for semantic understanding instead of keyword matching.
    """
    if not user_text:
        return []

    # FIX 9: Check cache first
    text_hash = hash(user_text.lower().strip())
    now = time.time()
    if text_hash in _intent_cache:
        if now - _cache_timestamps.get(text_hash, 0) < _CACHE_TTL:
            log.debug(f"[INTENT] Cache hit for: {user_text[:50]}")
            return _intent_cache[text_hash]

    try:
        payload = {
            "model": config.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 100,  # Keep low to force concise output, "stop": ["\n\n", "```", "</s>"],  # Stop sequences to prevent rambling
            },
        }

        headers = {
            "Authorization": f"Bearer {config.OLLAMA_API_KEY}",
            "Content-Type": "application/json",
        }

        max_retries = 2
        resp = None
        for attempt in range(max_retries):
            try:
                # FIX 9: Reduced timeout with fewer retries for faster failure
                resp = requests.post(
                    config.OLLAMA_CLOUD_URL,
                    json=payload,
                    headers=headers,
                    timeout=config.OLLAMA_TIMEOUT,
                )
                break
            except requests.exceptions.Timeout:
                log.warning(f"[INTENT] Timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Short delay before retry
                    continue
                # Fall back to keyword-based classification on timeout
                log.warning("[INTENT] Timeout during LLM request, using keyword fallback")
                return _keyword_based_classification(user_text)
            except requests.exceptions.ConnectionError as e:
                log.warning(f"[INTENT] Connection error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise
        if resp is None:
            return []
        resp.raise_for_status()
        data = resp.json()

        content = _extract_llm_content(data)
        if not content:
            # Some endpoints may return bare text or an alternate wrapper.
            content = resp.text.strip()

        # Parse JSON from response
        try:
            # Handle markdown code blocks if present
            if "```" in content:
                content = content.split("```")[-1].split("```")[0]

            # Try to find JSON array in content
            if "[" in content and "]" in content:
                start = content.find("[")
                end = content.rfind("]") + 1
                content = content[start:end]
            elif "[" in content:
                # Truncated output - try to extract what we have
                start = content.find("[")
                content = content[start:]
                # Try to complete the JSON if it looks truncated
                if not content.endswith("]"):
                    # Count braces to see if we can salvage
                    if content.count("{") == content.count("}"):
                        content = content + "]"  # Close the array

            intents = json.loads(content)
            if isinstance(intents, dict):
                intents = [intents]
        except json.JSONDecodeError as e:
            log.warning(f"[INTENT] Failed to parse JSON: {content[:100]}... Error: {e}")
            # Try to salvage partial results by looking for completed intent objects
            try:
                # Look for patterns like {"intent":"xxx","confidence":0.xx}
                import re

                pattern = r'\{"intent"\s*:\s*"(\w+)"\s*,\s*"confidence"\s*:\s*([\d.]+)\}'
                matches = re.findall(pattern, content)
                if matches:
                    log.info(f"[INTENT] Salvaged {len(matches)} intents from partial JSON")
                    valid_intents = [
                        {"intent": name, "confidence": float(conf)}
                        for name, conf in matches
                        if name in SUPPORTED_INTENTS
                    ]
                    return valid_intents
            except Exception:
                pass
            # Fallback: use keyword-based classification
            log.warning("[INTENT] Falling back to keyword-based classification")
            return _keyword_based_classification(user_text)

        # Validate and filter intents
        valid_intents = []
        for item in intents:
            if isinstance(item, dict):
                intent_name = item.get("intent", "")
                confidence = item.get("confidence", 0.0)

                if intent_name in SUPPORTED_INTENTS and 0.0 <= confidence <= 1.0:
                    valid_intents.append({"intent": intent_name, "confidence": confidence})

        # Sort by confidence descending
        valid_intents.sort(key=lambda x: x["confidence"], reverse=True)

        if not valid_intents:
            fallback = _keyword_based_classification(user_text)
            if fallback:
                log.warning("[INTENT] LLM returned no valid intents, using keyword fallback")
                valid_intents = fallback

        log.info(f"[INTENT] Classified: {valid_intents}")

        # FIX 9: Cache the result
        _intent_cache[text_hash] = valid_intents
        _cache_timestamps[text_hash] = now

        # Clean old cache entries
        old_keys = [k for k, t in _cache_timestamps.items() if now - t > _CACHE_TTL]
        for k in old_keys:
            del _intent_cache[k]
            del _cache_timestamps[k]

        return valid_intents

    except Exception as e:
        log.error(f"[INTENT] Classification error: {e}")
        return []


def _keyword_based_classification(user_text: str) -> list[dict]:
    """Fallback keyword-based intent classification when LLM fails."""
    text_lower = user_text.lower()

    # Simple keyword mapping
    keyword_map = {
        "open": ["open", "launch", "start"],
        "close": ["close", "exit", "quit"],
        "volume": ["volume", "mute", "unmute", "louder", "quieter", "up", "down"],
        "brightness": ["brightness", "bright", "dim"],
        "search": ["search", "google", "find", "look up"],
        "time": ["time", "date", "clock"],
        "screenshot": ["screenshot", "screen capture", "capture screen"],
        "shutdown": ["shutdown", "power off", "turn off"],
        "lock": ["lock", "lock screen"],
    }

    scores = {}
    for intent, keywords in keyword_map.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            # Normalize score to 0.3-0.9 range based on keyword matches
            normalized_score = min(0.3 + (score * 0.2), 0.9)
            scores[intent] = normalized_score

    # Convert to format
    valid_intents = [
        {"intent": intent, "confidence": confidence} for intent, confidence in scores.items()
    ]

    # Sort by confidence descending
    valid_intents.sort(key=lambda x: x["confidence"], reverse=True)

    if valid_intents:
        log.info(f"[INTENT] Keyword fallback classified: {valid_intents}")

    return valid_intents


def intents_to_tools(classified_intents: list[dict]) -> set[str]:
    """
    Map classified intents to tool names.
    Returns set of valid tool names to execute.
    """
    intent_to_tool = {
        "screenshot": "screen_capture",
        "time": "get_time",
        "open": "open_app",
        "close": "close_app",
        "volume": "set_volume",
        "brightness": "set_brightness",
        "search": "search_web",
        "shutdown": "shutdown_pc",
        "lock": "lock_pc",
    }

    return {intent_to_tool[i["intent"]] for i in classified_intents if i["confidence"] > 0.5}
