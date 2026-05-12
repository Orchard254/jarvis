"""
Main routing gate. Bridges brain, safety, tools, and verification.
Injects callbacks into tool_loop to maintain strict layer boundaries.
"""

import logging
import re
import sys

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
from tools.read_pc_state import read_pc_state
from verification.verifier import verify_action

from core.console import cli_input
from core.reporter import report

_TOOL_CONFIDENCE: dict[str, float] = {
    "read_pc_state": 0.95,
    "capture_screen": 0.95,
    "execute_code": 0.80,
    "browser": 0.75,
    "find_on_screen": 0.90,
    "vision_query": 0.90,
    "time_calendar": 0.85,
    "control_window": 0.85,
    "query_pc_index": 0.90,
    "memory": 0.85,
    "speak": 0.80,
    "schedule": 0.80,
    "ask_user": 0.90,
    "listen": 0.85,
    "watch_screen": 0.75,
    "send_message": 0.80,
}

logger = logging.getLogger(__name__)


class CappedList(list):
    def __init__(self, max_len: int = 40):
        super().__init__()
        self._max_len = max_len

    def append(self, item):
        super().append(item)
        if len(self) > self._max_len:
            del self[0]

    def extend(self, items):
        super().extend(items)
        if len(self) > self._max_len:
            del self[: len(self) - self._max_len]

    def insert(self, index, item):
        super().insert(index, item)
        if len(self) > self._max_len:
            del self[0]


