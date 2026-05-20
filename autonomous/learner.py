"""
Autonomous self-learner — practices tools during idle time, builds skills.

The learner runs as a background thread. When the user is idle (no keyboard/mouse
input for N minutes), it discovers knowledge gaps (tools with zero/few attempts
or low success rates), practices them safely, and records results.
"""

import logging
import threading
import time
from typing import Callable

from core.thread_db import get_connection
from settings import MEMORY_DB

logger = logging.getLogger(__name__)

# Tools too dangerous for autonomous practice (write, destructive, communication)
_DANGEROUS_TOOLS = {
    "shutdown", "restart", "lock_screen", "kill_process",
    "delete_file", "write_file", "move_file", "create_file",
    "execute_code", "run_python",
    "send_message", "speak",
    "write_clipboard",
    "manage_app", "query_system", "query_ui",  # intent-level stubs
}

# Read-only tools — always safe to practice unsupervised
_READ_ONLY_TOOLS = {
    "list_running_apps", "get_process_info", "get_system_stats",
    "get_battery", "list_installed_apps", "get_active_window",
    "get_window_bounds", "read_clipboard", "search_files",
    "read_file", "time_calendar", "screenshot", "read_screen",
    "open_url", "web_search", "fetch_page",
    "retrieve_memory", "search_memory", "summarize_session",
}

# Safe default parameter values for autonomous practice
_SAFE_DEFAULTS = {
    "name": "notepad",
    "target": "notepad",
    "title": "Untitled - Notepad",
    "text": "hello world",
    "path": ".",
    "query": "python",
    "url": "https://example.com",
    "message": "auto-learner test",
    "action": "get_time",
    "what": "running_apps",
    "key": "test_key",
    "source": "clipboard",
    "direction": "down",
    "clicks": 1,
    "x": 100,
    "y": 100,
}


