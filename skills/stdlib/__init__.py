"""
skills.stdlib — Standard Library Skills
========================================
Pre-written, audited Python modules the LLM imports inside execute_code
instead of reinventing common operations from scratch.

These are NOT tool schemas — the LLM does not call them via the tool protocol.
Instead, it writes Python in execute_code and imports what it needs:

    from skills.stdlib.web import search_web, fetch_url
    results = search_web("best Python libraries 2025")

    from skills.stdlib.filesystem import read_file, write_file
    content = read_file("~/notes.txt")  # Cross-platform home directory

    from skills.stdlib.messaging import send_email, notify
    send_email(to="me@gmail.com", subject="Done", body="Task finished.")

All functions return a dict with at minimum {"success": bool}.

Modules
-------
filesystem  read_file, write_file, file_ops
web         search_web, fetch_url
system      process_manager, system_settings, open_app, install_app
ui          clipboard, control_input, control_window
messaging   send_email, send_telegram, notify
network     network_check
time_cal    get_time, get_events, create_event, delete_event
"""

# Manifest — used by prompt_builder to inject docs into the system prompt.
STDLIB_MANIFEST = {
    "filesystem": {
        "module": "skills.stdlib.filesystem",
        "functions": ["read_file", "write_file", "file_ops"],
        "summary": "read/write files, list dirs, copy/move/delete, mkdir",
    },
    "web": {
        "module": "skills.stdlib.web",
        "functions": ["search_web", "fetch_url"],
        "summary": "search the web or fetch a URL's text content",
    },
    "system": {
        "module": "skills.stdlib.system",
        "functions": ["process_manager", "system_settings", "open_app", "install_app"],
        "summary": "list/kill/start processes, change system settings, open or install apps",
    },
    "ui": {
        "module": "skills.stdlib.ui",
        "functions": ["clipboard", "control_input", "control_window"],
        "summary": "clipboard read/write, keyboard/mouse input, window resize/move/close",
    },
    "messaging": {
        "module": "skills.stdlib.messaging",
        "functions": ["send_email", "send_telegram", "notify"],
        "summary": "send email (SMTP), Telegram message, or desktop toast notification",
    },
    "network": {
        "module": "skills.stdlib.network",
        "functions": ["network_check"],
        "summary": "ping, DNS lookup, download speed test, list connections/interfaces",
    },
    "time_cal": {
        "module": "skills.stdlib.time_cal",
        "functions": ["get_time", "get_events", "create_event", "delete_event"],
        "summary": "current date/time/timezone, Outlook/ICS calendar CRUD",
    },
}
