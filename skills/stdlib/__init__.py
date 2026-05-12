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
filesystem  read_file, write_file, file_ops, parallel_read
web         search_web, fetch_url, parallel_fetch
system      process_manager, system_settings, install_app, volume_mute_then_set, brightness_set_robust
messaging   send_email, send_telegram, notify

Other tools (control_window, clipboard, network_check, time_calendar) are
available as direct tool calls or by importing from tools.* inside execute_code.
"""

# Manifest — used by prompt_builder to inject docs into the system prompt.
STDLIB_MANIFEST = {
    "filesystem": {
        "module": "skills.stdlib.filesystem",
        "functions": ["read_file", "write_file", "file_ops", "parallel_read"],
        "summary": "read/write files, list dirs, copy/move/delete, mkdir, parallel file reading",
    },
    "web": {
        "module": "skills.stdlib.web",
        "functions": ["search_web", "fetch_url", "parallel_fetch"],
        "summary": "search the web or fetch a URL's text content, parallel URL fetching",
    },
    "system": {
        "module": "skills.stdlib.system",
        "functions": ["process_manager", "system_settings", "install_app", "volume_mute_then_set", "brightness_set_robust"],
        "summary": "list/kill/start processes, change system settings, install apps, volume control (mute-then-set), robust brightness control with fallbacks",
    },
    "messaging": {
        "module": "skills.stdlib.messaging",
        "functions": ["send_email", "send_telegram", "notify"],
        "summary": "send email (SMTP), Telegram message, or desktop toast notification",
    },
}
