"""skills.stdlib.messaging — email, Telegram, and desktop toast notifications."""
from __future__ import annotations

from tools.send_message import send_message
from tools.notify_user import notify_user


def send_email(
    to: str,
    subject: str = "",
    body: str = "",
    html: bool = False,
) -> dict:
    """Send an email via SMTP. Configure SMTP_* in .env."""
    return send_message(backend="email", to=to, subject=subject, body=body, html=html)


def send_telegram(body: str, chat_id: str = "") -> dict:
    """Send a Telegram message. Configure TELEGRAM_* in .env."""
    return send_message(backend="telegram", body=body, chat_id=chat_id)


def notify(title: str, message: str = "", duration: int = 5) -> dict:
    """Show a Windows desktop toast notification."""
    return notify_user(title=title, message=message, duration=duration)


__all__ = ["send_email", "send_telegram", "notify", "send_message", "notify_user"]
