"""
Unified memory tool.
Actions: store, recall, search
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
    limit: int = 10,
) -> dict:
    if action in ("store", "recall", "search"):
        return _memory_op(action, key, value, query, limit)
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
