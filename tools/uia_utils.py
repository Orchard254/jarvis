"""
Windows UI Automation (UIA) utilities.

Provides deterministic element finding and interaction via the Windows UIA COM API.
Uses module-level uia.FindControl() for element lookup (not control.FindControl).
Includes a shadow DOM cache for sub-second repeat lookups.

Architecture:
  1. Try exact name match first
  2. Fall back to substring match
  3. Cache resolved elements by HWND (shadow DOM pattern)
  4. Scope searches to specific windows when possible
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import uiautomation as uia
    _HAS_UIA = True
except ImportError:
    _HAS_UIA = False
    uia = None


# ── Shadow DOM cache ─────────────────────────────────────────────────────────
# Caches resolved UIA elements by HWND so repeated lookups within the same
# window don't require cross-process RPC calls.  Inspired by UI Automata.
_cache: dict[int, dict] = {}
_cache_max_age = 2.0  # seconds before re-resolution


def _cached_hwnd(control) -> int | None:
    """Get a stable cache key from a UIA control."""
    try:
        return control.NativeWindowHandle
    except Exception:
        return None


def _cache_put(control, name: str):
    hwnd = _cached_hwnd(control)
    if hwnd:
        _cache[hwnd] = {
            "control": control,
            "name": name,
            "ts": time.time(),
        }
        # Evict stale entries
        now = time.time()
        stale = [k for k, v in _cache.items() if now - v["ts"] > _cache_max_age]
        for k in stale:
            del _cache[k]


def _cache_get(name: str):
    """Return a cached control matching *name*, or None."""
    now = time.time()
    for hwnd, entry in list(_cache.items()):
        if now - entry["ts"] > _cache_max_age:
            del _cache[hwnd]
            continue
        if entry["name"] == name:
            return entry["control"]
    return None


def _cache_invalidate():
    _cache.clear()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe(control, attr: str, default=None):
    """Safely read a UIA control attribute that may not exist on all types."""
    try:
        return getattr(control, attr, default)
    except Exception:
        return default


def available() -> bool:
    return _HAS_UIA


# ── Find window by title ────────────────────────────────────────────────────


def _find_window(title: str) -> object | None:
    """Return the first top-level window whose title contains *title*."""
    if not _HAS_UIA:
        return None
    title_lower = title.lower()
    for child in uia.GetRootControl().GetChildren():
        try:
            if title_lower in (child.Name or "").lower():
                return child
        except Exception:
            continue
    return None


# ── Core element search ─────────────────────────────────────────────────────


def get_element(
    text: str | None = None,
    automation_id: str | None = None,
    class_name: str | None = None,
    from_control=None,
    timeout: float = 5.0,
    window_title: str | None = None,
) -> dict:
    """Find a UI element by text, automation_id, or class_name.

    Uses module-level uia.FindControl() which is the correct API for
    uiautomation 2.x.  Falls back to manual recursive search if FindControl
    fails on certain control types.
    """
    if not _HAS_UIA:
        return {"success": False, "error": "uiautomation not available"}

    # Scope to a specific window if requested
    root = from_control
    if window_title and root is None:
        root = _find_window(window_title)
        if root is None:
            return {"success": False, "error": f"Window not found: {window_title}"}
    if root is None:
        root = uia.GetRootControl()

    # Check cache first
    if text:
        cached = _cache_get(text)
        if cached is not None:
            try:
                if _safe(cached, "Name", "") == text:
                    return _control_to_dict(cached)
            except Exception as e:
                logger.debug(f"_control_to_dict failed: {e}")

    deadline = time.time() + timeout
    last_error = None

    while time.time() < deadline:
        try:
            found, found_name = _search_uia(root, text, automation_id, class_name)
            if found is not None:
                if text:
                    _cache_put(found, text)
                return _control_to_dict(found, name_override=found_name)
        except Exception as e:
            last_error = str(e)
        time.sleep(0.2)

    return {
        "success": False,
        "error": last_error or f"Element not found: text={text} id={automation_id}",
    }


def _search_uia(root, text, automation_id, class_name):
    """Search using module-level uia.FindControl first, fall back to manual.

    Returns (control, name) tuple where name is captured during search to
    survive element staleness (UIA elements can become invalid between
    match and property read).
    """
    found_name = None

    if _HAS_UIA:
        try:
            def _compare(control, _depth):
                nonlocal found_name
                if _matches(control, text, automation_id, class_name):
                    found_name = _safe(control, "Name", "") or ""
                    return True
                return False
            found = uia.FindControl(root, _compare)
            if found is not None:
                return found, found_name
        except Exception as e:
            logger.debug(f"FindControl failed: {e}")

    found_control, found_name = _search_manual(root, text, automation_id, class_name, depth=0)
    return found_control, found_name


def _matches(control, text, automation_id, class_name) -> bool:
    """Check if a control matches the given criteria."""
    try:
        if text:
            cname = _safe(control, "Name", "") or ""
            if text.lower() != cname.lower():
                return False
        if automation_id:
            if (_safe(control, "AutomationId", "") or "") != automation_id:
                return False
        if class_name:
            if (_safe(control, "ClassName", "") or "") != class_name:
                return False
        return True
    except Exception:
        return False


def _search_manual(control, text, automation_id, class_name, depth=0):
    """Manual recursive search. Returns (control, name) or (None, None)."""
    if depth > 10:
        return None, None
    try:
        if _matches(control, text, automation_id, class_name):
            name = _safe(control, "Name", "") or ""
            return control, name
    except Exception as e:
        logger.debug(f"_safe failed: {e}")
    try:
        for child in control.GetChildren():
            result, name = _search_manual(child, text, automation_id, class_name, depth + 1)
            if result:
                return result, name
    except Exception as e:
        logger.debug(f"_search_manual failed: {e}")
    return None, None


def _control_to_dict(control: object, name_override: str | None = None) -> dict:
    """Convert a UIA control to a serializable dict.

    Uses name_override (captured during search) when available to survive
    element staleness — the control's Name property may become unreadable
    between the search callback and this conversion.
    """
    rect = _safe(control, "BoundingRectangle")
    bounds = None
    if rect:
        try:
            bounds = {
                "left": rect.left,
                "top": rect.top,
                "width": rect.width(),
                "height": rect.height(),
            }
        except Exception:
            bounds = None

    name = name_override
    if not name:
        name = _safe(control, "Name", "") or ""

    return {
        "success": True,
        "name": name,
        "automation_id": _safe(control, "AutomationId", "") or "",
        "class_name": _safe(control, "ClassName", "") or "",
        "control_type": _safe(control, "ControlTypeName", "") or "",
        "handle": _safe(control, "NativeWindowHandle"),
        "bounds": bounds,
        "is_enabled": _safe(control, "IsEnabled", True),
        "is_visible": _safe(control, "IsVisible", True),
    }


# ── Public convenience functions ─────────────────────────────────────────────


def get_element_by_text(
    text: str,
    timeout: float = 5.0,
    click: bool = False,
    window_title: str | None = None,
) -> dict:
    """Find an element by visible text. Optionally click it."""
    result = get_element(text=text, timeout=timeout, window_title=window_title)
    if result["success"] and click:
        click_result = _do_click(result)
        return click_result
    return result


def get_element_by_id(automation_id: str, timeout: float = 3.0) -> dict:
    return get_element(automation_id=automation_id, timeout=timeout)


def _do_click(element_info: dict) -> dict:
    """Click a previously-resolved element via its name."""
    if not _HAS_UIA:
        return {"success": False, "error": "uiautomation not available"}
    name = element_info.get("name", "")
    if not name:
        return {"success": False, "error": "No element name to click"}

    try:
        root = uia.GetRootControl()
        found = uia.FindControl(root, lambda c, d: _safe(c, "Name", "") == name)
        if found is not None:
            found.Click()
            return {"success": True, "clicked": name}
    except Exception as e:
        logger.debug(f"UIA click failed: {e}")

    # Fallback: click via pyautogui at element bounds
    bounds = element_info.get("bounds")
    if bounds:
        cx = bounds["left"] + bounds["width"] // 2
        cy = bounds["top"] + bounds["height"] // 2
        try:
            import pyautogui
            pyautogui.click(cx, cy)
            return {"success": True, "method": "pyautogui", "clicked": name}
        except Exception as e:
            logger.debug(f"click failed: {e}")

    return {"success": False, "error": f"Could not click '{name}'"}


# ── Tree inspection ──────────────────────────────────────────────────────────


def get_tree(window_title: str | None = None, max_depth: int = 3) -> dict:
    """Get the UIA accessibility tree for the desktop or a specific window."""
    if not _HAS_UIA:
        return {"success": False, "error": "uiautomation not available"}

    root = uia.GetRootControl()
    if window_title:
        root = _find_window(window_title)
        if root is None:
            return {"success": False, "error": f"Window not found: {window_title}"}

    def _walk(control, depth: int = 0) -> list[dict]:
        if depth > max_depth:
            return []
        items = []
        items.append({
            "name": _safe(control, "Name", "") or "",
            "class_name": _safe(control, "ClassName", "") or "",
            "control_type": _safe(control, "ControlTypeName", "") or "",
            "automation_id": _safe(control, "AutomationId", "") or "",
            "is_enabled": _safe(control, "IsEnabled", True),
            "is_visible": _safe(control, "IsVisible", True),
        })
        if depth < max_depth:
            try:
                for child in control.GetChildren():
                    items.extend(_walk(child, depth + 1))
            except Exception as e:
                logger.debug(f"extend failed: {e}")
        return items

    elements = _walk(root)
    return {
        "success": True,
        "count": len(elements),
        "window_title": window_title or "desktop",
        "elements": elements,
    }


def wait_for_element_appear(text: str, timeout: float = 10.0) -> dict:
    return get_element(text=text, timeout=timeout)


def get_focused_element() -> dict:
    if not _HAS_UIA:
        return {"success": False, "error": "uiautomation not available"}
    try:
        focused = uia.GetFocusedControl()
        if focused is not None:
            return _control_to_dict(focused)
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": False, "error": "No focused element found"}
