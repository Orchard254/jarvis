"""
Unified execution and system operations tool.
Actions: run, read, write, clipboard, notify, search_web, fetch

Consolidates code execution, file operations, and utility calls
into a single tool accessed via execute_code imports.
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
    message: str | None = None,
    urgency: str = "low",
    query: str | None = None,
    url: str | None = None,
    background: bool = False,
    timeout: int | None = None,
) -> dict:
    if action == "run":
        return _run_code(code, language, background, timeout)
    elif action == "read":
        return _read_file(path)
    elif action == "write":
        return _write_file(path, content)
    elif action == "clipboard":
        return _clipboard()
    elif action == "notify":
        return _notify(message, urgency)
    elif action == "search_web":
        return _search_web(query)
    elif action == "fetch":
        return _fetch_url(url)
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


def _clipboard() -> dict:
    try:
        from tools.clipboard_tool import clipboard
        return clipboard()
    except Exception as e:
        return {"success": False, "error": f"Clipboard failed: {e}"}


def _notify(message: str | None, urgency: str) -> dict:
    if not message:
        return {"success": False, "error": "message required for notify action"}
    try:
        from tools.notify_user import notify_user
        return notify_user(message=message, urgency=urgency)
    except Exception as e:
        return {"success": False, "error": f"Notify failed: {e}"}


def _search_web(query: str | None) -> dict:
    if not query:
        return {"success": False, "error": "query required for search_web action"}
    try:
        from tools.search_web import search_web
        return search_web(query)
    except Exception as e:
        return {"success": False, "error": f"Web search failed: {e}"}


def _fetch_url(url: str | None) -> dict:
    if not url:
        return {"success": False, "error": "url required for fetch action"}
    try:
        from tools.fetch_url import fetch_url
        return fetch_url(url)
    except Exception as e:
        return {"success": False, "error": f"Fetch URL failed: {e}"}
