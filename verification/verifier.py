"""
3-tier router. Returns structured text report ONLY.

For execute_code, additionally checks jarvis.log for ERROR/Traceback
lines as an independent verification signal — catches silent failures
that the tool's own success flag might miss.
"""

import logging
import os
import re

from settings import LOG_FILE

logger = logging.getLogger(__name__)


def verify_action(tool_name: str, result: dict, expected: str = "") -> dict:
    if result.get("success") is False:
        return {
            "status": "FAILED",
            "method": "result",
            "summary": result.get("error") or f"{tool_name} failed.",
        }

    # For execute_code, cross-check against the log for silent failures
    if tool_name == "execute_code":
        log_result = _check_log_for_failures()
        if log_result:
            return {
                "status": "FAILED",
                "method": "log_check",
                "summary": log_result,
            }

    return {
        "status": "CONFIRMED",
        "method": "result",
        "summary": f"{tool_name} completed.",
    }


_FAILURE_PATTERNS = re.compile(
    r"^(.*\b(ERROR|Traceback|Exception|Failed|CRITICAL)\b.*)$",
    re.MULTILINE,
)


def _check_log_for_failures(lines: int = 30) -> str:
    """
    Read the last *lines* lines of jarvis.log and check for failure signals.
    Returns a human-readable summary if failures found, or empty string if clean.
    """
    path = LOG_FILE
    if not os.path.isfile(path):
        return ""

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            # Efficient tail: seek near end and read
            f.seek(0, 2)
            file_size = f.tell()
            # Read up to 8KB from the end
            chunk_size = min(file_size, 8192)
            f.seek(file_size - chunk_size)
            tail = f.read()

        matches = _FAILURE_PATTERNS.findall(tail)
        if not matches:
            return ""

        # Deduplicate and take the last 3 distinct failure lines
        seen: set[str] = set()
        failure_lines: list[str] = []
        for full_line, *_ in reversed(matches):
            key = full_line.strip()
            if key and key not in seen:
                seen.add(key)
                failure_lines.append(key)
                if len(failure_lines) >= 3:
                    break

        if failure_lines:
            snippet = " | ".join(reversed(failure_lines))
            return f"Log shows recent errors: {snippet}"

        return ""

    except Exception as exc:
        logger.debug(f"Log check skipped: {exc}")
        return ""
