"""
Build Jarvis chat history from episodic memory (command/response pairs).
"""

from __future__ import annotations

import json
import logging

from settings import (
    CONVERSATION_HISTORY_LIMIT,
    CONVERSATION_MESSAGE_MAX_CHARS,
    WORKING_MEMORY_MAX_MESSAGES,
)

logger = logging.getLogger(__name__)


def _truncate(text: str, limit: int = CONVERSATION_MESSAGE_MAX_CHARS) -> str:
    if not text or len(text) <= limit:
        return text or ""
    return text[: limit - 3] + "..."


def _response_text_from_episode(episode: dict) -> str:
    """Extract assistant-visible text from a response episode."""
    tr = episode.get("tool_result")
    if isinstance(tr, str):
        try:
            tr = json.loads(tr)
        except (json.JSONDecodeError, TypeError):
            if tr.strip():
                return _truncate(tr)
    if isinstance(tr, dict):
        for key in ("response", "message", "summary", "content"):
            val = tr.get(key)
            if isinstance(val, str) and val.strip():
                return _truncate(val.strip())
    if episode.get("success"):
        cmd = (episode.get("command_text") or "").strip()
        if cmd:
            return _truncate(f"Completed: {cmd[:200]}")
        return "Done."
    return ""


def episodes_to_chat_messages(episodes: list[dict]) -> list[dict]:
    """
    Convert episodic rows into OpenAI-style user/assistant messages.
    Pairs each ``command`` event with the next ``response`` in chronological order.
    """
    messages: list[dict] = []
    pending_user: str | None = None

    for ev in episodes:
        et = ev.get("event_type")
        if et == "command":
            cmd = (ev.get("command_text") or "").strip()
            if cmd:
                pending_user = cmd
        elif et == "response" and pending_user:
            assistant = _response_text_from_episode(ev)
            if assistant:
                messages.append({"role": "user", "content": _truncate(pending_user)})
                messages.append({"role": "assistant", "content": assistant})
            pending_user = None

    cap = max(
        2,
        min(
            WORKING_MEMORY_MAX_MESSAGES or 20,
            max(CONVERSATION_HISTORY_LIMIT * 2, 2),
        ),
    )
    return messages[-cap:]


def merge_histories(
    persisted: list[dict],
    in_memory: list[dict],
) -> list[dict]:
    """
    Merge episodic history with the orchestrator's in-session deque.
    In-memory tail wins when both end with the same user turn.
    """
    if not persisted:
        return list(in_memory)
    if not in_memory:
        return list(persisted)

    # If session continued in RAM, append only messages not already covered
    if len(in_memory) >= 2 and len(persisted) >= 2:
        if (
            in_memory[0].get("content") == persisted[-2].get("content")
            and in_memory[1].get("content") == persisted[-1].get("content")
        ):
            return persisted + list(in_memory[2:])

    return persisted + list(in_memory)
