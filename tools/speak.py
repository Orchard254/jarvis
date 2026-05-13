"""
Unified voice I/O tool.
Actions: speak, ask, listen
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def speak(
    action: str = "speak",
    text: str | None = None,
    prompt: str | None = None,
    choices: list[str] | None = None,
    timeout_seconds: int = 60,
    blocking: bool = True,
    speak_prompt: bool = True,
) -> dict:
    if action == "speak":
        return _speak(text, blocking)
    elif action == "ask":
        return _ask(prompt, choices, timeout_seconds)
    elif action == "listen":
        return _listen(prompt, timeout_seconds, speak_prompt)
    return {"success": False, "error": f"Unknown speak action: {action}"}


def _speak(text: str | None, blocking: bool) -> dict:
    if not text:
        return {"success": False, "error": "text required for speak action"}
    try:
        from output.tts import speak as tts_speak
        ok = tts_speak(text=text, blocking=blocking)
        return {"success": ok, "chars": len(text)}
    except Exception as e:
        return {"success": False, "error": f"TTS failed: {e}"}


def _ask(prompt: str | None, choices: list[str] | None, timeout: int) -> dict:
    if not prompt:
        return {"success": False, "error": "prompt required for ask action"}
    try:
        from tools.ask_user import ask_user
        return ask_user(prompt=prompt, choices=choices, timeout_seconds=timeout)
    except Exception as e:
        return {"success": False, "error": f"Ask user failed: {e}"}


def _listen(prompt: str | None, timeout: int, speak_prompt: bool) -> dict:
    try:
        from tools.listen import listen as listen_tool
        return listen_tool(
            prompt=prompt,
            timeout_seconds=timeout,
            speak_prompt=speak_prompt,
        )
    except Exception as e:
        return {"success": False, "error": f"Listen failed: {e}"}
