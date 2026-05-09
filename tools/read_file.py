"""
Read a text file and return its contents.

Safety guardrails:
  - Blocks access to .ssh, .aws, and common credential paths.
  - Caps the read at MAX_READ_BYTES (10 MB); larger files are truncated and
    a notice is appended so the caller knows the content is incomplete.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum number of bytes to read from a single file.  Reading beyond this
# limit risks exhausting process memory on large log files, database dumps, etc.
MAX_READ_BYTES = 10 * 1024 * 1024  # 10 MB

# Path fragments that must never be read — SSH keys, cloud-provider credential
# directories, and other common credential files.
_BLOCKED_READ_FRAGMENTS = (
    ".ssh",
    ".aws",
    ".gnupg",
    ".gpg",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "authorized_keys",
    "known_hosts",
    ".netrc",
    ".pgpass",
    "credentials",
    ".kube/config",
    "kubeconfig",
)


def _is_blocked_path(p: Path) -> bool:
    """Return True if *p* matches any sensitive path fragment."""
    # Normalise to forward-slash, lower-case for case-insensitive comparison
    # on Windows where paths are case-insensitive.
    normalized = p.as_posix().lower()
    return any(frag in normalized for frag in _BLOCKED_READ_FRAGMENTS)


def read_file(path: str) -> dict:
    """
    Read a text file at *path* and return its contents.

    Returns a dict with:
      success    (bool)   – whether the operation succeeded
      content    (str)    – file text (only on success)
      path       (str)    – resolved absolute path (only on success)
      size_bytes (int)    – total file size in bytes (only on success)
      truncated  (bool)   – True if the file was larger than MAX_READ_BYTES
      error      (str)    – human-readable message (only on failure)
    """
    try:
        p = Path(path).expanduser().resolve()

        # ── Sensitive path guard ────────────────────────────────────────────
        if _is_blocked_path(p):
            logger.warning("read_file: blocked read of sensitive path: %s", p)
            return {"success": False, "error": f"Access denied: blocked path '{path}'"}

        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}

        if not p.is_file():
            return {"success": False, "error": f"Not a file: {path}"}

        file_size = p.stat().st_size

        # ── Size guard and Line extraction ──────────────────────────────────
        if line_offset is not None or line_limit is not None:
            # When extracting specific lines, we still read within the MAX_READ_BYTES limit
            # but we parse lines.
            lines = []
            offset = line_offset or 0
            limit = line_limit if line_limit is not None else -1
            
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i < offset:
                        continue
                    if limit != -1 and len(lines) >= limit:
                        break
                    lines.append(line)
            
            content = "".join(lines)
            truncated = False # Since we're explicitly asking for lines, we don't consider it truncated
            
            # Still check overall size if they ask for too many lines
            if len(content.encode('utf-8')) > MAX_READ_BYTES:
                content = content.encode('utf-8')[:MAX_READ_BYTES].decode('utf-8', errors='replace')
                content += (
                    f"\n\n[TRUNCATED — line limit exceeded {MAX_READ_BYTES:,} bytes]"
                )
                truncated = True
        else:
            if file_size <= MAX_READ_BYTES:
                content = p.read_text(encoding="utf-8", errors="replace")
                truncated = False
            else:
                # Read only the first MAX_READ_BYTES to prevent OOM on huge files.
                with p.open("rb") as fh:
                    raw = fh.read(MAX_READ_BYTES)
                content = raw.decode("utf-8", errors="replace")
                content += (
                    f"\n\n[TRUNCATED — file is {file_size:,} bytes; "
                    f"only the first {MAX_READ_BYTES:,} bytes were returned]"
                )
                truncated = True
                logger.info(
                    "read_file: '%s' is %d bytes — truncated to %d bytes",
                    p,
                    file_size,
                    MAX_READ_BYTES,
                )

        return {
            "success": True,
            "content": content,
            "path": str(p),
            "size_bytes": file_size,
            "truncated": truncated,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
