"""
tools/input/clipboard.py — Clipboard tools

Tools for: copy to clipboard, paste from clipboard
Uses ctypes for Windows clipboard API.
"""

import logging
import time
from typing import Any, Optional

from ..base import BaseTool, ToolResult

log = logging.getLogger("clipboard_tools")


def get_clipboard_text() -> Optional[str]:
    """Get text content from clipboard."""
    try:
        import ctypes
        from ctypes import wintypes
        
        # Open clipboard
        if not ctypes.windll.user32.OpenClipboard(None):
            return None
        
        try:
            # Get text data (CF_UNICODETEXT = 13)
            handle = ctypes.windll.user32.GetClipboardData(13)
            if handle:
                # Lock and read the memory
                ptr = ctypes.windll.kernel32.GlobalLock(handle)
                if ptr:
                    text = ctypes.wstring_at(ptr)
                    ctypes.windll.kernel32.GlobalUnlock(handle)
                    return text
        finally:
            ctypes.windll.user32.CloseClipboard()
            
    except Exception as e:
        log.debug(f"Failed to get clipboard: {e}")
    
    return None


def set_clipboard_text(text: str) -> bool:
    """Set text content to clipboard."""
    try:
        import ctypes
        from ctypes import wintypes
        
        GHND = 0x42
        GMEM_MOVEABLE = 0x0002
        GMEM_ZEROINIT = 0x0040
        
        # Open clipboard
        if not ctypes.windll.user32.OpenClipboard(None):
            return False
        
        try:
            # Empty clipboard
            ctypes.windll.user32.EmptyClipboard()
            
            # Convert text to bytes with null terminator
            text_bytes = (text + '\0').encode('utf-16-le')
            size = len(text_bytes)
            
            # Allocate global memory
            handle = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
            if not handle:
                return False
            
            # Lock memory and copy data
            ptr = ctypes.windll.kernel32.GlobalLock(handle)
            if ptr:
                ctypes.memmove(ptr, text_bytes, size)
                ctypes.windll.kernel32.GlobalUnlock(handle)
                
                # Set clipboard data
                if ctypes.windll.user32.SetClipboardData(13, handle):  # CF_UNICODETEXT
                    return True
            
            # Clean up on failure
            ctypes.windll.kernel32.GlobalFree(handle)
            return False
            
        finally:
            ctypes.windll.user32.CloseClipboard()
            
    except Exception as e:
        log.error(f"Failed to set clipboard: {e}")
        return False


