"""
File Sub-Agent — file operations: read, write, search, move, organize.

Handles tasks like:
  - "Find all PDFs in Documents modified this month"
  - "Read the contents of report.txt and return them"
  - "Write a summary to ~/Desktop/notes.txt"
  - "Move all screenshots from Downloads to Pictures/Screenshots"
  - "Create a folder structure for a new project"

Reports file paths, contents, and outcomes to Jarvis.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register

logger = logging.getLogger(__name__)


class FileAgent(SubAgentBase):
    name = "file"
    description = (
        "File system operations: reading, writing, searching, moving, and organizing files. "
        "Use for any task involving local files or folders."
    )
    capabilities = [
        "read_file",
        "write_file",
        "search_files",
        "move_file",
        "delete_file",
        "create_file",
        "open_file",
        "download_file",
    ]

    def run(self, task: SubAgentTask) -> SubAgentResult:
        start = time.time()
        tool_log: list[dict] = []
        goal = task.goal
        ctx = task.context
        errors: list[str] = []
        results: dict = {}

        self._log.info(f"[{task.task_id}] File task: {goal[:100]}")

        action = ctx.get("action", "auto")

        # ── READ ─────────────────────────────────────────────────────────────
        if action in ("read", "auto") and "path" in ctx:
            path = ctx["path"]
            max_chars = int(ctx.get("max_chars", 8000))
            ok, result = self._tool_ok("read_file", path=path, max_chars=max_chars)
            tool_log.append({"tool": "read_file", "path": path, **result})
            if ok:
                results["content"] = result.get("content", "")
                results["path"] = path
                results["truncated"] = result.get("truncated", False)
                results["total_bytes"] = result.get("total_bytes", 0)
            else:
                errors.append(f"read_file({path}): {result.get('error', '?')}")

        # ── WRITE ─────────────────────────────────────────────────────────────
        if action in ("write", "auto") and "write_path" in ctx and "content" in ctx:
            path = ctx["write_path"]
            content = ctx["content"]
            ok, result = self._tool_ok("write_file", path=path, content=content)
            tool_log.append({"tool": "write_file", "path": path, **result})
            if ok:
                results["written_path"] = path
                results["written_chars"] = len(content)
            else:
                errors.append(f"write_file({path}): {result.get('error', '?')}")

        # ── SEARCH ────────────────────────────────────────────────────────────
        if action in ("search", "auto") and "pattern" in ctx:
            pattern = ctx["pattern"]
            location = ctx.get("location", str(Path.home()))
            max_results = int(ctx.get("max_results", 20))
            ok, result = self._tool_ok(
                "search_files",
                pattern=pattern,
                location=location,
                max_results=max_results,
            )
            tool_log.append({"tool": "search_files", "pattern": pattern, **result})
            if ok:
                results["found_files"] = result.get("results", [])
                results["file_count"] = result.get("count", 0)
            else:
                errors.append(f"search_files({pattern}): {result.get('error', '?')}")

        # ── MOVE / RENAME ──────────────────────────────────────────────────────
        if action in ("move", "rename") and "source" in ctx and "destination" in ctx:
            src = ctx["source"]
            dst = ctx["destination"]
            ok, result = self._tool_ok("move_file", source=src, destination=dst)
            tool_log.append({"tool": "move_file", "source": src, "destination": dst, **result})
            if ok:
                results["moved"] = {"from": src, "to": dst}
            else:
                errors.append(f"move_file({src} → {dst}): {result.get('error', '?')}")

        # ── BULK MOVE (list of {source, destination}) ──────────────────────────
        if action == "bulk_move" and "moves" in ctx:
            moved = []
            for m in ctx["moves"]:
                ok, result = self._tool_ok("move_file", source=m["source"], destination=m["destination"])
                tool_log.append({"tool": "move_file", **result})
                if ok:
                    moved.append({"from": m["source"], "to": m["destination"]})
                else:
                    errors.append(f"move_file({m['source']}): {result.get('error', '?')}")
            results["moved"] = moved

        # ── CREATE ────────────────────────────────────────────────────────────
        if action == "create" and "path" in ctx:
            path = ctx["path"]
            ok, result = self._tool_ok("create_file", path=path)
            tool_log.append({"tool": "create_file", "path": path, **result})
            if ok:
                results["created_path"] = path
            else:
                errors.append(f"create_file({path}): {result.get('error', '?')}")

        # ── DELETE ────────────────────────────────────────────────────────────
        if action == "delete" and "path" in ctx:
            path = ctx["path"]
            ok, result = self._tool_ok("delete_file", path=path)
            tool_log.append({"tool": "delete_file", "path": path, **result})
            if ok:
                results["deleted_path"] = path
            else:
                errors.append(f"delete_file({path}): {result.get('error', '?')}")

        # ── Build summary ──────────────────────────────────────────────────────
        elapsed = round(time.time() - start, 2)
        success = bool(results) and not (errors and not results)

        summary_parts = [f"File agent completed '{goal[:80]}':"]

        if "content" in results:
            chars = len(results["content"])
            trunc = " (truncated)" if results.get("truncated") else ""
            summary_parts.append(f"  Read {chars} chars from {results['path']}{trunc}")
            summary_parts.append(f"  Content preview: {results['content'][:300]}...")

        if "written_path" in results:
            summary_parts.append(
                f"  Wrote {results['written_chars']} chars to {results['written_path']}"
            )

        if "found_files" in results:
            count = results["file_count"]
            summary_parts.append(f"  Found {count} file(s) matching the search:")
            for f in results["found_files"][:10]:
                size_kb = round(f.get("size", 0) / 1024, 1)
                summary_parts.append(f"    - {f['path']} ({size_kb} KB)")

        if "moved" in results:
            moved = results["moved"]
            if isinstance(moved, list):
                summary_parts.append(f"  Moved {len(moved)} file(s).")
            else:
                summary_parts.append(f"  Moved {moved['from']} → {moved['to']}")

        if "created_path" in results:
            summary_parts.append(f"  Created: {results['created_path']}")

        if "deleted_path" in results:
            summary_parts.append(f"  Deleted: {results['deleted_path']}")

        if errors:
            summary_parts.append(f"  Errors: {'; '.join(errors)}")

        if len(summary_parts) == 1:
            summary_parts.append("  No file operations performed (check context keys).")

        return SubAgentResult(
            success=success,
            summary="\n".join(summary_parts),
            data=results,
            error="; ".join(errors) if not success else "",
            tool_calls=tool_log,
            elapsed_s=elapsed,
            agent_name=self.name,
        )


register(FileAgent())
