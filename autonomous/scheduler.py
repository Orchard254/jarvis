"""
Cron-style scheduler for autonomous tasks.
Triggers tasks at scheduled times, injects into orchestrator pipeline.
High-risk commands are gated through ApprovalGate before execution.

Recurring schedules are persisted to the ``recurring_schedules`` table in
MEMORY_DB so they survive JARVIS restarts.  On startup, __init__ calls
_load_recurring_from_db() to restore any active schedules back into memory.
"""

import logging
import re
import sqlite3
import threading
import time
from datetime import datetime

import settings
from settings import MEMORY_DB

from autonomous.approval_gate import ApprovalGate
from autonomous.task_queue import create_task, get_pending_tasks, update_task

logger = logging.getLogger(__name__)

# Default approval timeout (seconds) — kept short so the scheduler loop
# doesn't stall for too long waiting on a single task.
_APPROVAL_TIMEOUT = int(getattr(settings, "APPROVAL_TIMEOUT_SECONDS", 60))


# ------------------------------------------------------------------ #
#  DB initialisation (module-level, no class needed)                  #
# ------------------------------------------------------------------ #


def _init_recurring_db() -> None:
    """
    Create the ``recurring_schedules`` table if it doesn't already exist.
    Uses the same MEMORY_DB path as the rest of the autonomous layer.
    """
    MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recurring_schedules (
                task_id         TEXT PRIMARY KEY,
                command         TEXT,
                cron_expression TEXT,
                next_run        REAL,
                created_at      REAL,
                active          INTEGER DEFAULT 1
            )
        """)
        conn.commit()
    finally:
        conn.close()


class Scheduler:
    def __init__(self, orchestrator_callback):
        """
        Args:
            orchestrator_callback: function(user_input: str) -> str to execute tasks
        """
        self._orchestrator = orchestrator_callback
        self._stop_event = threading.Event()
        self._thread = None
        self._scheduled: dict[str, dict] = {}
        self._gate = ApprovalGate(timeout_seconds=_APPROVAL_TIMEOUT)
        # Ensure the recurring table exists, then restore any persisted schedules.
        _init_recurring_db()
        self._load_recurring_from_db()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def schedule(
        self, command: str, cron_expression: str, task_id: str | None = None
    ) -> str:
        """
        Schedule a task using cron-like syntax.
        Supported: "every N minutes/hours/days", "at HH:MM",
                   "on Monday at HH:MM", "in N minutes/hours"

        Recurring schedules are persisted to DB so they survive restarts.

        Args:
            command:         The task to execute.
            cron_expression: Human-readable schedule string.
            task_id:         Optional explicit ID (generated if None).

        Returns:
            task_id string
        """
        from uuid import uuid4

        task_id = task_id or str(uuid4())
        scheduled_for = self._parse_cron(cron_expression)

        if scheduled_for is None:
            raise ValueError(f"Unrecognized schedule: '{cron_expression}'")

        self._scheduled[task_id] = {
            "command": command,
            "cron": cron_expression,
            "next_run": scheduled_for,
        }
        create_task(command, scheduled_for=scheduled_for)

        # Persist recurring schedules so they survive a restart.
        if self._is_recurring(cron_expression):
            self._persist_recurring(task_id, command, cron_expression, scheduled_for)

        label = repr(command) if len(command) <= 40 else repr(command[:40]) + "..."
        logger.info(
            f"scheduler: scheduled task '{task_id[:8]}' — "
            f"{label} @ {datetime.fromtimestamp(scheduled_for)}"
        )
        return task_id

    def cancel(self, task_id: str) -> dict:
        """
        Cancel a recurring schedule: remove it from the in-memory dict and
        mark it ``active = 0`` in the DB so it is not reloaded on restart.

        Returns:
            dict with ``success`` (bool), ``task_id``, and optional ``reason``.
        """
        removed_from_memory = task_id in self._scheduled
        if removed_from_memory:
            del self._scheduled[task_id]

        db_updated = False
        try:
            conn = sqlite3.connect(MEMORY_DB)
            try:
                c = conn.cursor()
                c.execute(
                    "UPDATE recurring_schedules SET active = 0 WHERE task_id = ?",
                    (task_id,),
                )
                db_updated = c.rowcount > 0
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                f"scheduler: could not deactivate '{task_id[:8]}' in DB: {exc}"
            )

        if removed_from_memory or db_updated:
            logger.info(f"scheduler: cancelled recurring task '{task_id[:8]}'")
            return {"success": True, "task_id": task_id}

        logger.warning(f"scheduler: cancel: task '{task_id[:8]}' not found")
        return {"success": False, "reason": "task_not_found", "task_id": task_id}

    def start(self):
        """Start the background scheduler thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="scheduler"
        )
        self._thread.start()

    def stop(self):
        """Stop the scheduler thread gracefully."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------ #
    #  Internal: monitor loop                                              #
    # ------------------------------------------------------------------ #

    def _monitor_loop(self):
        """Background thread: checks for due tasks and executes them."""
        logger.info("scheduler: monitor loop started")

        while not self._stop_event.is_set():
            # --- DB-based one-shot tasks (existing behaviour) ---
            try:
                pending = get_pending_tasks()
                for task in pending:
                    self._handle_task(task)
            except Exception as e:
                logger.error(f"scheduler: monitor error: {e}")

            # --- In-memory recurring tasks ---
            now = time.time()
            for task_id, entry in list(self._scheduled.items()):
                if entry["next_run"] > now:
                    continue
                command = entry["command"]
                cron = entry["cron"]
                logger.info(
                    f"scheduler: recurring '{task_id[:8]}' due — '{command[:40]}'"
                )
                try:
                    self._orchestrator(command)
                    logger.info(f"scheduler: recurring '{task_id[:8]}' completed")
                except Exception as exc:
                    logger.error(f"scheduler: recurring '{task_id[:8]}' failed: {exc}")

                if self._is_recurring(cron):
                    next_run = self._parse_cron(cron)
                    if next_run:
                        self._scheduled[task_id]["next_run"] = next_run
                        # Keep the DB in sync so the next_run survives a restart.
                        self._update_next_run_db(task_id, next_run)
                        logger.info(
                            f"scheduler: next run for '{task_id[:8]}' "
                            f"at {datetime.fromtimestamp(next_run)}"
                        )
                else:
                    # One-shot — remove after firing
                    del self._scheduled[task_id]

            self._stop_event.wait(30)

        logger.info("scheduler: monitor loop stopped")

    def _handle_task(self, task: dict) -> None:
        """
        Evaluate one pending task: gate high-risk commands through
        ApprovalGate, then execute via the orchestrator callback.
        """
        task_id = task["task_id"]
        command = task["command"]
        confidence = float(task.get("confidence_required", 0.85))

        # ── Check whether this command requires approval ───────────────
        if self._requires_approval(command):
            logger.info(
                f"scheduler: task '{task_id[:8]}' requires approval "
                f"(command contains high-risk keyword)"
            )
            approved = self._gate.request(task_id, command, confidence)

            if not approved:
                logger.warning(
                    f"scheduler: task '{task_id[:8]}' was NOT approved — skipping"
                )
                update_task(task_id, "failed", error="Denied by approval gate")
                return

            logger.info(f"scheduler: task '{task_id[:8]}' approved — proceeding")

        # ── Execute through orchestrator ───────────────────────────────
        logger.info(f"scheduler: executing task '{task_id[:8]}' — '{command[:40]}...'")
        update_task(task_id, "running")

        try:
            result = self._orchestrator(command)
            # Extract tool_calls from the orchestrator instance for action_log
            action_log = []
            try:
                orch = getattr(self._orchestrator, "__self__", None)
                if orch and hasattr(orch, "_last_tool_calls"):
                    action_log = [
                        {
                            "tool": e.get("tool"),
                            "args": e.get("args"),
                            "success": e.get("result", {}).get("success", False),
                        }
                        for e in orch._last_tool_calls
                    ]
            except Exception:
                pass
            update_task(
                task_id, "complete", result={"response": result}, action_log=action_log
            )
        except Exception as e:
            logger.error(f"scheduler: task '{task_id[:8]}' failed: {e}")
            update_task(task_id, "failed", error=str(e))

    # ------------------------------------------------------------------ #
    #  Internal: DB persistence for recurring schedules                   #
    # ------------------------------------------------------------------ #

    def _persist_recurring(
        self, task_id: str, command: str, cron_expression: str, next_run: float
    ) -> None:
        """Insert or replace a recurring schedule row in the DB."""
        try:
            conn = sqlite3.connect(MEMORY_DB)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO recurring_schedules
                        (task_id, command, cron_expression, next_run, created_at, active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (task_id, command, cron_expression, next_run, time.time()),
                )
                conn.commit()
            finally:
                conn.close()
            logger.debug(f"scheduler: persisted recurring schedule '{task_id[:8]}'")
        except Exception as exc:
            logger.warning(
                f"scheduler: could not persist recurring schedule "
                f"'{task_id[:8]}': {exc}"
            )

    def _update_next_run_db(self, task_id: str, next_run: float) -> None:
        """Update the next_run timestamp for a persisted recurring schedule."""
        try:
            conn = sqlite3.connect(MEMORY_DB)
            try:
                conn.execute(
                    "UPDATE recurring_schedules SET next_run = ? WHERE task_id = ?",
                    (next_run, task_id),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                f"scheduler: could not update next_run for '{task_id[:8]}': {exc}"
            )

    def _load_recurring_from_db(self) -> None:
        """
        Reload all active recurring schedules from DB into ``self._scheduled``.
        Called once in ``__init__`` so that schedules survive JARVIS restarts.

        If a schedule's stored ``next_run`` is in the past, it is recalculated
        from the cron expression so the task fires at the correct future time
        rather than immediately triggering on every restart.
        """
        try:
            conn = sqlite3.connect(MEMORY_DB)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT task_id, command, cron_expression, next_run
                    FROM   recurring_schedules
                    WHERE  active = 1
                    """
                ).fetchall()
            finally:
                conn.close()

            now = time.time()
            loaded = 0
            for row in rows:
                task_id = row["task_id"]
                cron = row["cron_expression"]
                next_run = row["next_run"]

                # Stale next_run (e.g. JARVIS was offline for a while) —
                # recalculate so the task fires at the next proper interval.
                if next_run <= now:
                    recalculated = self._parse_cron(cron)
                    if recalculated:
                        next_run = recalculated
                        self._update_next_run_db(task_id, next_run)

                self._scheduled[task_id] = {
                    "command": row["command"],
                    "cron": cron,
                    "next_run": next_run,
                }
                loaded += 1

            if loaded:
                logger.info(
                    f"scheduler: reloaded {loaded} recurring schedule(s) from DB"
                )
        except Exception as exc:
            logger.warning(
                f"scheduler: could not load recurring schedules from DB: {exc}"
            )

    # ------------------------------------------------------------------ #
    #  Internal: helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _requires_approval(command: str) -> bool:
        """
        Return True if the command contains any keyword that is listed in
        settings.AUTONOMOUS_REQUIRE_APPROVAL.

        Falls back to a hard-coded safety set if the setting is absent.
        """
        risk_keywords: set[str] = getattr(
            settings,
            "AUTONOMOUS_REQUIRE_APPROVAL",
            {
                "delete",
                "format",
                "shutdown",
                "restart",
                "uninstall",
                "send_email",
                "make_purchase",
                "control_input",
            },
        )
        command_lower = command.lower()
        return any(keyword in command_lower for keyword in risk_keywords)

    @staticmethod
    def _is_recurring(cron: str) -> bool:
        """
        Return True for patterns that repeat indefinitely:
          - "every N minutes"    → True
          - "every N hours"      → True
          - "every day at HH:MM" → True
          - "on Monday at HH:MM" → True  (weekly)
          - "in N minutes/hours" → False (one-shot delay)
          - "at HH:MM"           → False (one-shot)
        """
        expr = cron.lower().strip()
        return bool(
            re.match(r"every \d+ (minutes?|hours?)", expr)
            or re.match(r"every day at", expr)
            or re.match(r"on \w+ at", expr)
        )

    # ------------------------------------------------------------------ #
    #  Internal: cron parser                                               #
    # ------------------------------------------------------------------ #

    def _parse_cron(self, expr: str) -> float | None:
        """Parse human-readable cron expression to Unix timestamp."""
        now = time.time()
        expr = expr.lower().strip()

        # "every N minutes"
        match = re.match(r"every (\d+) minutes?", expr)
        if match:
            return now + int(match.group(1)) * 60

        # "every N hours"
        match = re.match(r"every (\d+) hours?", expr)
        if match:
            return now + int(match.group(1)) * 3600

        # "every day at HH:MM"
        match = re.match(r"every day at (\d{1,2}):(\d{2})", expr)
        if match:
            h, m = int(match.group(1)), int(match.group(2))
            target = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
            ts = target.timestamp()
            return ts if ts > now else ts + 86400  # Tomorrow if today passed

        # "on Monday at HH:MM"
        match = re.match(r"on (\w+) at (\d{1,2}):(\d{2})", expr)
        if match:
            day_name, h, m = (
                match.group(1),
                int(match.group(2)),
                int(match.group(3)),
            )
            days = [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]
            if day_name in days:
                target_day = days.index(day_name)
                today = datetime.now().weekday()
                days_ahead = (target_day - today) % 7
                # Compare both hours AND minutes to avoid scheduling in the past
                now_dt = datetime.now()
                if days_ahead == 0 and (
                    now_dt.hour > h or (now_dt.hour == h and now_dt.minute >= m)
                ):
                    days_ahead = 7  # Same weekday next week
                target = datetime.now().replace(
                    hour=h, minute=m, second=0, microsecond=0
                )
                from datetime import timedelta

                target = target + timedelta(days=days_ahead)
                return target.timestamp()

        # "in N minutes/hours"
        match = re.match(r"in (\d+) (minutes?|hours?)", expr)
        if match:
            n, unit = int(match.group(1)), match.group(2)
            return now + n * (60 if unit.startswith("minute") else 3600)

        return None
