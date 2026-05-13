"""
Primitive: control_input(type, data)
Failsafe enabled, bounds checked.

Supported types:
  click, double_click, right_click, move, move_relative,
  type, hotkey, press, key, keys, scroll, scroll_h, drag, drag_smooth
"""

import pyautogui
import logging
import sys
import time

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

# Map of SendKeys aliases to pyautogui key names
_SENDKEYS_MAP = {
    "{del}": "delete", "{delete}": "delete",
    "{enter}": "enter", "{return}": "enter",
    "{esc}": "esc", "{escape}": "esc",
    "{tab}": "tab", "{bksp}": "backspace", "{backspace}": "backspace",
    "{up}": "up", "{down}": "down", "{left}": "left", "{right}": "right",
    "{home}": "home", "{end}": "end", "{pgup}": "pageup", "{pgdn}": "pagedown",
    "{ins}": "insert", "{insert}": "insert",
    "{capslock}": "capslock", "{numlock}": "numlock", "{scrolllock}": "scrolllock",
    "{f1}": "f1", "{f2}": "f2", "{f3}": "f3", "{f4}": "f4",
    "{f5}": "f5", "{f6}": "f6", "{f7}": "f7", "{f8}": "f8",
    "{f9}": "f9", "{f10}": "f10", "{f11}": "f11", "{f12}": "f12",
    "{space}": "space", "{ }": "space",
    "{printscreen}": "printscreen",
}


def _parse_sendkeys(text: str) -> list:
    """Parse SendKeys-style string into a list of key actions.

    Each action is either a plain key name or a list for hotkey combos.
    Examples:
      "^a" -> ["ctrl", "a"] (hotkey combo)
      "^a{DEL}" -> [["ctrl", "a"], "delete"]
      "Hello World" -> ["Hello World"] (typewrite)
    """
    if not text:
        return []

    result = []
    i = 0
    while i < len(text):
        if text[i] in ("^", "%", "+"):
            # Modifier prefix — collect until next special or end
            mod_map = {"^": "ctrl", "%": "alt", "+": "shift"}
            mods = []
            while i < len(text) and text[i] in ("^", "%", "+"):
                mods.append(mod_map[text[i]])
                i += 1
            # Next char or brace-group is the key
            if i < len(text) and text[i] == "{":
                end = text.index("}", i) if "}" in text[i:] else len(text)
                key = text[i + 1 : end].lower()
                i = end + 1
            elif i < len(text):
                key = text[i].lower()
                i += 1
            else:
                key = ""
            key = _SENDKEYS_MAP.get("{" + key + "}", key)
            if mods and key:
                result.append(mods + [key])
            elif key:
                result.append([key])
        elif text[i] == "{":
            # Braced key like {DEL}, {ENTER}
            end = text.index("}", i) if "}" in text[i:] else len(text)
            key = text[i + 1 : end].lower().strip()
            key = _SENDKEYS_MAP.get("{" + key + "}", key)
            if key:
                result.append([key])
            i = end + 1
        else:
            # Plain text — collect contiguous chars
            start = i
            while i < len(text) and text[i] not in ("^", "%", "+", "{"):
                i += 1
            chunk = text[start:i]
            if chunk:
                result.append(chunk)

    return result


def control_input(type: str, data: dict = None, window_title: str = None) -> dict:  # noqa: A002
    # Handle case where LLM passes 'data' as a string instead of a dict
    if isinstance(data, str):
        try:
            import json
            data = json.loads(data)
        except Exception:
            if type in ("hotkey", "keys", "press", "key"):
                data = {"keys": data.replace("+", ",").split(",")}
            elif type == "type":
                data = {"text": data}
            else:
                return {"success": False, "error": f"Expected dict for 'data', got string: {data}. Use type='keys' for SendKeys-style input."}

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
        elif type == "move_relative":
            dx = data.get("dx", 0)
            dy = data.get("dy", 0)
            pyautogui.moveRel(dx, dy, duration=data.get("duration", 0.15))
        elif type == "type":
            text = data.get("text") or data.get("data") or ""
            pyautogui.typewrite(str(text), interval=data.get("interval", 0.03))
        elif type in ("hotkey", "press", "key"):
            keys = data.get("keys") or data.get("key")
            if isinstance(keys, str):
                actions = _parse_sendkeys(keys)
                keys = []
                for a in actions:
                    if isinstance(a, list):
                        keys.extend(a)
                    elif isinstance(a, str):
                        keys.append(a)
            if not keys:
                return {"success": False, "error": "No 'keys' provided"}
            keys = [k.strip().lower() for k in keys if k.strip()]
            keys = [_SENDKEYS_MAP.get(k, k) for k in keys]
            if len(keys) > 1:
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(keys[0])
        elif type == "keys":
            text = data.get("keys") or data.get("text") or ""
            if not text:
                return {"success": False, "error": "No 'keys' provided"}
            actions = _parse_sendkeys(text)
            for action in actions:
                if isinstance(action, list):
                    if len(action) > 1:
                        pyautogui.hotkey(*action)
                    else:
                        pyautogui.press(action[0])
                elif isinstance(action, str):
                    pyautogui.typewrite(action)
        elif type == "scroll":
            pyautogui.scroll(data.get("clicks", 3), x=data.get("x"), y=data.get("y"))
        elif type == "scroll_h":
            pyautogui.hscroll(data.get("clicks", 3), x=data.get("x"), y=data.get("y"))
        elif type == "drag":
            x_start = data.get("start_x") if data.get("start_x") is not None else data.get("x")
            y_start = data.get("start_y") if data.get("start_y") is not None else data.get("y")
            x_end = data.get("end_x") if data.get("end_x") is not None else data.get("x", 0) + data.get("dx", 0)
            y_end = data.get("end_y") if data.get("end_y") is not None else data.get("y", 0) + data.get("dy", 0)
            duration = data.get("duration", 0.3)
            button = data.get("button", "left")
            if x_start is not None and y_start is not None:
                pyautogui.moveTo(x_start, y_start)
                pyautogui.drag(x_end - x_start, y_end - y_start, duration=duration, button=button)
            else:
                pyautogui.drag(x_end, y_end, duration=duration, button=button)
        elif type == "drag_smooth":
            x_end = data.get("x")
            y_end = data.get("y")
            dx = data.get("dx", 0)
            dy = data.get("dy", 0)
            duration = data.get("duration", 0.5)
            steps = data.get("steps", 20)
            button = data.get("button", "left")
            current_x, current_y = pyautogui.position()
            target_x = x_end if x_end is not None else current_x + dx
            target_y = y_end if y_end is not None else current_y + dy
            pyautogui.moveTo(current_x, current_y)
            pyautogui.drag(target_x - current_x, target_y - current_y, duration=duration, button=button)
        else:
            return {"success": False, "error": f"Unknown type: {type}"}
        return {"success": True, "type": type}
    except Exception as e:
        logger.error(f"control_input error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def get_mouse_position() -> dict:
    """Return the current mouse cursor position."""
    try:
        x, y = pyautogui.position()
        return {"success": True, "x": x, "y": y}
    except Exception as e:
        return {"success": False, "error": str(e)}