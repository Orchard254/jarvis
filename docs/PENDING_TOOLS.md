# PENDING_TOOLS.md

> **All tools in this file have been implemented (Phase 3).**
> See the individual files and `tools/__init__.py`.

## ✅ ask_user — `tools/ask_user.py`
- tkinter dialog (free-text or button choices) + console fallback.
- Thread-safe: works from background tool-loop thread.
- Configurable `timeout_seconds` auto-closes; returns `{answer, cancelled}`.

## ✅ time_calendar — `tools/time_calendar.py`
- `get_events` / `create_event` / `delete_event` on **outlook** or **ics** backend.
- `get_time` removed from tool schema (gpt-oss knows the date); still accessible via `skills.stdlib.time_cal.get_time()`.
- Backend via `CALENDAR_BACKEND` in `.env`.

## ✅ listen — `tools/listen.py`
- Speaks optional TTS prompt, then captures one utterance.
- Sets/clears `settings.STT_EXCLUSIVE` to pause the wake-word listener.
- `transcribe_once()` added to `perception/stt.py`.

## ✅ watch_screen — `tools/watch_screen.py`
- Polls `vision_query` at configurable interval.
- Pixel-diff pre-filter skips vision when screen hasn't changed.
- Cancellable via threading.Event.

## ✅ send_message — `tools/send_message.py`
- **email** via stdlib `smtplib` (STARTTLS; works with Gmail App Passwords).
- **telegram** via raw Bot API, stdlib `urllib` — no extra deps.
- Credentials in `.env`: `SMTP_*` and `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.

## Summary

| Tool | Status | File |
|---|---|---|---|
| `ask_user` | ✅ Done | `tools/ask_user.py` |
| `time_calendar` | ✅ Done (collapsed: `get_time`) | `tools/time_calendar.py` |
| `listen` | ✅ Done | `tools/listen.py` |
| `watch_screen` | ✅ Done | `tools/watch_screen.py` |
| `send_message` | ✅ Done | `tools/send_message.py` |
