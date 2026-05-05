"""
tools/input/clipboard.py — Clipboard tools

Tools for: copy to clipboard, paste from clipboard
Uses ctypes for Windows clipboard API.
"""

import logging
import time
from typing import Any, Optional

import psutil

from ..base import BaseTool, ToolResult

log = logging.getLogger("clipboard_tools")


def get_active_window_title() -> Optional[str]:
    """Get the title of the currently active window."""
    try:
        import ctypes
        from ctypes import wintypes
        
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            title_buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 256)
            return title_buf.value
    except Exception as e:
        log.debug(f"Failed to get active window: {e}")
    return None


def get_active_process_name() -> Optional[str]:
    """Get the process name of the currently active window."""
    try:
        import ctypes
        from ctypes import wintypes
        
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                process = psutil.Process(pid.value)
                return process.name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        log.debug(f"Failed to get active process: {e}")
    return None


def is_window_active(title_pattern: str) -> bool:
    """Check if a window matching the pattern is currently active."""
    active_title = get_active_window_title()
    if not active_title:
        return False
    
    return title_pattern.lower() in active_title.lower()


def ensure_window_active(title_pattern: str, app_name: Optional[str] = None) -> tuple[bool, str]:
    """
    Ensure a window is active, bringing it to foreground if needed.
    
    Args:
        title_pattern: Pattern to match in window title or app name (e.g., 'notepad', 'cmd')
        app_name: Optional application name to search for if title not found
        
    Returns:
        Tuple of (success, message)
    """
    # First check if already active
    if is_window_active(title_pattern):
        return True, f"{title_pattern} is already active"
    
    # Try to find and bring to foreground
    try:
        from ..apps.window import find_window_by_title, bring_to_foreground
        from ..apps.launcher import APP_MAPPINGS
        
        # First try direct title match
        hwnd = find_window_by_title(title_pattern)
        
        # If not found and we have an app_name, try mapping it to executable
        if hwnd is None and app_name:
            # Check if already active by process name
            active_proc = get_active_process_name()
            if active_proc and app_name.lower() in active_proc:
                return True, f"{app_name} is already active"
            
            # Try finding by app name in title
            hwnd = find_window_by_title(app_name)
            
            # If still not found, try the mapped executable name
            if hwnd is None and app_name.lower() in APP_MAPPINGS:
                exe_name = APP_MAPPINGS[app_name.lower()]
                # Remove .exe suffix for title search
                title_candidate = exe_name.replace('.exe', '')
                hwnd = find_window_by_title(title_candidate)
                
                # For cmd.exe, also try "Command Prompt" as title
                if hwnd is None and app_name.lower() in ['cmd', 'command prompt']:
                    hwnd = find_window_by_title('Command Prompt')
        
        if hwnd:
            bring_to_foreground(hwnd)
            time.sleep(0.3)  # Allow time for window to come to foreground
            
            # Verify it's now active
            if is_window_active(title_pattern) or (app_name and get_active_process_name() and app_name.lower() in get_active_process_name()):
                return True, f"Brought {title_pattern or app_name} to foreground"
            else:
                return True, f"Attemped to bring window to foreground (verification pending)"
        else:
            return False, f"No window found matching '{title_pattern}' or '{app_name}'"
            
    except Exception as e:
        log.error(f"Failed to ensure window active: {e}")
        return False, f"Error: {str(e)}"


