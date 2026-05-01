# brain.py — JARVIS AI core: LLM inference ONLY (tool_calls generation)

import json
import os
import threading
from typing import Callable, Generator

import requests

import config
from logger import get_logger

log = get_logger("brain")

TOOL_RELIABILITY_FILE = os.path.join(os.path.dirname(__file__), "tool_reliability.json")


def _get_reliability_context() -> str:
    """Get tool reliability context for LLM (read-only, no execution influence)."""
    try:
        if os.path.exists(TOOL_RELIABILITY_FILE):
            with open(TOOL_RELIABILITY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data:
                return ""

            # Only include tools where failures >= 3 AND failure_rate > 0.3
            failing_tools = []
            for name, info in data.items():
                successes = info.get("successes", 0)
                failures = info.get("failures", 0)
                total = successes + failures
                if total >= 3 and failures > 0:
                    fail_rate = (failures / total) * 100
                    if fail_rate > 30:  # > 0.3 = 30%
                        failing_tools.append((name, fail_rate, failures, total))

            if not failing_tools:
                return ""

            # Sort by failure rate, limit to TOP 5
            failing_tools.sort(key=lambda x: x[1], reverse=True)
            failing_tools = failing_tools[:5]

            # Build context string
            lines = ["Tool reliability warning:"]
            for name, fail_rate, failures, total in failing_tools:
                lines.append(f"  - {name}: {fail_rate:.0f}% failure rate")

            result = "\n".join(lines)

            # HARD LIMIT: max 500 characters
            if len(result) > 500:
                result = result[:497] + "..."

            return result
    except Exception as e:
        log.debug(f"Error reading tool reliability: {e}")
    return ""


# ── Streaming conversational reply (no tools) ─────────────────────────────────

# Common abbreviations that shouldn't be split as sentence endings
_ABBREVIATIONS = {
    "dr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "sr",
    "jr",
    "etc",
    "vs",
    "e.g",
    "i.e",
    "u.s",
    "u.k",
    "a.m",
    "p.m",
}


def _is_sentence_end(buffer: str, pos: int) -> bool:
    """Check if position in buffer is a real sentence end, not an abbreviation."""
    if buffer[pos] not in ".!?":
        return False

    # Check if this is an abbreviation (e.g., "Dr.")
    # Look backwards to find start of current word/token
    word_start = pos - 1
    while word_start >= 0 and buffer[word_start].isalpha():
        word_start -= 1
    word = buffer[word_start + 1 : pos].lower()
    if word in _ABBREVIATIONS:
        return False

    # Check if followed by space and capital letter (strong sentence boundary signal)
    if pos + 1 < len(buffer) and buffer[pos + 1] == " ":
        return True

    return False


def stream_reply(messages: list, system: str) -> Generator[str, None, None]:
    """Stream a conversational reply from Ollama sentence by sentence for TTS."""
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": True,
        "options": {
            "temperature": config.OLLAMA_TEMPERATURE,
            "num_predict": config.OLLAMA_MAX_TOKENS,
        },
    }

    # Try cloud first, then fallback to local Ollama
    urls_to_try = [
        (
            config.OLLAMA_CLOUD_URL,
            {
                "Authorization": f"Bearer {config.OLLAMA_API_KEY}",
                "Content-Type": "application/json",
            },
            "cloud",
        ),
        ("http://localhost:11434/api/chat", {"Content-Type": "application/json"}, "local"),
    ]

    buffer = ""
    yielded_text = ""

    for url, headers, source in urls_to_try:
        try:
            log.info(f"[BRAIN] Streaming from {source} Ollama endpoint: {url}")
            with requests.post(
                url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=120,
            ) as resp:
                resp.raise_for_status()

                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    token = chunk.get("message", {}).get("content", "")
                    buffer += token

                    while True:
                        # Find next sentence end
                        found = False
                        for i, ch in enumerate(buffer):
                            if (
                                _is_sentence_end(buffer, i)
                                and i + 1 < len(buffer)
                                and buffer[i + 1] == " "
                            ):
                                sentence = buffer[: i + 1].strip()
                                buffer = buffer[i + 2 :]
                                if sentence:
                                    yield sentence
                                    yielded_text += sentence + " "
                                found = True
                                break
                        if not found:
                            break

                    if chunk.get("done"):
                        break

                break  # Success, don't try other URLs

        except requests.exceptions.ConnectionError:
            log.warning(f"[BRAIN] {source} connection error during streaming")
            if source == "local":
                yield "[Error: Cannot reach Ollama. Check internet connection.]"
                return
            continue  # Try next URL
        except requests.exceptions.HTTPError as e:
            log.warning(f"[BRAIN] {source} HTTP error during streaming: {e}")
            if source == "local":
                yield f"[Error: HTTP {e.response.status_code}]"
                return
            continue  # Try next URL
        except Exception as e:
            log.warning(f"[BRAIN] {source} request error during streaming: {e}")
            if source == "local":
                yield f"[Error: {e}]"
                return
            continue  # Try next URL
    else:
        # All URLs failed
        yield "[Error: Cannot reach any Ollama endpoint.]"
        return

    if buffer.strip():
        yield buffer.strip()


