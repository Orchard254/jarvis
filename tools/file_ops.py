"""File system operations — list, delete, move, copy, rename, mkdir, exists, search_content."""

import logging
import os
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Blocked-path guard (loaded lazily to avoid circular imports at test time) ─
def _get_blocked_paths() -> list:
    try:
        from settings import BLOCKED_PATHS

        return BLOCKED_PATHS
    except ImportError:
        # Fallback defaults using environment variables for portability
        system_root = os.environ.get("SystemRoot", "C:/Windows")
        return [
            f"{system_root}/System32",
            f"{system_root}/SysWOW64",
            f"{system_root}/Boot",
        ]


def _safe_path(p: str) -> Path:
    return Path(p).expanduser().resolve()


def _is_blocked(p: Path) -> bool:
    blocked = _get_blocked_paths()
    p_str = str(p)
    return any(p_str.startswith(b.replace("/", os.sep)) for b in blocked)


def file_ops(
    action: str,
    path: str = None,
    destination: str = None,
    pattern: str = None,
    recursive: bool = False,
    limit: int = 100,
    # read / write params
    content: str = None,
    append: bool = False,
    line_offset: int = None,
    line_limit: int = None,
) -> dict:
    """
    File system operations.
    Actions: list, delete, move, copy, rename, mkdir, exists, search_content,
             zip, unzip, read, write
    """
    try:
        # ── list ──────────────────────────────────────────────────────────────
        if action == "list":
            if path is None:
                return {"success": False, "error": "action 'list' requires 'path'"}
            try:
                p = _safe_path(path)
            except Exception as e:
                return {"success": False, "error": f"Invalid path: {path} - {e}"}
                
            if not p.exists():
                return {"success": False, "error": f"Path does not exist: {path}"}
            if not p.is_dir():
                return {"success": False, "error": f"Not a directory: {path}"}

            items = []
            try:
                for f in p.iterdir():
                    try:
                        stat = f.stat()
                        items.append(
                            {
                                "name": f.name,
                                "path": str(f),
                                "type": "file" if f.is_file() else "dir",
                                "size_bytes": stat.st_size if f.is_file() else 0,
                                "modified_at": stat.st_mtime,
                            }
                        )
                    except PermissionError:
                        continue
                    if len(items) >= limit:
                        break
            except PermissionError as e:
                return {"success": False, "error": f"Permission denied: {e}"}

            return {
                "success": True,
                "path": str(p),
                "items": items,
                "count": len(items),
                "action": "list",
            }

        # ── delete ────────────────────────────────────────────────────────────
        elif action == "delete":
            if path is None:
                return {"success": False, "error": "action 'delete' requires 'path'"}
            try:
                p = _safe_path(path)
            except Exception as e:
                return {"success": False, "error": f"Invalid path: {path} - {e}"}
                
            if _is_blocked(p):
                return {"success": False, "error": f"Path is protected: {path}"}
            if not p.exists():
                return {"success": False, "error": f"Path does not exist: {path}"}

            try:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    if recursive:
                        shutil.rmtree(p)
                    else:
                        p.rmdir()  # Raises OSError if not empty
            except Exception as e:
                return {"success": False, "error": f"Delete failed: {e}"}
            return {"success": True, "path": str(p), "action": "delete"}

        # ── move ──────────────────────────────────────────────────────────────
        elif action == "move":
            if path is None or destination is None:
                return {
                    "success": False,
                    "error": "action 'move' requires 'path' and 'destination'",
                }
            src = _safe_path(path)
            dst = _safe_path(destination)
            if _is_blocked(src) or _is_blocked(dst):
                return {"success": False, "error": "Path is protected"}
            if not src.exists():
                return {"success": False, "error": f"Source does not exist: {path}"}

            shutil.move(str(src), str(dst))
            return {
                "success": True,
                "source": str(src),
                "destination": str(dst),
                "action": "move",
            }

        # ── copy ──────────────────────────────────────────────────────────────
        elif action == "copy":
            if path is None or destination is None:
                return {
                    "success": False,
                    "error": "action 'copy' requires 'path' and 'destination'",
                }
            src = _safe_path(path)
            dst = _safe_path(destination)
            if not src.exists():
                return {"success": False, "error": f"Source does not exist: {path}"}

            if src.is_file():
                shutil.copy2(str(src), str(dst))
            elif src.is_dir():
                shutil.copytree(str(src), str(dst))
            return {
                "success": True,
                "source": str(src),
                "destination": str(dst),
                "action": "copy",
            }

        # ── rename ────────────────────────────────────────────────────────────
        elif action == "rename":
            if path is None or destination is None:
                return {
                    "success": False,
                    "error": "action 'rename' requires 'path' and 'destination'",
                }
            src = _safe_path(path)
            dst = _safe_path(destination)
            if _is_blocked(src):
                return {"success": False, "error": "Path is protected"}
            if _is_blocked(dst):
                return {"success": False, "error": "Destination is protected"}
            if not src.exists():
                return {"success": False, "error": f"Path does not exist: {path}"}

            src.rename(dst)
            return {
                "success": True,
                "source": str(src),
                "destination": str(dst),
                "action": "rename",
            }

        # ── mkdir ─────────────────────────────────────────────────────────────
        elif action == "mkdir":
            if path is None:
                return {"success": False, "error": "action 'mkdir' requires 'path'"}
            try:
                p = _safe_path(path)
            except Exception as e:
                return {"success": False, "error": f"Invalid path: {path} - {e}"}
            if _is_blocked(p):
                return {"success": False, "error": f"Path is protected: {path}"}
            p.mkdir(parents=True, exist_ok=True)
            return {"success": True, "path": str(p.resolve()), "action": "mkdir"}

        # ── exists ────────────────────────────────────────────────────────────
        elif action == "exists":
            if path is None:
                return {"success": False, "error": "action 'exists' requires 'path'"}
            p = _safe_path(path)
            exists = p.exists()
            ftype = "file" if p.is_file() else ("dir" if p.is_dir() else None)
            return {
                "success": True,
                "path": str(p),
                "exists": exists,
                "type": ftype,
                "action": "exists",
            }

        # ── search_content ────────────────────────────────────────────────────
        elif action == "search_content":
            if path is None or pattern is None:
                return {
                    "success": False,
                    "error": "action 'search_content' requires 'path' and 'pattern'",
                }
            p = _safe_path(path)
            if not p.exists():
                return {"success": False, "error": f"Path does not exist: {path}"}

            matches = []
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return {"success": False, "error": f"Invalid regex pattern: {e}"}

            walk_root = [p] if p.is_file() else []
            if p.is_dir():
                walker = p.rglob("*") if recursive else p.glob("*")
                walk_root = [f for f in walker if f.is_file()]

            for filepath in walk_root:
                if len(matches) >= limit:
                    break
                try:
                    with filepath.open("r", encoding="utf-8", errors="replace") as fh:
                        for lineno, line in enumerate(fh, 1):
                            m = compiled.search(line)
                            if m:
                                matches.append(
                                    {
                                        "file": str(filepath),
                                        "line_number": lineno,
                                        "line": line.rstrip("\n"),
                                        "match": m.group(0),
                                    }
                                )
                                if len(matches) >= limit:
                                    break
                except (UnicodeDecodeError, PermissionError):
                    continue  # skip binary / inaccessible files

            return {
                "success": True,
                "pattern": pattern,
                "path": str(p),
                "matches": matches,
                "count": len(matches),
                "action": "search_content",
            }

        # ── zip ───────────────────────────────────────────────────────────────
        elif action == "zip":
            if path is None or destination is None:
                return {
                    "success": False,
                    "error": "action 'zip' requires 'path' and 'destination' (the zip file path)",
                }
            src = _safe_path(path)
            dst = _safe_path(destination)
            if not src.exists():
                return {"success": False, "error": f"Source does not exist: {path}"}
            
            # shutil.make_archive expects base name without extension
            base_name = str(dst)
            if base_name.endswith('.zip'):
                base_name = base_name[:-4]
                
            try:
                shutil.make_archive(base_name, 'zip', str(src))
            except Exception as e:
                return {"success": False, "error": f"Zip failed: {e}"}
                
            return {
                "success": True,
                "source": str(src),
                "destination": f"{base_name}.zip",
                "action": "zip",
            }

        # ── unzip ─────────────────────────────────────────────────────────────
        elif action == "unzip":
            if path is None or destination is None:
                return {
                    "success": False,
                    "error": "action 'unzip' requires 'path' (zip file) and 'destination' (extract folder)",
                }
            src = _safe_path(path)
            dst = _safe_path(destination)
            if not src.exists():
                return {"success": False, "error": f"Source zip does not exist: {path}"}
                
            try:
                shutil.unpack_archive(str(src), str(dst), 'zip')
            except Exception as e:
                return {"success": False, "error": f"Unzip failed: {e}"}
                
            return {
                "success": True,
                "source": str(src),
                "destination": str(dst),
                "action": "unzip",
            }

        # ── read ──────────────────────────────────────────────────────────────
        elif action == "read":
            if path is None:
                return {"success": False, "error": "action 'read' requires 'path'"}

            from safety.path_guard import SENSITIVE_PATH_FRAGMENTS as _BLOCKED_READ, contains_sensitive_path
            MAX_READ = 10 * 1024 * 1024  # 10 MB

            try:
                p = _safe_path(path)
            except Exception as e:
                return {"success": False, "error": f"Invalid path: {e}"}

            norm = p.as_posix().lower()
            if any(frag in norm for frag in _BLOCKED_READ):
                return {"success": False, "error": f"Access denied: blocked path '{path}'"}
            if not p.exists():
                return {"success": False, "error": f"File not found: {path}"}
            if not p.is_file():
                return {"success": False, "error": f"Not a file: {path}"}

            file_size = p.stat().st_size

            if line_offset is not None or line_limit is not None:
                offset = line_offset or 0
                lim = line_limit if line_limit is not None else -1
                lines = []
                with p.open("r", encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        if i < offset:
                            continue
                        if lim != -1 and len(lines) >= lim:
                            break
                        lines.append(line)
                file_content = "".join(lines)
                truncated = len(file_content.encode("utf-8")) > MAX_READ
                if truncated:
                    file_content = file_content.encode("utf-8")[:MAX_READ].decode("utf-8", errors="replace")
                    file_content += "\n\n[TRUNCATED]"
            elif file_size <= MAX_READ:
                file_content = p.read_text(encoding="utf-8", errors="replace")
                truncated = False
            else:
                with p.open("rb") as fh:
                    file_content = fh.read(MAX_READ).decode("utf-8", errors="replace")
                file_content += f"\n\n[TRUNCATED — {file_size:,} bytes total, first {MAX_READ:,} shown]"
                truncated = True

            return {
                "success": True,
                "action": "read",
                "path": str(p),
                "content": file_content,
                "size_bytes": file_size,
                "truncated": truncated,
            }

        # ── write ─────────────────────────────────────────────────────────────
        elif action == "write":
            if path is None:
                return {"success": False, "error": "action 'write' requires 'path'"}
            if content is None:
                return {"success": False, "error": "action 'write' requires 'content'"}

            from safety.path_guard import SENSITIVE_PATH_FRAGMENTS as _BLOCKED_WRITE
            MAX_WRITE = 10 * 1024 * 1024  # 10 MB

            try:
                p = _safe_path(path)
            except Exception as e:
                return {"success": False, "error": f"Invalid path: {e}"}

            norm = p.as_posix().lower()
            if any(frag in norm for frag in _BLOCKED_WRITE):
                return {"success": False, "error": f"Access denied: blocked path '{path}'"}

            # Block .env files outside the Jarvis project directory
            if p.name.lower() == ".env":
                _jarvis_root = Path(__file__).resolve().parents[1]
                try:
                    p.relative_to(_jarvis_root)
                except ValueError:
                    return {"success": False, "error": ".env files outside the Jarvis project directory are not allowed"}

            content_bytes = len(content.encode("utf-8"))
            if content_bytes > MAX_WRITE:
                return {
                    "success": False,
                    "error": f"Content too large: {content_bytes:,} bytes exceeds {MAX_WRITE:,}-byte limit",
                }

            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with p.open(mode, encoding="utf-8") as fh:
                fh.write(content)

            return {
                "success": True,
                "action": "write",
                "path": str(p),
                "size_bytes": content_bytes,
                "append": append,
            }

        else:
            return {"success": False, "error": f"Unknown action: '{action}'"}

    except Exception as e:
        logger.error(f"file_ops({action}): {e}")
        return {"success": False, "error": str(e)}
