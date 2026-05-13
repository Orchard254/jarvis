"""
Unified window management tool.
Actions: open, close, focus, list, info, resize, minimize, maximize, restore

open action internally checks if app is already running (focuses if so),
finds the executable path, launches, waits for window, and focuses.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def window(
    action: str = "list",
    app_name: str | None = None,
    window_title: str | None = None,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    params: dict | None = None,
) -> dict:
    if action == "open":
        return _open(app_name)
    elif action in ("close", "focus", "minimize", "maximize", "restore"):
        return _control(action, window_title, params)
    elif action == "resize":
        return _control("resize", window_title, params or {})
    elif action == "move":
        return _control("move", window_title, params or {})
    elif action == "list":
        return _list_all()
    elif action == "info":
        return _info(window_title)
    return {"success": False, "error": f"Unknown window action: {action}"}


def _open(app_name: str | None) -> dict:
    if not app_name:
        return {"success": False, "error": "app_name required for open action"}
    try:
        from tools.open_app import open_app
        return open_app(app_name)
    except Exception as e:
        return {"success": False, "error": f"Could not open '{app_name}': {e}"}


def _control(
    action: str,
    window_title: str | None,
    params: dict | None,
) -> dict:
    if action in ("focus", "close", "minimize", "maximize", "restore") and not window_title:
        return {"success": False, "error": f"window_title required for {action} action"}
    try:
        from tools.control_window import control_window
        return control_window(window_title=window_title or "", action=action, params=params or {})
    except Exception as e:
        return {"success": False, "error": f"Window {action} failed: {e}"}


def _list_all() -> dict:
    try:
        from tools.control_window import control_window
        return control_window(window_title="", action="list")
    except Exception as e:
        return {"success": False, "error": f"List windows failed: {e}"}


def _info(window_title: str | None) -> dict:
    if not window_title:
        return {"success": False, "error": "window_title required for info action"}
    try:
        from tools.control_window import control_window
        return control_window(window_title=window_title, action="info")
    except Exception as e:
        return {"success": False, "error": f"Window info failed: {e}"}
