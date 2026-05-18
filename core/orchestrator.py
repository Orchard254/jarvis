"""
Main routing gate. Director → (if needed) Execution → Director summary.
"""

import logging
import re
import sys
from collections import deque

import autonomous.task_queue
import settings
from autonomous.approval_gate import ApprovalGate
from autonomous.scheduler import Scheduler
from agents.director import JarvisAgent
from agents.execution import ExecutionAgent
from safety import executor as safety
from skills.skill_store import get_active_skills
from tools import TOOL_REGISTRY
from verification.verifier import verify_action

from core.console import cli_input
from core.system_state import SystemState

logger = logging.getLogger(__name__)


class Orchestrator:
    MAX_HISTORY = 40

    def __init__(self, memory=None):
        self._history = deque(maxlen=self.MAX_HISTORY)
        self._state = SystemState()
        self._approval_gate = ApprovalGate()
        self._memory = memory
        self._scheduler = Scheduler(self.handle)
        self.running = True
        self._tool_failure_streak: dict[str, int] = {}
        self._jarvis = JarvisAgent()
        self._execution = ExecutionAgent(self._execute_wrapper, self._verify_wrapper)
        self._lazy_init_done = False

    def _lazy_init(self):
        if self._lazy_init_done:
            return
        self._lazy_init_done = True
        autonomous.task_queue.init_db()
        self._scheduler.start()
        from indexer import pc_indexer as _indexer
        _indexer.start()

    # ── Fast-path admin commands (no LLM call) ────────────────────────────

    def _handle_admin(self, text: str) -> str | None:
        t = text.strip().lower()
        if t == "skills status":
            active = get_active_skills()
            if not active:
                return "No active skills yet."
            return "Active skills:\n" + "\n".join(
                f"  {s['intent_label']} (success: {s['success_rate']:.0%})"
                for s in active
            )
        if t == "summary":
            from autonomous.activity_log import generate_summary
            return generate_summary()
        if t == "status":
            import shutil
            import psutil
            ram = psutil.virtual_memory()
            disk_path = "C:\\" if sys.platform == "win32" else "/"
            try:
                disk = shutil.disk_usage(disk_path)
            except Exception:
                disk = shutil.disk_usage(".")
            return (
                f"RAM: {ram.percent}% used | "
                f"Disk {disk_path}: {disk.used // 1e9:.1f}GB / {disk.total // 1e9:.1f}GB"
            )
        if t.startswith("task status"):
            parts = text.split()
            if len(parts) > 2:
                from autonomous.task_queue import get_task as _get_tq_task
                task = _get_tq_task(parts[2])
                if task:
                    return f"Task {parts[2]}: {task.get('status', '?')} (created: {task.get('created_at', '?')})"
                return f"Task {parts[2]} not found"
            from autonomous.task_queue import get_active_tasks as _get_active
            active = _get_active()
            if not active:
                return "No active tasks"
            return "\n".join(f"{t['task_id'][:8]}: {t.get('command', '?')[:40]} - {t['status']}" for t in active)
        return None

    # ── Main entry point ─────────────────────────────────────────────────

    def handle(self, user_input: str) -> str:
        self._lazy_init()
        logger.info(f"Orchestrator.handle: '{user_input}'")
        self._tool_failure_streak.clear()
        try:
            text = re.sub(r"^\d+\.\s*", "", user_input).strip()

            admin = self._handle_admin(text)
            if admin is not None:
                self._update_history(user_input, admin)
                return admin

            # Step 1: Director thinks
            director_result = self._jarvis.process(
                user_input=text,
                history=list(self._history),
            )

            task = director_result.get("delegate_task")
            if not task:
                response = director_result.get("response", "Done.")
                if self._memory:
                    self._memory.write_episodic("response", command_text=user_input, tool_name="chat", success=True, tool_result={"response": response[:500]})
                self._update_history(user_input, response)
                return response

            # Step 2: Execution acts
            exec_results = self._execution.execute_task(task)

            # Step 3: Director summarizes
            response = self._jarvis.summarize(task, exec_results, list(self._history))

            if self._memory:
                self._memory.write_episodic("response", command_text=user_input, tool_name="delegated", success=True, tool_result={"response": response[:500]})

            self._update_history(user_input, response)
            return response

        except Exception as e:
            logger.error(f"Orchestrator pipeline error: {e}", exc_info=True)
            return f"I encountered an error: {e}"

    def _update_history(self, user_input: str, response: str):
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": response})

    # ── Tool execution wrapper ───────────────────────────────────────────

    def _execute_wrapper(self, tool_name: str, args: dict) -> dict:
        if tool_name not in TOOL_REGISTRY:
            return {"success": False, "message": f"Unknown tool: {tool_name}", "data": {}, "timestamp": ""}

        if tool_name == "wait" and args.get("condition"):
            condition = args["condition"]
            target = str(args.get("target", "")).lower()
            state = self._state.snapshot()
            if condition == "window_visible" and target:
                if target in state.get("active_window", "").lower():
                    return {"success": True, "message": f"Wait skipped: '{target}' already active", "data": {}, "timestamp": ""}
            elif condition == "text_visible" and target:
                if target in state.get("screen_text", "").lower():
                    return {"success": True, "message": f"Wait skipped: text '{target}' already on screen", "data": {}, "timestamp": ""}
            elif condition == "cpu_idle" and target:
                try:
                    if float(state.get("cpu_percent", 100)) < float(target):
                        return {"success": True, "message": f"Wait skipped: CPU already idle ({state.get('cpu_percent')}% < {target}%)", "data": {}, "timestamp": ""}
                except (ValueError, TypeError):
                    pass

        probe_tools = {"focus_window", "wait", "get_active_window"}
        if tool_name in probe_tools:
            confidence = 0.85
            streak = 0
        else:
            streak = self._tool_failure_streak.get(tool_name, 0)
            confidence = 0.85 if streak == 0 else (0.75 if streak == 1 else 0.40)

        result = safety.execute(
            tool_name,
            TOOL_REGISTRY[tool_name],
            args,
            plan={
                "confidence": confidence,
                "llm_response": "",
                "tool_name": tool_name,
                "approved": True,
            },
        )
        if result.get("success"):
            self._tool_failure_streak[tool_name] = 0
        else:
            self._tool_failure_streak[tool_name] = streak + 1
        self._state.update(tool_name, args, result)
        return result

    def _verify_wrapper(self, tool_name: str, result: dict, expected: str) -> dict:
        return verify_action(tool_name, result, expected=expected)

    # ── CLI loop ─────────────────────────────────────────────────────────

    def run_cli(self, output_callback=None):
        print("JARVIS ready. Type a command (or 'quit' to exit).")
        while self.running:
            try:
                user_input = cli_input().strip()
                if user_input.lower() in ("quit", "exit", "q"):
                    break
                if not user_input:
                    continue

                schedule_match = re.match(
                    r"schedule\s+\"?([^\"]+?)\"?\s+(every|in|at)\s+(.*)",
                    user_input,
                    re.IGNORECASE,
                )
                if schedule_match:
                    cmd, _, cron_val = schedule_match.groups()
                    tid = self._scheduler.schedule(cmd.strip(), cron_val.strip())
                    print(f"\nScheduled: '{cmd}' ({tid[:8]})")
                    continue

                response = self.handle(user_input)
                if output_callback:
                    output_callback(response)
                else:
                    print(f"\nJARVIS: {response}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"CLI loop error: {e}")
                print(f"System error: {e}")
        print("JARVIS stopped.")