def get_clipboard_text(retries: int = 5, delay: float = 0.5) -> Optional[str]:
    """
    Get text content from clipboard with retry logic.
    Uses pyperclip for cross-platform compatibility and better error handling.
    
    Args:
        retries: Number of times to retry if clipboard is busy
        delay: Delay between retries in seconds
    
    Returns:
        Text content or None if failed
    """
    for attempt in range(retries):
        try:
            import pyperclip
            
            # Initial delay to let previous operations complete
            time.sleep(0.5)
            
            # Try to get clipboard text using pyperclip
            text = pyperclip.paste()
            
            if text and len(text.strip()) > 0:
                return text
            else:
                log.debug(f"Clipboard text is empty (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
                    continue
                return None
                
        except Exception as e:
            log.debug(f"Failed to get clipboard (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                log.error(f"All clipboard read attempts failed: {e}")
    
    return None


def set_clipboard_text(text: str) -> bool:
    """Set text content to clipboard using pyperclip."""
    try:
        import pyperclip
        
        # Retry logic for setting clipboard
        for attempt in range(3):
            try:
                pyperclip.copy(text)
                # Verify it was set correctly
                time.sleep(0.2)
                verify = pyperclip.paste()
                if verify == text:
                    return True
            except Exception as e:
                log.debug(f"Failed to set clipboard (attempt {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(0.3 * (attempt + 1))
                continue
        return False
        
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
        
        # Retry logic for setting clipboard
        for attempt in range(3):
            if set_clipboard_text(text):
                preview = text[:50] + "..." if len(text) > 50 else text
                return ToolResult.ok(f"Copied to clipboard: {preview}")
            log.debug(f"Failed to set clipboard (attempt {attempt + 1}/3)")
            time.sleep(0.2 * (attempt + 1))  # Exponential backoff
        
        return ToolResult.fail(error="Failed to copy to clipboard after 3 attempts")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "low"


class PasteFromClipboardTool(BaseTool):
    """Paste/get text from the system clipboard."""
    
    name = "paste_from_clipboard"
    description = "Get the current text content from the system clipboard."
    parameters = {
        "retries": {
            "type": "number",
            "description": "Number of retry attempts if clipboard is busy (default: 3)",
        },
        "delay": {
            "type": "number",
            "description": "Delay between retries in seconds (default: 0.5)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        retries = int(kwargs.get("retries", 5))
        delay = float(kwargs.get("delay", 0.5))
        
        # Add initial delay to allow previous clipboard operations to fully complete
        # This is critical after Ctrl+C which may not have finished yet
        time.sleep(1.0)
        
        text = get_clipboard_text(retries=retries, delay=delay)
        
        if text is not None:
            # Limit output length
            if len(text) > 1000:
                text = text[:1000] + f"\n... ({len(text)} total characters)"
            return ToolResult.ok(f"Clipboard content:\n{text}")
        else:
            return ToolResult.fail(error="Clipboard is empty or contains non-text data")
    
    def estimate_duration(self, **kwargs) -> float:
        retries = kwargs.get("retries", 3)
        delay = kwargs.get("delay", 0.5)
        return 0.3 + (retries * delay)  # Initial delay + potential retries
    
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
        "target_app": {
            "type": "string",
            "description": "Optional: Name of the application that should be active (e.g., 'notepad', 'chrome'). If provided, ensures this app is active before typing.",
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
        target_app = kwargs.get("target_app")
        
        # If no target_app specified, try to detect if a common text editor is active
        # This prevents typing into the terminal when Notepad/WordPad is open
        if not target_app:
            active_process = get_active_process_name()
            active_title = get_active_window_title()
            
            # Common text editors that should receive typed text
            text_editors = ['notepad', 'wordpad', 'winword', 'excel', 'powerpnt']
            
            # Check if a text editor is currently active
            if active_process and any(editor in active_process.lower() for editor in text_editors):
                target_app = active_process.replace('.exe', '')
                log.info(f"Auto-detected text editor: {target_app}")
            # If terminal is active and no target specified, warn the user
            elif active_process and any(term in active_process.lower() for term in ['python.exe', 'cmd.exe', 'powershell.exe', 'terminal', 'wt.exe']):
                log.warning(f"type_text called with terminal active ('{active_title}'). Text will be typed into terminal. Consider specifying target_app parameter.")
        
        # Ensure the target application is active if specified
        if target_app:
            success, message = ensure_window_active(target_app, target_app)
            if not success:
                log.warning(f"Target app {target_app} not active: {message}")
                return ToolResult.fail(error=f"Cannot type: {target_app} is not active. {message}")
            log.info(f"Verified {target_app} is active before typing")
        
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


class ClearTextTool(BaseTool):
    """Clear all text in the active window (e.g., Notepad)."""
    
    name = "clear_text"
    description = "Clear all text content in the currently active window by selecting all (Ctrl+A) and deleting. Automatically brings the target application to foreground if needed. Use for clearing text editors like Notepad, WordPad, or any text field."
    parameters = {
        "target_app": {
            "type": "string",
            "description": "Name of the application whose text should be cleared (e.g., 'notepad', 'wordpad'). Will bring this app to foreground before clearing. If not specified, clears text in whatever window is currently active.",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        target_app = kwargs.get("target_app")
        
        # Always try to ensure a window is active before clearing
        if target_app:
            success, message = ensure_window_active(target_app.lower(), target_app.lower())
            if not success:
                log.warning(f"Target app {target_app} not found: {message}")
                return ToolResult.fail(error=f"Cannot clear text: {target_app} is not open. {message}")
            log.info(f"Brought {target_app} to foreground for clearing text")
        else:
            # No target specified - check what's currently active and warn if it might be wrong
            active_process = get_active_process_name()
            active_title = get_active_window_title()
            log.info(f"Current active window: '{active_title}' (process: {active_process})")
            
            # Warn if trying to clear from terminal/command prompt
            if active_process and any(term in active_process for term in ['python.exe', 'cmd.exe', 'powershell.exe', 'terminal']):
                log.warning("Attempting to clear text while terminal is active - this may not be intended")
        
        try:
            import subprocess
            
            # Small delay to ensure window is ready
            time.sleep(0.2)
            
            # Use PowerShell to send Ctrl+A then Delete in sequence
            script = """
            $shell = New-Object -ComObject WScript.Shell
            # Brief pause to ensure focus
            Start-Sleep -Milliseconds 100
            # Select all
            $shell.SendKeys("^a")
            Start-Sleep -Milliseconds 100
            # Delete selected text
            $shell.SendKeys("{DELETE}")
            Start-Sleep -Milliseconds 50
            """
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                app_info = f" in {target_app}" if target_app else ""
                return ToolResult.ok(f"Cleared all text{app_info}")
            else:
                return ToolResult.fail(error=f"Clear text failed: {result.stderr}")
                
        except Exception as e:
            log.error(f"Clear text failed: {e}")
            return ToolResult.fail(error=f"Clear text failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.8
    
    def risk_level(self) -> str:
        return "medium"  # Can delete unintended content


class PressKeyTool(BaseTool):
    """Press a keyboard key or key combination."""
    
    name = "press_key"
    description = "Press a keyboard key or key combination. Supports special keys like Win, Alt, Ctrl, Shift and combinations like 'Win+D', 'Alt+F4', 'Ctrl+C'."
    parameters = {
        "keys": {
            "type": "string",
            "description": "Key or key combination (e.g., 'F5', 'Win+D', 'Ctrl+C', 'Alt+Tab')",
        },
        "target_app": {
            "type": "string",
            "description": "Optional: Name of the application that should be active (e.g., 'notepad', 'chrome'). If provided, ensures this app is active before pressing keys.",
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
        target_app = kwargs.get("target_app")
        
        # Ensure the target application is active if specified
        if target_app:
            success, message = ensure_window_active(target_app, target_app)
            if not success:
                log.warning(f"Target app {target_app} not active: {message}")
                # Try to continue anyway - the key press might still work
                log.info(f"Attempting to press keys anyway...")
            else:
                log.info(f"Verified {target_app} is active before pressing keys")
        
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
    ClearTextTool,
    PressKeyTool,
]
