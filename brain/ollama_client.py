"""
Cloud LLM client wrapper. Uses /api/chat with native tool-calling.
Handles retries, timeouts, and health checks.
"""

import datetime
import json
import logging
import random
import sys
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


def _parse_message(msg: dict) -> str:
    return (msg.get("content") or "").strip()


def _parse_thinking(msg: dict) -> str:
    return msg.get("reasoning_content") or msg.get("thinking") or ""


def _parse_tool_calls(tool_calls_raw: list) -> list[dict]:
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
    return tool_calls


def _parse_response(data: dict) -> tuple:
    if "choices" in data and data["choices"]:
        choice = data["choices"][0]
        msg = choice.get("message", {})
        tool_calls_raw = msg.get("tool_calls") or []
        thinking = _parse_thinking(msg)
    else:
        msg = data.get("message", {})
        tool_calls_raw = msg.get("tool_calls") or []
        thinking = _parse_thinking(msg)

    if thinking:
        logger.debug(f"[thinking] {thinking[:200]}{chr(46)*3 if len(thinking) > 200 else ''}")

    content = _parse_message(msg)
    tool_calls = _parse_tool_calls(tool_calls_raw)
    model = data.get("model", "")
    return content, tool_calls, thinking, model


def _build_payload(
    messages: list[dict],
    model: str,
    temperature: float = 0.2,
    stream: bool = False,
    tools: list[dict] = None,
    use_think: bool = None,
    budget: int = None,
    effort: str = None,
) -> dict:
    payload = {
        "model": model or LLM_MODEL,
        "messages": messages,
        "stream": stream,
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
    return payload


def _resolve_endpoint(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if "/api/chat" in base_url or "/v1" in base_url:
        return base_url
    return f"{base_url}/chat/completions"


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

    endpoint = _resolve_endpoint(LLM_BASE_URL)
    retry_count = 0
    while retry_count < max_retries:
        try:
            resp = requests.post(
                endpoint, json=payload, headers=headers, timeout=LLM_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            content, tool_calls, _, model_raw = _parse_response(data)
            return {
                "content": content,
                "tool_calls": tool_calls if tool_calls else None,
                "model": model_raw or model or LLM_MODEL,
                "done": True,
            }

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                logger.error(f"Cloud LLM unavailable after {max_retries} retries: {e}")
                if FALLBACK_TO_LOCAL:
                    logger.info("Falling back to local Ollama instance...")
                    try:
                        local_payload = _build_payload(
                            messages, model=OLLAMA_LOCAL_MODEL, temperature=temperature, tools=tools
                        )
                        local_endpoint = _resolve_endpoint(OLLAMA_LOCAL_URL)
                        resp = requests.post(
                            local_endpoint,
                            json=local_payload,
                            headers={"Content-Type": "application/json"},
                            timeout=LLM_TIMEOUT,
                        )
                        resp.raise_for_status()
                        content, tool_calls, _, model_raw = _parse_response(resp.json())
                        return {
                            "content": content,
                            "tool_calls": tool_calls if tool_calls else None,
                            "model": model_raw or OLLAMA_LOCAL_MODEL,
                            "done": True,
                        }
                    except Exception as local_e:
                        logger.error(f"Local fallback also failed: {local_e}")
                raise OllamaError(f"LLM unavailable after {max_retries} retries and fallback exhausted")
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