def _init_curriculum_db():
    conn = get_connection(MEMORY_DB, timeout=5.0)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS learner_curriculum (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            topic_type TEXT NOT NULL DEFAULT 'tool',
            attempts INTEGER DEFAULT 0,
            successes INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            last_practiced REAL,
            status TEXT DEFAULT 'discovered',
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_curriculum_topic
        ON learner_curriculum(topic, topic_type)
    """)
    conn.commit()


def _get_idle_minutes() -> float:
    """Return minutes since last user input (keyboard/mouse) via Windows API."""
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            tick = ctypes.windll.kernel32.GetTickCount()
            return (tick - lii.dwTime) / 60000.0
    except Exception as exc:
        logger.debug(f"Idle detection unavailable: {exc}")
    return 0.0


class AutoLearner:
    """Background learner that safely practices tools during idle time."""

    def __init__(
        self,
        tool_registry: dict,
        tool_fn: Callable,
        idle_threshold_minutes: int = 5,
        min_practice_interval_minutes: int = 30,
        poll_interval_seconds: int = 60,
    ):
        self._tool_registry = tool_registry
        self._tool_fn = tool_fn
        self._idle_threshold = idle_threshold_minutes
        self._min_interval = min_practice_interval_minutes
        self._poll_interval = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        _init_curriculum_db()

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="auto-learner"
        )
        self._thread.start()
        logger.info("Auto-learner started (poll every %ss, idle threshold %sm)",
                     self._poll_interval, self._idle_threshold)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def learn_cycle(self) -> dict:
        """Run one learning cycle (called internally or manually)."""
        idle_mins = _get_idle_minutes()
        if idle_mins < self._idle_threshold:
            return {
                "success": False,
                "reason": f"User active ({idle_mins:.1f}m idle < {self._idle_threshold}m)",
            }

        if not self._is_due():
            return {"success": False, "reason": "Too soon since last practice"}

        gaps = self._discover_gaps()
        if not gaps:
            self._record_practice_timestamp()
            return {
                "success": True,
                "practiced": 0,
                "message": "No knowledge gaps found",
            }

        results = []
        for gap in gaps[:3]:
            result = self._practice(gap)
            results.append(result)

        practiced = sum(1 for r in results if r.get("practiced"))
        self._record_practice_timestamp()
        logger.info("Auto-learner: practiced %d tool(s) this cycle", practiced)
        return {"success": True, "practiced": practiced, "results": results}

    def curriculum_status(self) -> list[dict]:
        """Return current curriculum for display."""
        conn = get_connection(MEMORY_DB, timeout=5.0)
        conn.row_factory = None
        rows = conn.execute(
            "SELECT topic, attempts, successes, failures, success_rate, status, notes "
            "FROM learner_curriculum ORDER BY status, success_rate"
        ).fetchall()
        return [
            {
                "topic": r[0], "attempts": r[1], "successes": r[2],
                "failures": r[3], "success_rate": r[4],
                "status": r[5], "notes": (r[6] or "")[:100],
            }
            for r in rows
        ]

    # ── Internal ────────────────────────────────────────────────────────────

    def _poll_loop(self):
        logger.info("Auto-learner: poll loop started")
        while not self._stop_event.is_set():
            try:
                self.learn_cycle()
            except Exception as exc:
                logger.error("Auto-learner: cycle error: %s", exc)
            self._stop_event.wait(self._poll_interval)

    def _is_due(self) -> bool:
        conn = get_connection(MEMORY_DB, timeout=5.0)
        row = conn.execute(
            "SELECT MAX(last_practiced) FROM learner_curriculum"
        ).fetchone()
        if not row or row[0] is None:
            return True
        elapsed = time.time() - float(row[0])
        return elapsed >= self._min_interval * 60

    def _discover_gaps(self) -> list[dict]:
        """Find tools that need practice — never practiced first, then low success."""
        conn = get_connection(MEMORY_DB, timeout=5.0)
        conn.row_factory = None
        practiced_rows = conn.execute(
            "SELECT topic, successes, failures, attempts, status "
            "FROM learner_curriculum WHERE topic_type = 'tool'"
        ).fetchall()
        practiced = {r[0]: {"s": r[1], "f": r[2], "n": r[3], "status": r[4]} for r in practiced_rows}

        gaps = []
        for tool in sorted(self._tool_registry):
            if tool in _DANGEROUS_TOOLS:
                continue
            info = practiced.get(tool)
            if not info:
                gaps.append({"topic": tool, "type": "tool", "reason": "never_practiced"})
            elif info["status"] == "mastered":
                continue
            elif info["n"] < 3:
                gaps.append({"topic": tool, "type": "tool", "reason": "low_attempts", "attempts": info["n"]})
            elif info["s"] / max(info["n"], 1) < 0.5:
                gaps.append({"topic": tool, "type": "tool", "reason": "low_success",
                             "rate": info["s"] / max(info["n"], 1)})

        gaps.sort(key=lambda g: (
            0 if g.get("reason") == "never_practiced" else 1,
            g.get("rate", 1.0),
        ))
        return gaps

    def _practice(self, gap: dict) -> dict:
        tool = gap["topic"]
        safe_params = self._safe_params(tool)

        if safe_params is None:
            self._record_result(tool, False, notes="no safe params")
            return {"tool": tool, "practiced": False, "reason": "no_safe_params"}

        logger.info("Auto-learner: practicing '%s' with %s", tool, safe_params)
        try:
            result = self._tool_fn(tool, safe_params)
            success = result.get("success", False)
            notes = str(result.get("data", result.get("message", result.get("error", ""))))[:200]
            self._record_result(tool, success, notes=notes)
            return {"tool": tool, "practiced": True, "success": success, "notes": notes}
        except Exception as exc:
            self._record_result(tool, False, notes=str(exc)[:200])
            return {"tool": tool, "practiced": True, "success": False, "error": str(exc)}

    def _safe_params(self, tool: str) -> dict | None:
        """Build safe default params for a tool. Returns None if unsafe."""
        import tools as tools_module
        for schema in tools_module.TOOL_SCHEMAS:
            if schema["function"]["name"] != tool:
                continue
            props = schema["function"].get("parameters", {}).get("properties", {})
            required = schema["function"].get("parameters", {}).get("required", [])
            if not required:
                return {}
            params = {}
            for req in required:
                if req in _SAFE_DEFAULTS:
                    params[req] = _SAFE_DEFAULTS[req]
                else:
                    logger.debug("Auto-learner: skipping '%s' — unknown required param '%s'", tool, req)
                    return None
            return params
        return {}

    def _record_result(self, topic: str, success: bool, notes: str = ""):
        conn = get_connection(MEMORY_DB, timeout=5.0)
        now = time.time()
        existing = conn.execute(
            "SELECT id, attempts, successes, failures, status "
            "FROM learner_curriculum WHERE topic = ? AND topic_type = 'tool'",
            (topic,),
        ).fetchone()
        if existing:
            cid, attempts, successes, failures, status = existing
            attempts += 1
            if success:
                successes += 1
            else:
                failures += 1
            rate = successes / max(attempts, 1)
            new_status = "mastered" if (rate >= 0.8 and attempts >= 5) else "in_progress"
            conn.execute(
                "UPDATE learner_curriculum SET attempts=?, successes=?, failures=?, "
                "success_rate=?, last_practiced=?, status=?, notes=? WHERE id=?",
                (attempts, successes, failures, rate, now, new_status, notes, cid),
            )
        else:
            rate = 1.0 if success else 0.0
            conn.execute(
                "INSERT INTO learner_curriculum (topic, topic_type, attempts, successes, "
                "failures, success_rate, last_practiced, status, notes) "
                "VALUES (?, 'tool', 1, ?, ?, ?, ?, ?, ?)",
                (topic, 1 if success else 0, 0 if success else 1, rate, now,
                 "in_progress", notes),
            )
        conn.commit()

    def _record_practice_timestamp(self):
        """Bump the 'last_practiced' sentinel even if nothing was practiced."""
        conn = get_connection(MEMORY_DB, timeout=5.0)
        conn.execute(
            "INSERT INTO learner_curriculum (topic, topic_type, attempts, successes, "
            "failures, success_rate, last_practiced, status, notes) "
            "VALUES ('_sentinel', 'meta', 0, 0, 0, 0.0, ?, 'completed', 'cycle') "
            "ON CONFLICT(topic, topic_type) DO UPDATE SET last_practiced=?",
            (time.time(), time.time()),
        )
        conn.commit()
