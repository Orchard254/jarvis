"""
Plan validator — scans code/commands for destructive patterns before execution.
"""

import logging
import re

logger = logging.getLogger(__name__)

_DANGEROUS: list[tuple[str, str]] = [
    (r"\brm\s+-[rRfF]{1,3}\b", "Destructive recursive delete (rm -rf)"),
    (r"\bdel\s+/[sS]", "Destructive del command"),
    (r"\brd\s+/[sS]", "Recursive directory removal (rd /s)"),
    (r"\bformat\s+[a-zA-Z]:", "Disk format command"),
    (r"\breg\s+delete\b", "Windows registry deletion"),
    (r"\bdiskpart\b", "Disk partition tool (diskpart)"),
    (r"\bbcdedit\b", "Boot configuration edit (bcdedit)"),
    (r"shutil\.rmtree", "Recursive directory removal (shutil.rmtree)"),
    (r"winreg\.DeleteKey|winreg\.DeleteValue", "Windows registry deletion (winreg)"),
    # exec/eval/compile/__import__ are covered by AST checks in tool_guard.py
]

_TEMP_CONTEXT = re.compile(
    r"tempfile|gettempdir|%TEMP%|%TMP%|LOCALAPPDATA"
    r"|[/\\\\]Temp[/\\\\'\"]|\btemp|\btmp|\bcache\b|\bcleanup\b",
    re.IGNORECASE,
)

_TEMP_LIFTABLE = frozenset({
    "Recursive directory removal (shutil.rmtree)",
})


def validate(plan: dict) -> tuple[bool, str]:
    if not plan:
        return True, ""

    surfaces: list[str] = []
    for key in ("code", "command"):
        val = plan.get(key)
        if isinstance(val, str):
            surfaces.append(val)
        elif isinstance(val, dict):
            surfaces.append(str(val))

    combined = "\n".join(surfaces)
    if not combined.strip():
        return True, ""

    for pattern, reason in _DANGEROUS:
        if not re.search(pattern, combined, re.IGNORECASE):
            continue
        if reason in _TEMP_LIFTABLE and _TEMP_CONTEXT.search(combined):
            continue
        logger.warning(f"plan_validator: BLOCKED — {reason}")
        return False, f"Blocked: {reason}"

    return True, ""
