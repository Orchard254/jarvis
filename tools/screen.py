"""
Unified perception tool.
Actions: capture, find, tree, query, watch, ocr

Uses Windows UIA for deterministic element finding (no OCR fragility)
and falls back to vision model / OCR when UIA is insufficient.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from tools import uia_utils

logger = logging.getLogger(__name__)


def screen(
    action: str = "capture",
    text: str | None = None,
    question: str | None = None,
    condition: str | None = None,
    region: dict | None = None,
    window_title: str | None = None,
    timeout_seconds: int = 30,
    check_interval: int = 5,
    click: bool = False,
    max_depth: int = 3,
) -> dict:
    if action == "capture":
        return _capture(region, window_title)
    elif action == "find":
        return _find(text, timeout_seconds, click, window_title)
    elif action == "tree":
        return _tree(window_title, max_depth)
    elif action == "query":
        return _query(question, region)
    elif action == "watch":
        return _watch(condition, timeout_seconds, check_interval, region)
    elif action == "ocr":
        return _ocr(region)
    return {"success": False, "error": f"Unknown screen action: {action}"}


def _capture(region: dict | None = None, window_title: str | None = None) -> dict:
    """Take a screenshot. Delegates to existing capture_screen logic."""
    try:
        from tools.capture_screen import capture_screen
        return capture_screen(region=region, window_title=window_title)
    except Exception as e:
        return {"success": False, "error": f"Capture failed: {e}"}


def _find(text: str | None, timeout: float, do_click: bool, window_title: str | None = None) -> dict:
    """Find a UI element by text using UIA. Falls back to OCR if UIA fails.

    When window_title is provided, scopes the UIA search to that window.
    """
    if not text:
        return {"success": False, "error": "text required for find action"}

    if uia_utils.available():
        result = uia_utils.get_element_by_text(
            text, timeout=timeout, click=do_click, window_title=window_title,
        )
        if result["success"]:
            return result
        logger.info(f"UIA find failed for '{text}', trying OCR fallback")

    try:
        from tools.find_on_screen import find_on_screen
        return find_on_screen(description=text, click=do_click)
    except Exception as e:
        return {"success": False, "error": f"Could not find '{text}': {e}"}


def _tree(window_title: str | None, max_depth: int) -> dict:
    """Get the UIA accessibility tree."""
    if not uia_utils.available():
        return {"success": False, "error": "UIA not available for tree generation"}
    return uia_utils.get_tree(window_title, max_depth)


def _query(question: str | None, region: dict | None) -> dict:
    """Ask a vision model about the screen."""
    if not question:
        return {"success": False, "error": "question required for query action"}
    try:
        from tools.vision_query import vision_query
        return vision_query(question=question, region=region)
    except Exception as e:
        return {"success": False, "error": f"Vision query failed: {e}"}


def _watch(condition: str | None, timeout: int, interval: int, region: dict | None) -> dict:
    """Monitor screen until condition is met or timeout."""
    if not condition:
        return {"success": False, "error": "condition required for watch action"}
    try:
        from tools.watch_screen import watch_screen
        return watch_screen(
            condition=condition,
            timeout_seconds=timeout,
            check_interval=interval,
            region=region,
        )
    except Exception as e:
        return {"success": False, "error": f"Watch failed: {e}"}


def _ocr(region: dict | None) -> dict:
    """Read text from screen region using OCR."""
    try:
        from tools.vision_query import vision_query
        q = "Read all text visible in this region exactly as written"
        return vision_query(question=q, region=region)
    except Exception as e:
        return {"success": False, "error": f"OCR failed: {e}"}
