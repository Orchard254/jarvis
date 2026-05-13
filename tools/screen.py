"""
Unified perception tool.
Actions: capture, find, tree, query, ocr, elements

Uses Windows UIA for deterministic element finding (no OCR fragility)
and falls back to vision model / OCR when UIA is insufficient.
The 'elements' action merges UIA + OCR to list all interactive elements
with coordinates — works on any app.
"""

from __future__ import annotations

import logging
from typing import Any

from tools import uia_utils

logger = logging.getLogger(__name__)


def screen(
    action: str = "capture",
    text: str | None = None,
    question: str | None = None,
    region: dict | None = None,
    window_title: str | None = None,
    timeout_seconds: int = 5,
    click: bool = False,
    max_depth: int = 3,
    grid: bool = False,
    grid_size: int = 100,
) -> dict:
    if action == "capture":
        return _capture(region, window_title, grid, grid_size)
    elif action == "find":
        return _find(text, timeout_seconds, click, window_title)
    elif action == "tree":
        return _tree(window_title, max_depth)
    elif action == "query":
        return _query(question, region)
    elif action == "ocr":
        return _ocr(region)
    elif action == "elements":
        return _elements(window_title, max_depth)
    return {"success": False, "error": f"Unknown screen action: {action}"}


def _capture(
    region: dict | None = None,
    window_title: str | None = None,
    grid: bool = False,
    grid_size: int = 100,
) -> dict:
    """Take a screenshot. Optionally overlay a coordinate grid."""
    try:
        from tools.capture_screen import capture_screen
        return capture_screen(
            region=region, window_title=window_title,
            grid=grid, grid_size=grid_size,
        )
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



def _ocr(region: dict | None) -> dict:
    """Read text from screen region using OCR."""
    try:
        from tools.vision_query import vision_query
        q = "Read all text visible in this region exactly as written"
        return vision_query(question=q, region=region)
    except Exception as e:
        return {"success": False, "error": f"OCR failed: {e}"}


def _elements(window_title: str | None, max_depth: int) -> dict:
    """List all interactive elements with coordinates from UIA + OCR.

    Combines UIA accessibility tree (for native app elements) with OCR
    text detection (for elements UIA can't see, like web content). Returns
    a unified list of clickable elements with names, types, and bounding
    boxes the LLM can use to decide what to click.
    """
    elements: list[dict] = []
    sources_used: list[str] = []

    # ── 1. UIA elements (native apps) ────────────────────────────────────
    if uia_utils.available():
        try:
            import uiautomation as uia

            root = uia.GetRootControl()
            if window_title:
                root = uia_utils._find_window(window_title)
                if root is None:
                    return {"success": False, "error": f"Window not found: {window_title}"}

            interactive_types = {
                "ButtonControl", "EditControl", "ComboBoxControl",
                "CheckBoxControl", "RadioButtonControl", "HyperlinkControl",
                "MenuItemControl", "TabItemControl", "ListItemControl",
                "TreeItemControl", "SliderControl", "ToggleSwitchControl",
            }

            def _walk_interactive(control, depth=0):
                if depth > max_depth:
                    return
                try:
                    ctype = uia_utils._safe(control, "ControlTypeName", "") or ""
                    name = uia_utils._safe(control, "Name", "") or ""
                    is_enabled = uia_utils._safe(control, "IsEnabled", True)

                    if ctype in interactive_types and name and is_enabled:
                        rect = uia_utils._safe(control, "BoundingRectangle")
                        bounds = None
                        if rect:
                            try:
                                bounds = {
                                    "left": rect.left,
                                    "top": rect.top,
                                    "width": rect.width(),
                                    "height": rect.height(),
                                    "center_x": rect.left + rect.width() // 2,
                                    "center_y": rect.top + rect.height() // 2,
                                }
                            except Exception:
                                pass

                        elements.append({
                            "name": name,
                            "type": ctype.replace("Control", ""),
                            "source": "uia",
                            "bounds": bounds,
                            "automation_id": uia_utils._safe(control, "AutomationId", "") or "",
                        })

                    if depth < max_depth:
                        for child in control.GetChildren():
                            _walk_interactive(child, depth + 1)
                except Exception:
                    pass

            _walk_interactive(root)
            sources_used.append("uia")
            logger.info(f"elements: found {len(elements)} UIA interactive elements")
        except Exception as e:
            logger.debug(f"UIA elements scan failed: {e}")

    # ── 2. OCR text elements (web content, non-native apps) ──────────────
    try:
        from verification.ocr_match import find_text_on_screen as _ocr_find
        # We don't have specific text to search for, so skip OCR in this mode.
        # OCR is query-based (needs a target string). For broad scanning,
        # we rely on the vision LLM approach below.
        sources_used.append("ocr_available")
    except ImportError:
        pass

    # ── 3. Vision-based element scan (catches what UIA misses) ───────────
    if len(elements) == 0 or window_title:
        try:
            from tools.vision_query import vision_query

            q = (
                "List ALL clickable/interactive elements visible on screen. "
                "For each, give: name, type (button/link/input/icon/tab/menu), "
                "and approximate center pixel coordinates (x, y). "
                f"Screen size is shown in the image metadata. "
                "Respond as JSON array: "
                '[{"name": "...", "type": "...", "x": N, "y": N}]'
            )
            vision_result = vision_query(question=q)
            if vision_result.get("success"):
                import json
                import re
                answer = vision_result.get("answer", "")
                # Parse JSON from vision response
                answer = re.sub(r"^```[a-z]*\s*", "", answer.strip(), flags=re.IGNORECASE)
                answer = re.sub(r"\s*```$", "", answer.strip())
                try:
                    vision_elements = json.loads(answer)
                    if isinstance(vision_elements, list):
                        for ve in vision_elements:
                            elements.append({
                                "name": ve.get("name", ""),
                                "type": ve.get("type", "unknown"),
                                "source": "vision",
                                "bounds": {
                                    "center_x": ve.get("x", 0),
                                    "center_y": ve.get("y", 0),
                                } if "x" in ve else None,
                            })
                        sources_used.append("vision")
                except (json.JSONDecodeError, TypeError):
                    logger.debug("Could not parse vision elements response")
        except Exception as e:
            logger.debug(f"Vision element scan failed: {e}")

    return {
        "success": True,
        "count": len(elements),
        "sources": sources_used,
        "window_title": window_title or "desktop",
        "elements": elements,
    }