class Orchestrator:
    def __init__(self, memory=None):
        self._history: list[dict] = CappedList(max_len=40)
        self._mode = "interactive_cloud"
        self._approval_gate = ApprovalGate()
        autonomous.task_queue.init_db()
        self._scheduler = Scheduler(self.handle)
        self._scheduler.start()
        self._memory = memory
        self.running = True
        self._last_tool_calls: list[dict] = []
        self._handle_lock = __import__("threading").Lock()
        init_skills()

        try:
            from core.heartbeat_monitor import monitor
            monitor.start()
            logger.info("Heartbeat monitor started")
        except Exception as _hb_exc:
            logger.warning(f"Heartbeat monitor failed to start: {_hb_exc}")

        if getattr(settings, "AMBIENT_MONITORING", True):
            try:
                from autonomous import ambient_monitor
                ambient_monitor.start()
                import atexit
                atexit.register(ambient_monitor.stop)
                logger.info("Ambient monitor started")
            except Exception as _am_exc:
                logger.warning(f"Ambient monitor unavailable: {_am_exc}")

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
                logger.info(
                    f"Loaded {len(self._history) // 2} conversation turns from memory"
                )
            except Exception as _e:
                logger.debug(f"Could not load history from memory: {_e}")

        logger.info("Orchestrator initialized with full pipeline wiring and Skill Store")

    def handle(self, user_input: str) -> str:
        logger.info(f"Orchestrator.handle: '{user_input}'")
        try:
            clean_input = re.sub(r"^\d+\.\s*", "", user_input).strip()

            if self._memory:
                self._memory.write_episodic("command", command_text=user_input)

            if clean_input.lower() == "skills status":
                active_skills = get_active_skills()
                if not active_skills:
                    return "No active skills yet."
                skill_strings = [
                    f"{s['skill_id']} ({s['intent_label']})" for s in active_skills
                ]
                return f"Active skills: {', '.join(skill_strings)}"

            if clean_input.lower().startswith("task status"):
                from core.task_registry import registry
                parts = clean_input.split()
                if len(parts) > 2:
                    task_id = parts[2]
                    task = registry.get_task(task_id)
                    if task:
                        return f"Task {task_id}: {task.status.value} ({task.progress}%)"
                    return f"Task {task_id} not found"
                else:
                    active = registry.get_active_tasks()
                    if not active:
                        return "No active tasks"
                    return "\n".join([f"{t.id}: {t.name} - {t.status.value} ({t.progress}%)" for t in active])

            # Pre-search skill store before entering tool loop (Bug 5 fix)
            skill_match = search_by_intent(clean_input) if settings.ENABLE_SKILLS else None
            skill_context = ""
            if skill_match and skill_match.get("skill_id"):
                skill_context = (
                    f"Saved skill found for intent '{clean_input}':\n"
                    f"  code: {skill_match.get('code', '')[:500]}\n"
                    f"  language: {skill_match.get('language', 'python')}\n"
                    f"Execute this code via execute_code — do NOT assume it already ran."
                )

            memory_context = ""
            if self._memory:
                memory_context = self._memory.get_context_summary()

            with self._handle_lock:
                history_snapshot = list(self._history)

            result = tool_loop_run(
                user_input=clean_input,
                history=history_snapshot,
                execute_fn=self._execute_wrapper,
                verify_fn=self._verify_wrapper,
                mode=self._mode,
                tools=[],
                memory_context=memory_context,
                valid_tool_names=set(TOOL_REGISTRY.keys()),
                pc_state_fn=read_pc_state,
            )

            response = result.get("response", "Done.")
            with self._handle_lock:
                self._last_tool_calls = result.get("tool_calls", [])

            if result.get("success") and result.get("tool_calls"):
                try:
                    formatted = report(
                        intent={"goal": clean_input, "raw_input": user_input},
                        results=result.get("tool_calls", []),
                        verification={
                            "status": "CONFIRMED" if result.get("success") else "FAILED",
                            "summary": response,
                        },
                    )
                    if formatted and len(formatted) > 5:
                        response = formatted
                except Exception as _rep_exc:
                    logger.debug(f"Reporter skipped: {_rep_exc}")

            if self._memory:
                self._memory.write_episodic(
                    "response",
                    command_text=user_input,
                    tool_name="tool_loop",
                    success=result.get("success"),
                    tool_result={"response": response[:500]},
                )

            with self._handle_lock:
                self._history.append({"role": "user", "content": user_input})
                self._history.append({"role": "assistant", "content": response})

            return response

        except Exception as e:
            logger.error(f"Orchestrator pipeline error: {e}", exc_info=True)
            return f"I encountered an error: {e}"

    def _execute_wrapper(self, tool_name: str, args: dict) -> dict:
        if tool_name not in TOOL_REGISTRY:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        tool_fn = TOOL_REGISTRY[tool_name]
        confidence = _TOOL_CONFIDENCE.get(tool_name, 0.80)
        threshold_override = getattr(self, "_autonomous_threshold", None)
        if threshold_override is not None:
            confidence = threshold_override
        return safety.execute(tool_name, tool_fn, args, plan={"confidence": confidence})

    def _verify_wrapper(self, tool_name: str, result: dict, expected: str) -> dict:
        return verify_action(tool_name, result, expected=expected)

    def set_mode(self, mode: str):
        if mode in ITERATION_CAPS:
            self._mode = mode
            logger.info(f"Execution mode set to: {mode}")
        else:
            logger.warning(f"Unknown mode: {mode}. Defaulting to {self._mode}")

    def handle_autonomous(self, task_id: str, command: str, confidence: float) -> str:
        self._autonomous_threshold = settings.AUTONOMOUS_CONFIDENCE_THRESHOLD
        try:
            return self.handle(command)
        finally:
            self._autonomous_threshold = None

    def run_cli(self, output_callback=None):
        print("JARVIS ready. Type a command (or 'quit' to exit).")
        print("Autonomous: 'schedule <cmd> every N hours', 'status', 'summary'")
        print("Skills: 'skills status' to list active skills")
        while self.running:
            try:
                user_input = cli_input().strip()
                if user_input.lower() in ("quit", "exit", "q"):
                    break
                if not user_input:
                    continue

                if (user_input.lower().startswith("skill") and "status" in user_input.lower()):
                    skills = get_active_skills(limit=10)
                    if skills:
                        print(
                            "\n"
                            + "\n".join([
                                f"{s['intent_label']} (success: {s['success_rate']:.0%})"
                                for s in skills
                            ])
                        )
                    else:
                        print("\nNo active skills yet. Use JARVIS normally to teach it new tasks.")
                    continue
                elif user_input.lower() == "summary":
                    from autonomous.activity_log import generate_summary
                    print(f"\n{generate_summary()}")
                    continue
                elif user_input.lower() == "status":
                    import shutil
                    import psutil
                    ram = psutil.virtual_memory()
                    disk_path = "C:\\" if sys.platform == "win32" else "/"
                    try:
                        disk = shutil.disk_usage(disk_path)
                    except Exception:
                        disk = shutil.disk_usage(".")
                    print(
                        f"\nRAM: {ram.percent}% used | Disk C: {disk.used // 1e9:.1f}GB / {disk.total // 1e9:.1f}GB"
                    )
                    continue
                elif user_input.startswith("schedule "):
                    match = re.match(
                        r"schedule\s+\"?([^\"]+?)\"?\s+(every|in|at)\s+(.*)",
                        user_input,
                        re.IGNORECASE,
                    )
                    if match:
                        cmd, cron_word, cron_val = match.groups()
                        tid = self._scheduler.schedule(
                            cmd.strip(), f"{cron_word} {cron_val}".strip()
                        )
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
