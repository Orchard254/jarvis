"""
Unified input tool (keyboard + mouse).
Actions: click, type, hotkey, scroll, drag
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def input(
    action: str = "type",
    text: str | None = None,
    keys: str | None = None,
    x: int | None = None,
    y: int | None = None,
    target_text: str | None = None,
    window_title: str | None = None,
    direction: str = "down",
    clicks: int = 1,
    from_x: int | None = None,
    from_y: int | None = None,
    to_x: int | None = None,
    to_y: int | None = None,
) -> dict:
    if action == "click":
        return _click(x, y, target_text)
    elif action == "type":
        return _type(text, window_title)
    elif action == "hotkey":
        return _hotkey(keys)
    elif action == "scroll":
        return _scroll(direction, clicks)
    elif action == "drag":
        return _drag(from_x, from_y, to_x, to_y)
    return {"success": False, "error": f"Unknown input action: {action}"}


def _click(x: int | None, y: int | None, target_text: str | None) -> dict:
    if target_text:
        from tools.screen import screen
        return screen(action="find", text=target_text, click=True)
    if x is not None and y is not None:
        try:
            import pyautogui
            pyautogui.click(x, y)
            return {"success": True, "x": x, "y": y}
        except Exception as e:
            return {"success": False, "error": f"Click at ({x},{y}) failed: {e}"}
    return {"success": False, "error": "Provide target_text or x,y coordinates"}


def _type(text: str | None, window_title: str | None = None) -> dict:
    if not text:
        return {"success": False, "error": "text required for type action"}
    try:
        import time
        import pyautogui

        # Focus the target window before typing
        if window_title:
            try:
                import pygetwindow as gw
                for w in gw.getAllWindows():
                    if w.visible and window_title.lower() in (w.title or "").lower():
                        w.activate()
                        time.sleep(0.3)
                        break
            except Exception as e:
                logger.debug(f"sleep failed: {e}")

        pyautogui.write(text, interval=0.03)
        return {"success": True, "chars": len(text)}
    except Exception as e:
        return {"success": False, "error": f"Type failed: {e}"}


def _hotkey(keys: str | None) -> dict:
    if not keys:
        return {"success": False, "error": "keys required for hotkey action (e.g. 'ctrl+c')"}
    try:
        import pyautogui
        parts = keys.lower().split("+")
        pyautogui.hotkey(*parts)
        return {"success": True, "keys": keys}
    except Exception as e:
        return {"success": False, "error": f"Hotkey {keys} failed: {e}"}


def _scroll(direction: str, clicks: int) -> dict:
    try:
        import pyautogui
        amount = clicks * (1 if direction == "down" else -1)
        pyautogui.scroll(amount)
        return {"success": True, "direction": direction, "clicks": clicks}
    except Exception as e:
        return {"success": False, "error": f"Scroll failed: {e}"}


def _drag(from_x: int | None, from_y: int | None, to_x: int | None, to_y: int | None) -> dict:
    if None in (from_x, from_y, to_x, to_y):
        return {"success": False, "error": "from_x, from_y, to_x, to_y required for drag"}
    try:
        import pyautogui
        pyautogui.drag(to_x - from_x, to_y - from_y, duration=0.3)
        return {"success": True, "from": (from_x, from_y), "to": (to_x, to_y)}
    except Exception as e:
        return {"success": False, "error": f"Drag failed: {e}"}



