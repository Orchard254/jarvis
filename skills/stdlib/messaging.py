"""skills.stdlib.messaging — desktop toast notifications.

Email and Telegram should be handled by the LLM writing the code
via exec(run). notify_user is kept because it's used by the ambient
monitor and safety executor internally.
"""
from __future__ import annotations

from tools.notify_user import notify_user


def notify(title: str, message: str = "", duration: int = 5) -> dict:
    """Show a Windows desktop toast notification."""
    return notify_user(title=title, message=message, duration=duration)


__all__ = ["notify", "notify_user"]
