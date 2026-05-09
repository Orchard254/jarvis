"""
Immutable pre/post execution log. JSON lines format.
"""

import json
import logging
import time
from pathlib import Path

from settings import LOGS_DIR

logger = logging.getLogger(__name__)
_log_file = LOGS_DIR / "audit.log"
_MAX_BYTES = 10 * 1024 * 1024  # rotate at 10 MB


def setup():
    _log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Audit log initialized: {_log_file}")


def _write(entry: dict) -> None:
    """Append one JSON-lines entry, rotating the file at 10 MB."""
    try:
        if _log_file.exists() and _log_file.stat().st_size >= _MAX_BYTES:
            _log_file.rename(_log_file.with_suffix(".log.1"))
        with open(_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as exc:
        # Never let an audit-log failure propagate to the tool caller
        logger.error(f"audit_log write failed: {exc}")


def log_call(tool_name: str, args: dict, result) -> None:
    success = False
    error = None
    returncode = None
    if isinstance(result, dict):
        success = result.get("success", False)
        error = result.get("error")
        returncode = result.get("returncode")
    elif isinstance(result, list):
        success = True
    _write(
        {
            "ts": time.time(),
            "tool": tool_name,
            "args": args,
            "success": success,
            "error": error,
            "returncode": returncode,
        }
    )


def log_blocked(tool_name: str, args: dict, reason: str) -> None:
    _write(
        {
            "ts": time.time(),
            "tool": tool_name,
            "args": args,
            "blocked": True,
            "reason": reason,
        }
    )
