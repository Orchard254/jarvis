"""
Unified system state tool.
Actions: state, search_app, search_file, hardware

Provides live desktop state snapshots and searches installed apps/files.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def system(
    action: str = "state",
    query: str | None = None,
    type: str | None = None,
) -> dict:
    if action == "state":
        return _state()
    elif action in ("search_app", "search_file"):
        return _search(query, action.replace("search_", ""))
    elif action == "hardware":
        return _hardware()
    return {"success": False, "error": f"Unknown system action: {action}"}


def _state() -> dict:
    """Live snapshot of open windows, running processes, focused app."""
    try:
        from tools.read_pc_state import read_pc_state
        return read_pc_state()
    except Exception as e:
        return {"success": False, "error": f"State check failed: {e}"}


def _search(query: str | None, search_type: str) -> dict:
    """Search installed apps or files."""
    if not query:
        return {"success": False, "error": "query required for search action"}
    try:
        from tools.query_pc_index import query_pc_index
        return query_pc_index(query=query, type=search_type)
    except Exception as e:
        return {"success": False, "error": f"Search failed: {e}"}


def _hardware() -> dict:
    """Get hardware information: CPU, RAM, disk."""
    try:
        import psutil
        import shutil
        ram = psutil.virtual_memory()
        disk = shutil.disk_usage("C:\\")
        cpu = psutil.cpu_percent(interval=0.5)
        return {
            "success": True,
            "cpu_percent": cpu,
            "ram_total_gb": round(ram.total / 1e9, 1),
            "ram_free_gb": round(ram.available / 1e9, 1),
            "ram_percent": ram.percent,
            "disk_total_gb": round(disk.total / 1e9, 1),
            "disk_free_gb": round(disk.free / 1e9, 1),
        }
    except Exception as e:
        return {"success": False, "error": f"Hardware info failed: {e}"}
