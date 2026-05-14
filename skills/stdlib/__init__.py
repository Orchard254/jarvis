"""
skills.stdlib — Standard Library Skills
========================================
Minimal set of pre-written helpers the LLM can import inside exec(run).

Philosophy: if the LLM can write the code, it's NOT a tool — it's a skill.
Most tasks should be done by the LLM writing code via exec(run) or using
the 6 core tools (screen, input, window, browser, exec, memory).

These stdlib modules only exist for things that genuinely benefit from
pre-built, tested implementations (like volume control with pycaw fallback).

Modules
-------
filesystem  read_file, write_file (used by exec facade)
system      volume_mute_then_set, brightness_set_robust
messaging   notify (desktop toast via notify_user)
"""

# Manifest — used by prompt_builder to inject docs into the system prompt.
STDLIB_MANIFEST = {
    "filesystem": {
        "module": "skills.stdlib.filesystem",
        "functions": ["read_file", "write_file"],
        "summary": "read/write files (used by exec facade internally)",
    },
    "system": {
        "module": "skills.stdlib.system",
        "functions": ["volume_mute_then_set", "brightness_set_robust"],
        "summary": "volume control (pycaw + keypress fallback), brightness control (sbc + WMI + keypress fallback)",
    },
    "messaging": {
        "module": "skills.stdlib.messaging",
        "functions": ["notify"],
        "summary": "desktop toast notification",
    },
}
