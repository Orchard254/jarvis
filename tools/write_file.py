"""
Write text content to a file.

Safety guardrails:
  - Blocks writes to .ssh, .aws, and common credential paths.
  - Blocks writes to .env files that live outside the Jarvis project directory
    (the project's own .env is explicitly permitted).
  - Returns an error if content exceeds MAX_WRITE_BYTES (10 MB) to prevent
    accidental disk exhaustion.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum number of UTF-8 encoded bytes allowed in a single write operation.
MAX_WRITE_BYTES = 10 * 1024 * 1024  # 10 MB

from safety.path_guard import SENSITIVE_PATH_FRAGMENTS as _BLOCKED_WRITE_FRAGMENTS, contains_sensitive_path

# Root of the Jarvis project — used to decide whether a .env file write is
# inside the project (allowed) or somewhere else on the filesystem (blocked).
_JARVIS_ROOT = Path(__file__).resolve().parents[1]


def _check_blocked_path(p: Path):
    """
    Return (blocked: bool, reason: str).

    Checks:
      1. Whether *p* contains any of the _BLOCKED_WRITE_FRAGMENTS.
      2. Whether *p* is a .env file located outside the Jarvis project tree.
    """
    # Normalise to forward-slash, lower-case for case-insensitive comparison.
    normalized = p.as_posix().lower()

    for frag in _BLOCKED_WRITE_FRAGMENTS:
        if frag in normalized:
            return True, f"writing to '{frag}' paths is not allowed"

    # Block .env files outside the Jarvis project directory.
    # The project's own .env (used by python-dotenv) is explicitly allowed.
    if p.name.lower() == ".env":
        try:
            p.relative_to(_JARVIS_ROOT)
            # Path is inside the project tree — allow it.
        except ValueError:
            return (
                True,
                ".env files outside the Jarvis project directory are not allowed",
            )

    return False, ""


def write_file(path: str, content: str, append: bool = False) -> dict:
    """
    Write *content* to *path*.

    Returns a dict with:
      success    (bool)  – whether the operation succeeded
      path       (str)   – resolved absolute path (only on success)
      size_bytes (int)   – number of bytes written (only on success)
      error      (str)   – human-readable message (only on failure)
    """
    try:
        p = Path(path).expanduser().resolve()

        # ── Sensitive path guard ────────────────────────────────────────────
        blocked, reason = _check_blocked_path(p)
        if blocked:
            logger.warning("write_file: blocked write to sensitive path: %s", p)
            return {"success": False, "error": f"Access denied: {reason}"}

        # ── Size guard ──────────────────────────────────────────────────────
        content_bytes = len(content.encode("utf-8"))
        if content_bytes > MAX_WRITE_BYTES:
            logger.warning(
                "write_file: content too large (%d bytes) for path '%s'",
                content_bytes,
                p,
            )
            return {
                "success": False,
                "error": (
                    f"Content too large: {content_bytes:,} bytes exceeds the "
                    f"{MAX_WRITE_BYTES:,}-byte limit"
                ),
            }

        p.parent.mkdir(parents=True, exist_ok=True)
        
        mode = "a" if append else "w"
        with p.open(mode, encoding="utf-8") as f:
            f.write(content)

        return {"success": True, "path": str(p), "size_bytes": content_bytes}

    except Exception as e:
        return {"success": False, "error": str(e)}
