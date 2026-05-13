"""
Unified execution tool.
Actions: run, read, write

The LLM's escape hatch — run Python/PowerShell code and manage files.
For anything not covered by dedicated tools, use exec(run).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def exec(
    action: str = "run",
    code: str | None = None,
    language: str = "python",
    path: str | None = None,
    content: str | None = None,
    background: bool = False,
    timeout: int | None = None,
) -> dict:
    if action == "run":
        return _run_code(code, language, background, timeout)
    elif action == "read":
        return _read_file(path)
    elif action == "write":
        return _write_file(path, content)
    return {"success": False, "error": f"Unknown exec action: {action}"}


def _run_code(
    code: str | None, language: str, background: bool, timeout: int | None,
) -> dict:
    if not code:
        return {"success": False, "error": "code required for run action"}
    try:
        from tools.execute_code import execute_code
        kwargs = {"code": code, "language": language, "background": background}
        if timeout:
            kwargs["timeout"] = timeout
        return execute_code(**kwargs)
    except Exception as e:
        return {"success": False, "error": f"Code execution failed: {e}"}


def _read_file(path: str | None) -> dict:
    if not path:
        return {"success": False, "error": "path required for read action"}
    try:
        from tools.read_file import read_file
        return read_file(path)
    except Exception as e:
        return {"success": False, "error": f"Read file failed: {e}"}


def _write_file(path: str | None, content: str | None) -> dict:
    if not path or content is None:
        return {"success": False, "error": "path and content required for write action"}
    try:
        from tools.write_file import write_file
        return write_file(path=path, content=content)
    except Exception as e:
        return {"success": False, "error": f"Write file failed: {e}"}
