"""
Primitive: query_pc_index(query, type=None)
Read-only interface to PC Index. Never writes.
"""

import json
import logging
import sqlite3
from pathlib import Path

from settings import PC_INDEX_DB
from core.thread_db import get_connection

logger = logging.getLogger(__name__)


def query_pc_index(query: str, type: str = None) -> dict:  # noqa: A002
    if not PC_INDEX_DB.exists():
        return {"success": False, "error": "PC index not initialized.", "results": []}

    results = []
    # Strip common extensions so "OpenCode.exe" matches "OpenCode"
    clean = query.lower().replace(".exe", "").replace(".lnk", "").replace(".msi", "")
    q = f"%{clean}%"

    try:
        conn = get_connection(PC_INDEX_DB, timeout=2.0)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
    except Exception as e:
        return {"success": False, "error": f"DB read error: {e}", "results": []}
    

    try:
        if type in (None, "app"):
            for r in c.execute(
                "SELECT name, exe_path, version, source FROM apps WHERE lower(name) LIKE ? OR lower(exe_path) LIKE ? ORDER BY name LIMIT 8",
                (q, q),
            ):
                results.append(
                    {
                        "type": "app",
                        "name": r["name"],
                        "path": r["exe_path"],
                        "extra": {"version": r["version"], "source": r["source"]},
                    }
                )

        if type in (None, "file"):
            for r in c.execute(
                "SELECT filename, full_path, size_bytes, directory FROM files WHERE lower(filename) LIKE ? ORDER BY modified_at DESC LIMIT 8",
                (q,),
            ):
                results.append(
                    {
                        "type": "file",
                        "name": r["filename"],
                        "path": r["full_path"],
                        "extra": {"size_bytes": r["size_bytes"], "dir": r["directory"]},
                    }
                )

        if type in (None, "state"):
            row = c.execute(
                "SELECT windows_json, processes_json, focused_app FROM state_snapshots ORDER BY captured_at DESC LIMIT 1"
            ).fetchone()
            if row:
                # Search open windows
                wins = json.loads(row["windows_json"] or "[]")
                for w in wins:
                    if query.lower() in w.get("title", "").lower():
                        results.append(
                            {
                                "type": "window",
                                "name": w["title"],
                                "path": None,
                                "extra": {
                                    "rect": {
                                        k: w[k]
                                        for k in ["left", "top", "width", "height"]
                                        if k in w
                                    }
                                },
                            }
                        )
                # Search running processes
                # NOTE: state_monitor stores processes as a list of plain
                # strings (process names), NOT dicts.  Guard against both
                # formats so this never raises AttributeError.
                procs = json.loads(row["processes_json"] or "[]")
                for p in procs:
                    if isinstance(p, dict):
                        pname = p.get("name", "")
                        ppath = p.get("exe", "")
                        ppid = p.get("pid")
                        pstat = p.get("status", "running")
                    else:
                        # Plain string — just the process name
                        pname = str(p)
                        ppath = ""
                        ppid = None
                        pstat = "running"
                    if query.lower() in pname.lower():
                        results.append(
                            {
                                "type": "process",
                                "name": pname,
                                "path": ppath,
                                "extra": {"pid": ppid, "status": pstat},
                            }
                        )
    except Exception as e:
        logger.error(f"query_pc_index error: {e}")

    logger.info(f"query_pc_index('{query}', type={type}) -> {len(results)} results")
    return {"success": True, "results": results, "count": len(results), "query": query}
