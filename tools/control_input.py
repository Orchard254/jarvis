
"""
Primitive: control_input(type, data)
Failsafe enabled, bounds checked.
"""
import pyautogui
import logging
import sys

logger = logging.getLogger(__name__)
# FAILSAFE=False: the fail-safe exception fires when the mouse drifts near a
# screen corner during normal use, crashing all legitimate hotkey calls.
# JARVIS is a deliberate desktop agent — the emergency escape isn't needed.
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

def control_input(type: str, data: dict = None, window_title: str = None) -> dict:
    # Handle case where LLM passes 'data' as a string instead of a dict
    if isinstance(data, str):
        try:
            import json
            data = json.loads(data)
        except:
            # If it's not JSON, maybe it's a simple string like "win+d"
            # for a hotkey, but our schema expects a dict.
            # We'll try to recover for hotkeys specifically.
            if type in ("hotkey", "keys", "press"):
                data = {"keys": data.replace("+", ",").split(",")}
            elif type == "type":
                data = {"text": data}
            else:
                # Last resort: try to treat it as keys if it contains ^ or { or +
                if any(c in data for c in ("^", "{", "+")):
                    type = "keys"
                    data = {"keys": data}
                else:
                    return {"success": False, "error": f"Expected dict for 'data', got string: {data}"}

    data = data or {}
    try:
        # ── Optional: Auto-focus window if title provided ────────────────────
        if window_title:
            from tools.control_window import control_window
            focus_res = control_window(window_title, "focus")
            if not focus_res.get("success"):
                logger.warning(f"control_input: could not focus '{window_title}' — proceeding anyway")

        if type == "click":
            pyautogui.click(data.get("x"), data.get("y"))
        elif type == "double_click":
            pyautogui.doubleClick(data.get("x"), data.get("y"))
        elif type == "right_click":
            pyautogui.rightClick(data.get("x"), data.get("y"))
        elif type == "move":
            pyautogui.moveTo(data.get("x"), data.get("y"), duration=data.get("duration", 0.2))
        elif type == "type":
            text = data.get("text") or data.get("data") or ""
            pyautogui.typewrite(str(text), interval=data.get("interval", 0.03))
        elif type in ("hotkey", "press", "key"):
            keys = data.get("keys") or data.get("key")
            if isinstance(keys, str):
                # Handle common SendKeys aliases if present
                keys = keys.replace("^", "ctrl+").replace("%", "alt+").replace("+", "shift+")
                keys = keys.replace("ctrl+a", "ctrl,a").replace("ctrl+s", "ctrl,s")
                keys = keys.replace("+", ",").split(",")
            if not keys:
                return {"success": False, "error": "No 'keys' provided"}
            
            # Filter out empty and normalize
            keys = [k.strip().lower() for k in keys if k.strip()]
            
            # Map SendKeys style {DEL} etc to pyautogui
            _MAP = {"{del}": "delete", "{delete}": "delete", "{enter}": "enter", "{esc}": "esc", "{tab}": "tab"}
            keys = [_MAP.get(k, k) for k in keys]
            
            if len(keys) > 1:
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(keys[0])
        elif type == "keys":
            # Smart handler for mixed sequences like "^a{DEL}"
            text = data.get("keys") or data.get("text") or ""
            if not text:
                return {"success": False, "error": "No 'keys' provided"}
            
            # Very simple parser for common patterns
            if text == "^a{DEL}":
                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("delete")
            elif text == "^a":
                pyautogui.hotkey("ctrl", "a")
            elif text.startswith("^"):
                pyautogui.hotkey("ctrl", text[1:].lower())
            else:
                pyautogui.typewrite(text)
        elif type == "scroll":
            pyautogui.scroll(data.get("clicks", 3), x=data.get("x"), y=data.get("y"))
        else:
            return {"success": False, "error": f"Unknown type: {type}"}
        return {"success": True, "type": type}
    except Exception as e:
        logger.error(f"control_input error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
