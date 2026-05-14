"""
Cloud LLM client wrapper. Uses /api/chat with native tool-calling.
Handles retries, timeouts, and health checks.
"""

import datetime
import json
import logging
import random
import time

import requests
from settings import (
    FALLBACK_TO_LOCAL,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT,
    OLLAMA_API_KEY,
    OLLAMA_LOCAL_MODEL,
    OLLAMA_LOCAL_URL,
    OLLAMA_MAX_TOKENS,
)

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    pass


# Simple tracker for mock LLM
_mock_tools_called = False
# Track last user message to reset state for new commands
_last_user_cmd = ""

# For testing: always use mock LLM
FORCE_MOCK_LLM = False


def chat(
    messages: list[dict],
    tools: list[dict] = None,
    model: str = None,
    temperature: float = 0.2,
    max_retries: int = 3,
    think: bool = None,
    thinking_budget: int = None,
    reasoning_effort: str = None,
) -> dict:
    """
    think=True   : enable gpt-oss chain-of-thought reasoning (recommended for
                   multi-step / complex tasks).  Falls back silently if the
                   model does not support it.
    thinking_budget: max tokens the model may spend thinking (default from
                     settings.THINKING_BUDGET).
    reasoning_effort: "low" | "medium" | "high" — maps to the model's internal
                      effort level.  Higher = better reasoning, slower + costlier.
    """
    from settings import THINKING_ENABLED, THINKING_BUDGET, REASONING_EFFORT

    global _mock_tools_called, _last_user_cmd

    if FORCE_MOCK_LLM:
        logger.info("Using mock LLM for testing")
        return _mock_chat(messages, tools)

    headers = {"Content-Type": "application/json"}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    # Resolve thinking parameters — caller overrides settings defaults
    use_think = think if think is not None else THINKING_ENABLED
    budget = thinking_budget if thinking_budget is not None else THINKING_BUDGET
    effort = reasoning_effort if reasoning_effort is not None else REASONING_EFFORT

    payload = {
        "model": model or LLM_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": OLLAMA_MAX_TOKENS,
    }
    if tools:
        payload["tools"] = tools

    # ── gpt-oss 120b thinking / reasoning parameters ──────────────────────────
    # These are passed as top-level keys; models that don't support them
    # will ignore them silently.
    if use_think:
        payload["think"] = True
        payload["thinking_budget"] = budget
    if effort:
        payload["reasoning_effort"] = effort

    # Determine the correct endpoint - use /chat/completions for OpenAI-compatible API
    base_url = LLM_BASE_URL.rstrip("/")
    if "/api/chat" in base_url or "/v1" in base_url:
        endpoint = base_url
    else:
        endpoint = f"{base_url}/chat/completions"

    # Exponential backoff retry logic
    retry_count = 0
    while retry_count <= max_retries:
        try:
            resp = requests.post(
                endpoint, json=payload, headers=headers, timeout=LLM_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            # Handle OpenAI-compatible response format
            if "choices" in data:
                choice = data["choices"][0]
                msg = choice.get("message", {})
                tool_calls_raw = msg.get("tool_calls") or []
                # Extract thinking content if present (OpenAI reasoning format)
                thinking = msg.get("reasoning_content") or msg.get("thinking") or ""
            else:
                # Fallback to original Ollama format
                msg = data.get("message", {})
                tool_calls_raw = msg.get("tool_calls") or []
                # Ollama native thinking field
                thinking = msg.get("thinking") or ""

            if thinking:
                logger.debug(f"[thinking] {thinking[:200]}{'...' if len(thinking) > 200 else ''}")

            tool_calls = []
            for tc in tool_calls_raw:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append(
                    {
                        "id": tc.get("id", f"call_{len(tool_calls)}"),
                        "function": {"name": fn.get("name", ""), "arguments": args},
                    }
                )

            return {
                "content": (msg.get("content") or "").strip(),
                "tool_calls": tool_calls if tool_calls else None,
                "model": data.get("model", model or LLM_MODEL),
                "done": True,
            }

        except Exception as e:
            retry_count += 1
            if retry_count > max_retries:
                logger.error(f"Cloud LLM unavailable after {max_retries} retries: {e}")
                if FALLBACK_TO_LOCAL:
                    logger.info("Falling back to local Ollama instance...")
                    try:
                        local_payload = {
                            "model": OLLAMA_LOCAL_MODEL,
                            "messages": messages,
                            "stream": False,
                            "temperature": temperature,
                        }
                        if tools:
                            local_payload["tools"] = tools
                        local_base_url = OLLAMA_LOCAL_URL.rstrip("/")
                        if "/api/chat" in local_base_url or "/v1" in local_base_url:
                            local_endpoint = local_base_url
                        else:
                            local_endpoint = f"{local_base_url}/chat/completions"
                        resp = requests.post(
                            local_endpoint,
                            json=local_payload,
                            headers={"Content-Type": "application/json"},
                            timeout=LLM_TIMEOUT,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        if "choices" in data:
                            choice = data["choices"][0]
                            msg = choice.get("message", {})
                            tool_calls_raw = msg.get("tool_calls") or []
                        else:
                            msg = data.get("message", {})
                            tool_calls_raw = msg.get("tool_calls") or []
                        tool_calls = []
                        for tc in tool_calls_raw:
                            fn = tc.get("function", {})
                            args = fn.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except json.JSONDecodeError:
                                    args = {}
                            tool_calls.append(
                                {
                                    "id": tc.get("id", f"call_{len(tool_calls)}"),
                                    "function": {
                                        "name": fn.get("name", ""),
                                        "arguments": args,
                                    },
                                }
                            )
                        return {
                            "content": (msg.get("content") or "").strip(),
                            "tool_calls": tool_calls if tool_calls else None,
                            "model": data.get("model", OLLAMA_LOCAL_MODEL),
                            "done": True,
                        }
                    except Exception as local_e:
                        logger.warning(f"Local fallback also failed: {local_e}")
                logger.warning("Falling back to mock LLM")
                return _mock_chat(messages, tools)
            wait_time = 2 ** (retry_count - 1)
            # BUG FIX: add ±25% jitter to prevent thundering-herd retries
            # when multiple agent threads hit a transient 500 simultaneously.
            jitter = random.uniform(-0.25 * wait_time, 0.25 * wait_time)
            wait_total = max(0.1, wait_time + jitter)
            # Log payload size on server errors to aid future diagnosis
            if "500" in str(e) or "Server Error" in str(e):
                payload_kb = len(json.dumps(payload)) / 1024
                logger.warning(
                    f"Request failed (attempt {retry_count}/{max_retries}), "
                    f"retrying in {wait_total:.1f}s (payload={payload_kb:.1f}KB): {e}"
                )
            else:
                logger.warning(
                    f"Request failed (attempt {retry_count}/{max_retries}), "
                    f"retrying in {wait_total:.1f}s: {e}"
                )
            deadline = time.monotonic() + wait_total
            while time.monotonic() < deadline:
                time.sleep(min(0.1, deadline - time.monotonic()))


def _mock_chat(messages: list[dict], tools: list[dict] = None) -> dict:
    global _mock_tools_called, _last_user_cmd
    logger.info(
        f"_mock_chat called, _mock_tools_called={_mock_tools_called}, _last_user_cmd={_last_user_cmd}"
    )

    last_user_msg = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    last_user_msg = last_user_msg.strip()

    # Strip any leading prefixes like "1. ", "2. ", etc.
    import re

    last_user_msg = re.sub(r"^\d+\.\s*", "", last_user_msg).strip()

    # Reset for new commands
    if last_user_msg != _last_user_cmd:
        logger.info(f"  New command detected, resetting state: {last_user_msg}")
        _mock_tools_called = False
        _last_user_cmd = last_user_msg

    if _mock_tools_called:
        logger.info("  Returning final response!")
        return {
            "content": "Done! The task is complete.",
            "tool_calls": None,
            "model": "mock_llm",
            "done": True,
        }

    tool_calls = None
    content = ""
    lower_msg = last_user_msg.lower()

    if "time" in lower_msg:
        current_time = datetime.datetime.now().strftime("%I:%M %p on %B %d, %Y")
        content = f"The current time is {current_time}."
    elif "open notepad" in lower_msg:
        tool_calls = [
            {
                "id": "call_0",
                "function": {
                    "name": "execute_code",
                    "arguments": {
                        "code": "import subprocess; subprocess.Popen('notepad.exe')",
                        "language": "python",
                    },
                },
            }
        ]
        _mock_tools_called = True
    elif "what windows are open" in lower_msg:
        tool_calls = [
            {"id": "call_0", "function": {"name": "read_pc_state", "arguments": {}}}
        ]
        _mock_tools_called = True
    elif "notify" in lower_msg:
        tool_calls = [
            {
                "id": "call_0",
                "function": {
                    "name": "notify_user",
                    "arguments": {
                        "message": "Test notification received!",
                        "urgency": "normal",
                    },
                },
            }
        ]
        _mock_tools_called = True
    elif "write" in lower_msg and "jarvis_test.txt" in lower_msg:
        import os

        desktop = os.path.expanduser("~/Desktop")
        test_file = os.path.join(desktop, "jarvis_test.txt")
        tool_calls = [
            {
                "id": "call_0",
                "function": {
                    "name": "write_file",
                    "arguments": {"path": test_file, "content": "JARVIS is live"},
                },
            }
        ]
        _mock_tools_called = True
    elif "schedule" in lower_msg:
        content = "Task scheduled successfully! The schedule has been added to the autonomous task queue."
    else:
        content = "I understand you want to do something! Since Ollama isn't running, I'm in test mode. Try asking 'what time is it', 'open notepad', 'what windows are open', 'notify me with a test', 'write to jarvis_test.txt', or 'schedule a task'."

    logger.info(f"  Returning tool_calls: {tool_calls is not None}")
    return {
        "content": content,
        "tool_calls": tool_calls,
        "model": "mock_llm",
        "done": True,
    }


def chat_stream(
    messages: list[dict],
    tools: list[dict] = None,
    model: str = None,
    temperature: float = 0.2,
    print_chunks: bool = True,
    think: bool = None,
    thinking_budget: int = None,
    reasoning_effort: str = None,
) -> dict:
    """
    Stream response tokens from the LLM.
    Supports think/thinking_budget/reasoning_effort — same as chat().
    Falls back to the blocking chat() on any exception.
    Returns: {"content": str, "tool_calls": list | None, "done": True}
    """
    if FORCE_MOCK_LLM:
        return _mock_chat(messages, tools)

    from settings import THINKING_ENABLED, THINKING_BUDGET, REASONING_EFFORT

    use_think = think if think is not None else THINKING_ENABLED
    budget = thinking_budget if thinking_budget is not None else THINKING_BUDGET
    effort = reasoning_effort if reasoning_effort is not None else REASONING_EFFORT

    try:
        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

        payload = {
            "model": model or LLM_MODEL,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": OLLAMA_MAX_TOKENS,
        }
        if tools:
            payload["tools"] = tools

        if use_think:
            payload["think"] = True
            payload["thinking_budget"] = budget
        if effort:
            payload["reasoning_effort"] = effort

        base_url = LLM_BASE_URL.rstrip("/")
        if "/api/chat" in base_url or "/v1" in base_url:
            endpoint = base_url
        else:
            endpoint = f"{base_url}/chat/completions"

        content_parts: list[str] = []
        # index -> {"id": str, "name": str, "arguments": str}
        tc_accumulator: dict[int, dict] = {}
        is_openai_format: bool | None = None

        resp = requests.post(
            endpoint, json=payload, headers=headers, timeout=LLM_TIMEOUT, stream=True
        )
        resp.raise_for_status()

        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            # OpenAI SSE lines start with "data: "
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if line.startswith("data:"):
                line = line[5:].strip()
            if line in ("", "[DONE]"):
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Auto-detect response format on first real chunk
            if is_openai_format is None:
                is_openai_format = "choices" in data

            if is_openai_format:
                choice = (data.get("choices") or [{}])[0]
                delta = choice.get("delta", {})
                finish = choice.get("finish_reason")

                # Accumulate content
                chunk = delta.get("content") or ""
                if chunk:
                    content_parts.append(chunk)
                    if print_chunks:
                        print(chunk, end="", flush=True)

                # Accumulate tool_call deltas
                for tc_delta in delta.get("tool_calls") or []:
                    idx = tc_delta.get("index", 0)
                    if idx not in tc_accumulator:
                        tc_accumulator[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.get("id"):
                        tc_accumulator[idx]["id"] = tc_delta["id"]
                    fn = tc_delta.get("function", {})
                    if fn.get("name"):
                        tc_accumulator[idx]["name"] += fn["name"]
                    if fn.get("arguments"):
                        tc_accumulator[idx]["arguments"] += fn["arguments"]

                if finish in ("stop", "tool_calls", "length"):
                    break

            else:
                # Ollama native format
                msg = data.get("message", {})
                chunk = msg.get("content") or ""
                if chunk:
                    content_parts.append(chunk)
                    if print_chunks:
                        print(chunk, end="", flush=True)

                # Ollama native tool_calls appear on the final done=True chunk
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    idx = len(tc_accumulator)
                    tc_accumulator[idx] = {
                        "id": tc.get("id", f"call_{idx}"),
                        "name": fn.get("name", ""),
                        "arguments": json.dumps(args),  # re-encode for unified path
                    }

                if data.get("done"):
                    break

        if print_chunks and content_parts:
            print()  # final newline

        # Convert accumulator to tool_calls list
        tool_calls: list[dict] = []
        for idx in sorted(tc_accumulator.keys()):
            entry = tc_accumulator[idx]
            args_raw = entry["arguments"]
            try:
                args = json.loads(args_raw) if args_raw else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                {
                    "id": entry["id"] or f"call_{idx}",
                    "function": {"name": entry["name"], "arguments": args},
                }
            )

        return {
            "content": "".join(content_parts).strip(),
            "tool_calls": tool_calls if tool_calls else None,
            "done": True,
        }

    except Exception as stream_err:
        logger.warning(
            f"chat_stream: streaming failed ({stream_err}) — falling back to chat()"
        )
        return chat(messages, tools, model, temperature)


def health_check() -> bool:
    try:
        base_url = LLM_BASE_URL.rstrip("/")
        # Try OpenAI-compatible health check first
        try:
            list_url = (
                f"{base_url}/models" if "/v1" in base_url else f"{base_url}/api/tags"
            )
            return requests.get(list_url, timeout=5).status_code == 200
        except Exception:
            # Fallback to simple ping
            return requests.get(base_url, timeout=5).status_code in [200, 401, 404, 405]
    except Exception:
        return False


def list_models() -> list:
    try:
        base_url = LLM_BASE_URL.rstrip("/")
        list_url = f"{base_url}/models" if "/v1" in base_url else f"{base_url}/api/tags"
        resp = requests.get(list_url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if "models" in data:
            return [m["id"] for m in data["models"]]
        elif "data" in data:
            return [m["id"] for m in data["data"]]
        return []
    except Exception:
        return []
