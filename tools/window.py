"""
Unified window & desktop management tool.
Actions: open, close, focus, list, minimize, maximize, state

open action internally checks if app is already running (focuses if so),
finds the executable path, launches, waits for window, and focuses.
state action returns a live snapshot of open windows and running processes.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def window(
    action: str = "list",
    app_name: str | None = None,
    window_title: str | None = None,
) -> dict:
    if action == "open":
        return _open(app_name)
    elif action in ("close", "focus", "minimize", "maximize"):
        return _control(action, window_title)
    elif action == "list":
        return _list_all()
    elif action == "state":
        return _state()
    return {"success": False, "error": f"Unknown window action: {action}"}


def _open(app_name: str | None) -> dict:
    if not app_name:
        return {"success": False, "error": "app_name required for open action"}
    try:
        from tools.open_app import open_app
        return open_app(app_name)
    except Exception as e:
        return {"success": False, "error": f"Could not open '{app_name}': {e}"}


def _control(action: str, window_title: str | None) -> dict:
    if not window_title:
        return {"success": False, "error": f"window_title required for {action} action"}
    try:
        from tools.control_window import control_window
        return control_window(window_title=window_title, action=action, params={})
    except Exception as e:
        return {"success": False, "error": f"Window {action} failed: {e}"}


def _list_all() -> dict:
    try:
        from tools.control_window import control_window
        return control_window(window_title="", action="list")
    except Exception as e:
        return {"success": False, "error": f"List windows failed: {e}"}


def _state() -> dict:
    """Live snapshot of open windows, running processes, focused app."""
    try:
        from tools.read_pc_state import read_pc_state
        return read_pc_state()
    except Exception as e:
        return {"success": False, "error": f"State check failed: {e}"}