# ── LLM tool_call generation ONLY (single call) ─────────────────────────


def run_agent(
    messages: list,
    tools: list,
    on_text: Callable = None,
    abort_event: threading.Event = None,
    inject_context: bool = False,
) -> tuple[str, list, list]:
    """
    Single LLM inference call. Returns (text, updated_messages, tool_calls).
    brain.py ONLY does LLM inference - jarvis.py handles execution loop.

    Improvements:
    - Better error context in messages
    - Clearer tool_call formatting for LLM
    - Only inject reliability context when needed (prevent pollution)
    """
    if abort_event and abort_event.is_set():
        log.info("[BRAIN] Aborted by user")
        return "", messages, []

    log.info("[BRAIN] LLM inference call")

    # Track injected message indices for cleanup after API call
    injected_indices = []
    # FIX 12: Insert hint as system message before last user message, not append
    if messages and messages[-1].get("role") == "tool":
        last_result = messages[-1].get("content", "")
        if "FAILED" in last_result or "Error" in last_result:
            hint = {
                "role": "system",
                "content": "Previous tool call failed. Consider: 1) Check parameter values, 2) Try alternative approach, 3) Verify tool is appropriate for the task.",
            }
            insert_idx = len(messages) - 1
            while insert_idx > 0 and messages[insert_idx].get("role") != "user":
                insert_idx -= 1
            if insert_idx >= 0:
                messages.insert(insert_idx, hint)
                injected_indices.append(insert_idx)

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "tools": tools,
        "options": {
            "temperature": config.OLLAMA_TEMPERATURE,
            "num_predict": config.AGENT_MAX_TOKENS,
        },
    }

    # FIX 5: Try cloud first, then fallback to local Ollama
    urls_to_try = [
        (
            config.OLLAMA_CLOUD_URL,
            {
                "Authorization": f"Bearer {config.OLLAMA_API_KEY}",
                "Content-Type": "application/json",
            },
            "cloud",
        ),
        ("http://localhost:11434/api/chat", {}, "local"),  # No auth for local
    ]

    for url, hdrs, source in urls_to_try:
        try:
            log.info(f"[BRAIN] Trying {source} Ollama endpoint: {url}")
            resp = requests.post(
                url,
                json=payload,
                headers=hdrs,
                timeout=config.OLLAMA_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            log.info(f"[BRAIN] Successfully connected to {source} Ollama")
            break
        except requests.exceptions.HTTPError as e:
            log.warning(f"[BRAIN] {source} HTTP error: {e}")
            if source == "local":
                if on_text:
                    on_text(f"I hit an API error. HTTP {e.response.status_code}.")
                return "", messages, []
            continue  # Try next URL
        except requests.exceptions.ConnectionError as e:
            log.warning(f"[BRAIN] {source} connection error: {e}")
            if source == "local":
                if on_text:
                    on_text("I lost connection to the language model.")
                return "", messages, []
            continue  # Try next URL
        except Exception as e:
            log.warning(f"[BRAIN] {source} request error: {e}")
            if source == "local":
                if on_text:
                    on_text("I lost connection to the language model.")
                return "", messages, []
            continue  # Try next URL
    else:
        # All URLs failed
        log.error("[BRAIN] All Ollama endpoints failed")
        if on_text:
            on_text("I cannot reach the language model. Please check your connection.")
        return "", messages, []

    msg = data.get("message", {})
    if not msg:
        log.error(f"[BRAIN] Unexpected response structure: {data}")
        if on_text:
            on_text("I received an invalid response from the language model.")
        return "", messages, []

    text = (msg.get("content") or "").strip()
    tool_calls = msg.get("tool_calls") or []

    if text and on_text:
        on_text(text)

    # Append assistant message with tool_calls if present
    assistant_msg = {"role": "assistant", "content": text}
    if tool_calls:
        # Improve: Log tool call details for debugging
        for tc in tool_calls:
            fn = tc.get("function", {})
            log.info(
                f"[BRAIN] Generated tool_call: {fn.get('name', '')} with {fn.get('arguments', {})}"
            )
        assistant_msg["tool_calls"] = tool_calls

    messages.append(assistant_msg)

    # Cleanup: Remove injected context/hint messages to prevent accumulation
    if injected_indices:
        # Sort in reverse order to avoid index shifting
        for idx in sorted(injected_indices, reverse=True):
            if idx < len(messages):
                removed = messages.pop(idx)
                log.debug(f"[BRAIN] Removed injected message: {removed.get('content', '')[:50]}...")

    return text, messages, tool_calls
