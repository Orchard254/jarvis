"""
Unified memory and scheduling tool.
Actions: store, recall, forget, search, summary, schedule, cancel, list
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def memory(
    action: str = "recall",
    key: str | None = None,
    value: Any = None,
    query: str | None = None,
    command: str | None = None,
    when: str | None = None,
    task_id: str | None = None,
    limit: int = 10,
) -> dict:
    if action in ("store", "recall", "forget", "search", "summary"):
        return _memory_op(action, key, value, query, limit)
    elif action in ("schedule", "cancel", "list"):
        return _schedule_op(action, command, when, task_id)
    return {"success": False, "error": f"Unknown memory action: {action}"}


def _memory_op(
    action: str, key: str | None, value: Any, query: str | None, limit: int,
) -> dict:
    try:
        from tools.memory_tool import memory as memory_tool
        kwargs = {"action": action, "limit": limit}
        if key:
            kwargs["key"] = key
        if value is not None:
            kwargs["value"] = value
        if query:
            kwargs["query"] = query
        return memory_tool(**kwargs)
    except Exception as e:
        return {"success": False, "error": f"Memory {action} failed: {e}"}


def _schedule_op(
    action: str, command: str | None, when: str | None, task_id: str | None,
) -> dict:
    try:
        from tools.schedule_tool import schedule as schedule_tool
        kwargs = {"action": action}
        if command:
            kwargs["command"] = command
        if when:
            kwargs["when"] = when
        if task_id:
            kwargs["task_id"] = task_id
        return schedule_tool(**kwargs)
    except Exception as e:
        return {"success": False, "error": f"Schedule {action} failed: {e}"}
