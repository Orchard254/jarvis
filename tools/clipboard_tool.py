"""Clipboard read/write tool."""

import logging
import subprocess

logger = logging.getLogger(__name__)


def clipboard(action: str = "read", text: str = None) -> dict:
    """Read from or write to the system clipboard."""

    # ── Primary: pyperclip ───────────────────────────────────────────────────
    try:
        import pyperclip

        if action == "read":
            t = pyperclip.paste()
            return {"success": True, "text": t, "length": len(t), "action": "read"}
        else:  # write
            pyperclip.copy(text or "")
            return {"success": True, "action": "write"}

    except ImportError:
        logger.debug("clipboard: pyperclip not available, trying win32clipboard")
    except Exception as e:
        logger.warning(f"clipboard pyperclip error: {e}")

    # ── Fallback: win32clipboard (part of pywin32) ───────────────────────────
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            if action == "read":
                try:
                    data = win32clipboard.GetClipboardData(
                        win32clipboard.CF_UNICODETEXT
                    )
                except Exception:
                    data = ""
                return {
                    "success": True,
                    "text": data,
                    "length": len(data),
                    "action": "read",
                }
            else:  # write
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(
                    text or "", win32clipboard.CF_UNICODETEXT
                )
                return {"success": True, "action": "write"}
        finally:
            win32clipboard.CloseClipboard()

    except ImportError:
        logger.debug("clipboard: win32clipboard not available, trying PowerShell")
    except Exception as e:
        logger.warning(f"clipboard win32clipboard error: {e}")

    # ── Second fallback: PowerShell ──────────────────────────────────────────
    try:
        if action == "read":
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            t = result.stdout.rstrip("\n")
            return {"success": True, "text": t, "length": len(t), "action": "read"}
        else:  # write
            safe_text = (text or "").replace("'", "''")  # escape single quotes
            result = subprocess.run(
                ["powershell", "-command", f"Set-Clipboard '{safe_text}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": result.stderr.strip() or "PowerShell Set-Clipboard failed",
                }
            return {"success": True, "action": "write"}

    except Exception as e:
        logger.error(f"clipboard PowerShell fallback error: {e}")
        return {"success": False, "error": str(e)}