class CopyToClipboardTool(BaseTool):
    """Copy text to the system clipboard."""
    
    name = "copy_to_clipboard"
    description = "Copy text to the system clipboard. The text will be available for pasting elsewhere."
    parameters = {
        "text": {
            "type": "string",
            "description": "Text to copy to clipboard",
        },
    }
    required_parameters = ["text"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        text = kwargs.get("text")
        if text is None:
            return False, "text parameter is required"
        if not isinstance(text, str):
            return False, "text must be a string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        text = kwargs["text"]
        
        if set_clipboard_text(text):
            preview = text[:50] + "..." if len(text) > 50 else text
            return ToolResult.ok(f"Copied to clipboard: {preview}")
        else:
            return ToolResult.fail(error="Failed to copy to clipboard")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "low"


class PasteFromClipboardTool(BaseTool):
    """Paste/get text from the system clipboard."""
    
    name = "paste_from_clipboard"
    description = "Get the current text content from the system clipboard."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        text = get_clipboard_text()
        
        if text is not None:
            # Limit output length
            if len(text) > 1000:
                text = text[:1000] + f"\n... ({len(text)} total characters)"
            return ToolResult.ok(f"Clipboard content:\n{text}")
        else:
            return ToolResult.fail(error="Clipboard is empty or contains non-text data")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "low"


class TypeTextTool(BaseTool):
    """Type text into the active window."""
    
    name = "type_text"
    description = "Type text into the currently active window as if typing on keyboard. Use for filling forms or entering text."
    parameters = {
        "text": {
            "type": "string",
            "description": "Text to type",
        },
        "delay": {
            "type": "number",
            "description": "Delay between keystrokes in seconds (default: 0.05)",
        },
    }
    required_parameters = ["text"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        text = kwargs.get("text")
        if not text:
            return False, "text parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        text = kwargs["text"]
        delay = kwargs.get("delay", 0.05)
        
        try:
            # Try to use pyautogui for reliable keyboard input
            try:
                import pyautogui
                pyautogui.FAILSAFE = True
                pyautogui.PAUSE = delay
                pyautogui.write(text, interval=delay)
                log.info(f"Typed {len(text)} characters using pyautogui")
                return ToolResult.ok(f"Typed {len(text)} characters")
            except ImportError:
                log.debug("pyautogui not available, falling back to ctypes")
            except Exception as e:
                log.warning(f"pyautogui failed: {e}, falling back to ctypes")
            
            # Fallback: Use ctypes with proper scan codes
            import ctypes
            
            # Map for special characters that need shift
            shift_chars = {
                '!': ('1', True), '@': ('2', True), '#': ('3', True),
                '$': ('4', True), '%': ('5', True), '^': ('6', True),
                '&': ('7', True), '*': ('8', True), '(': ('9', True),
                ')': ('0', True), '_': ('-', True), '+': ('=', True),
                '{': ('[', True), '}': (']', True), '|': ('\\', True),
                ':': (';', True), '"': ("'", True), '<': (',', True),
                '>': ('.', True), '?': ('/', True), '~': ('`', True),
            }
            
            VK_SHIFT = 0x10
            
            for char in text:
                if char in shift_chars:
                    base_char, needs_shift = shift_chars[char]
                    # Press shift
                    ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
                    time.sleep(delay / 2)
                    # Press base character
                    ctypes.windll.user32.keybd_event(ord(base_char.upper()), 0, 0, 0)
                    time.sleep(delay)
                    ctypes.windll.user32.keybd_event(ord(base_char.upper()), 0, 0x0002, 0)
                    time.sleep(delay / 2)
                    # Release shift
                    ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0x0002, 0)
                elif char.isupper():
                    # Uppercase letters need shift
                    ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
                    time.sleep(delay / 2)
                    ctypes.windll.user32.keybd_event(ord(char), 0, 0, 0)
                    time.sleep(delay)
                    ctypes.windll.user32.keybd_event(ord(char), 0, 0x0002, 0)
                    time.sleep(delay / 2)
                    ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0x0002, 0)
                else:
                    # Regular characters
                    ctypes.windll.user32.keybd_event(ord(char.upper()), 0, 0, 0)
                    time.sleep(delay)
                    ctypes.windll.user32.keybd_event(ord(char.upper()), 0, 0x0002, 0)
            
            return ToolResult.ok(f"Typed {len(text)} characters")
            
        except Exception as e:
            log.error(f"Type text failed: {e}")
            return ToolResult.fail(error=f"Type text failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        text = kwargs.get("text", "")
        delay = kwargs.get("delay", 0.05)
        return len(text) * delay
    
    def risk_level(self) -> str:
        return "medium"  # Can trigger unintended actions


class PressKeyTool(BaseTool):
    """Press a keyboard key or key combination."""
    
    name = "press_key"
    description = "Press a keyboard key or key combination. Supports special keys like Win, Alt, Ctrl, Shift and combinations like 'Win+D', 'Alt+F4', 'Ctrl+C'."
    parameters = {
        "keys": {
            "type": "string",
            "description": "Key or key combination (e.g., 'F5', 'Win+D', 'Ctrl+C', 'Alt+Tab')",
        },
    }
    required_parameters = ["keys"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        keys = kwargs.get("keys")
        if not keys:
            return False, "keys parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        keys = kwargs["keys"]
        
        try:
            import subprocess
            
            # Use PowerShell WScript.Shell for special keys
            # Extended key map including calculator symbols
            key_map = {
                "win": "#",
                "windows": "#",
                "lwin": "#",
                "rwin": "#",
                "alt": "%",
                "ctrl": "^",
                "shift": "+",
                "tab": "{TAB}",
                "enter": "{ENTER}",
                "return": "{ENTER}",
                "escape": "{ESC}",
                "space": " ",
                "backspace": "{BACKSPACE}",
                "delete": "{DELETE}",
                "home": "{HOME}",
                "end": "{END}",
                "pageup": "{PGUP}",
                "pagedown": "{PGDN}",
                "up": "{UP}",
                "down": "{DOWN}",
                "left": "{LEFT}",
                "right": "{RIGHT}",
                "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}",
                "f5": "{F5}", "f6": "{F6}", "f7": "{F7}", "f8": "{F8}",
                "f9": "{F9}", "f10": "{F10}", "f11": "{F11}", "f12": "{F12}",
                # Calculator/math symbols - map to their literal characters
                # In SendKeys, these need special handling
                "plus": "{+}",  # Literal plus sign
                "add": "{+}",
                "subtract": "-",
                "multiply": "*",
                "divide": "/",
                "decimal": ".",
                "dot": ".",
                "percent": "%",
                # Parentheses and brackets
                "lparen": "(",
                "rparen": ")",
                "lbracket": "[",
                "rbracket": "]",
                "lbrace": "{{",  # Escaped { in SendKeys
                "rbrace": "}}",  # Escaped } in SendKeys
            }
            
            # Parse key combination
            # Check if it's a hotkey combo (contains + but not just "+")
            parts = keys.lower().split("+")
            
            # Handle single "+" key press vs combination like "ctrl+s"
            if keys == "+" or keys.strip() == "+":
                # User wants to press the plus key literally
                script = """
                $shell = New-Object -ComObject WScript.Shell
                $shell.SendKeys("{+}")
                """
            elif len(parts) > 1 and parts[0].strip() in ["ctrl", "alt", "shift", "win", "windows", "lwin", "rwin"]:
                # It's a modifier combination like "ctrl+c" or "win+d"
                ps_keys = []
                for i, part in enumerate(parts):
                    part = part.strip()
                    if part in key_map:
                        mapped = key_map[part]
                        # Modifiers should not be wrapped in braces when combined
                        if part in ["ctrl", "alt", "shift", "win", "windows", "lwin", "rwin"]:
                            ps_keys.append(mapped)
                        else:
                            ps_keys.append(f"{mapped}")
                    elif len(part) == 1:
                        ps_keys.append(part)
                    else:
                        ps_keys.append(f"{{{part.upper()}}}")
                
                sendkeys_str = "".join(ps_keys)
                script = f"""
                $shell = New-Object -ComObject WScript.Shell
                $shell.SendKeys("{sendkeys_str}")
                """
            else:
                # Single key or non-modifier combination
                processed_parts = []
                for part in parts:
                    part = part.strip()
                    if part in key_map:
                        processed_parts.append(key_map[part])
                    elif len(part) == 1:
                        # Single character - escape if special in SendKeys
                        if part in "+^%~(){{}}[]":
                            processed_parts.append("{" + part + "}")
                        else:
                            processed_parts.append(part)
                    else:
                        processed_parts.append(f"{{{part.upper()}}}")
                
                sendkeys_str = "".join(processed_parts)
                script = f"""
                $shell = New-Object -ComObject WScript.Shell
                $shell.SendKeys("{sendkeys_str}")
                """
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                return ToolResult.ok(f"Pressed: {keys}")
            else:
                return ToolResult.fail(error=f"Key press failed: {result.stderr}")
                
        except Exception as e:
            log.error(f"Press key failed: {e}")
            return ToolResult.fail(error=f"Press key failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "medium"  # Can trigger unintended actions


# Export all tool classes
CLIPBOARD_TOOLS = [
    CopyToClipboardTool,
    PasteFromClipboardTool,
    TypeTextTool,
    PressKeyTool,
]
