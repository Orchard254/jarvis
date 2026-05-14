"""
Main routing gate. Bridges brain, safety, tools, and verification.
Injects callbacks into tool_loop to maintain strict layer boundaries.
"""

import logging
import re
import sys
from collections import deque

import autonomous.activity_log
import autonomous.task_queue
import settings
from autonomous.approval_gate import ApprovalGate
from autonomous.scheduler import Scheduler
from brain.tool_loop import run as tool_loop_run
from safety import executor as safety
from settings import ITERATION_CAPS, TOOL_LOOP_HISTORY_MESSAGES
from skills.skill_store import get_active_skills, search_by_intent
from skills.skill_store import init_db as init_skills
from tools import TOOL_REGISTRY
from indexer.state_monitor import read_pc_state
from verification.verifier import verify_action

from core.console import cli_input
from core.reporter import report

logger = logging.getLogger(__name__)


class Orchestrator:
    MAX_HISTORY = 40

    def __init__(self, memory=None):
        self._history = deque(maxlen=self.MAX_HISTORY)
        self._mode = "interactive_cloud"
        self._approval_gate = ApprovalGate()
        autonomous.task_queue.init_db()
        self._scheduler = Scheduler(self.handle)
        self._scheduler.start()
        self._memory = memory
        self.running = True
        self._last_tool_calls: list[dict] = []
        init_skills()

        try:
            from core.heartbeat_monitor import monitor
            monitor.start()
        except Exception:
            logger.warning("Heartbeat monitor unavailable")

        if getattr(settings, "AMBIENT_MONITORING", True):
            try:
                from autonomous import ambient_monitor
                ambient_monitor.start()
                import atexit
                atexit.register(ambient_monitor.stop)
            except Exception:
                logger.warning("Ambient monitor unavailable")

        if memory:
            try:
                recent = memory.get_recent_episodes(limit=20)
                for ep in reversed(recent):
                    cmd = ep.get("command_text", "")
                    tr = ep.get("tool_result") or {}
                    resp = tr.get("response", "") if isinstance(tr, dict) else ""
                    if cmd and resp:
                        self._history.append({"role": "user", "content": cmd})
                        self._history.append({"role": "assistant", "content": resp})
            except Exception:
                pass

    # ── Special commands (fast path, no LLM call) ─────────────────────────

    def _handle_special(self, text: str) -> str | None:
        if text == "skills status":
            active = get_active_skills()
            if not active:
                return "No active skills yet."
            return "Active skills:\n" + "\n".join(
                f"  {s['intent_label']} (success: {s['success_rate']:.0%})"
                for s in active
            )
        if text == "summary":
            from autonomous.activity_log import generate_summary
            return generate_summary()
        if text == "status":
            import shutil, psutil
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
        if text.startswith("task status"):
            from core.task_registry import registry
            parts = text.split()
            if len(parts) > 2:
                task = registry.get_task(parts[2])
                if task:
                    return f"Task {parts[2]}: {task.status.value} ({task.progress}%)"
                return f"Task {parts[2]} not found"
            active = registry.get_active_tasks()
            if not active:
                return "No active tasks"
            return "\n".join(f"{t.id}: {t.name} - {t.status.value} ({t.progress}%)" for t in active)
        return None

    # ── Main entry point ──────────────────────────────────────────────────

    def handle(self, user_input: str) -> str:
        logger.info(f"Orchestrator.handle: '{user_input}'")
        try:
            text = re.sub(r"^\d+\.\s*", "", user_input).strip()

            special = self._handle_special(text)
            if special is not None:
                self._update_history(user_input, special)
                return special

            if self._memory:
                self._memory.write_episodic("command", command_text=user_input)

            memory_context = self._memory.get_context_summary() if self._memory else ""
            if settings.ENABLE_SKILLS:
                match = search_by_intent(text)
                if match and match.get("skill_id"):
                    skill_hint = (
                        f"Saved skill found for intent '{text}':\n"
                        f"  code: {match.get('code', '')[:500]}\n"
                        f"  language: {match.get('language', 'python')}\n"
                        f"Execute this code via execute_code — do NOT assume it already ran."
                    )
                    memory_context = f"{skill_hint}\n\n{memory_context}" if memory_context else skill_hint

            result = tool_loop_run(
                user_input=text,
                history=list(self._history),
                execute_fn=self._execute_wrapper,
                verify_fn=self._verify_wrapper,
                mode=self._mode,
                tools=[],
                memory_context=memory_context,
                valid_tool_names=set(TOOL_REGISTRY.keys()),
                pc_state_fn=read_pc_state,
            )

            response = result.get("response", "Done.")
            self._last_tool_calls = result.get("tool_calls", [])

            if result.get("success") and result.get("tool_calls"):
                try:
                    formatted = report(
                        intent={"goal": text, "raw_input": user_input},
                        results=result["tool_calls"],
                        verification={
                            "status": "CONFIRMED" if result["success"] else "FAILED",
                            "summary": response,
                        },
                    )
                    if formatted and len(formatted) > 5:
                        response = formatted
                except Exception:
                    pass

            if self._memory:
                self._memory.write_episodic(
                    "response",
                    command_text=user_input,
                    tool_name="tool_loop",
                    success=result.get("success"),
                    tool_result={"response": response[:500]},
                )

            self._update_history(user_input, response)
            return response

        except Exception as e:
            logger.error(f"Orchestrator pipeline error: {e}", exc_info=True)
            return f"I encountered an error: {e}"

    def _update_history(self, user_input: str, response: str):
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": response})

    # ── Callbacks injected into tool_loop ─────────────────────────────────

    def _execute_wrapper(self, tool_name: str, args: dict) -> dict:
        if tool_name not in TOOL_REGISTRY:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        return safety.execute(
            tool_name,
            TOOL_REGISTRY[tool_name],
            args,
            plan={"confidence": 0.80},
        )

    def _verify_wrapper(self, tool_name: str, result: dict, expected: str) -> dict:
        return verify_action(tool_name, result, expected=expected)

    # ── Mode switching ────────────────────────────────────────────────────

    def set_mode(self, mode: str):
        if mode in ITERATION_CAPS:
            self._mode = mode

    # ── CLI loop ──────────────────────────────────────────────────────────

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
