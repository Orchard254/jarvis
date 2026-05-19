"""
Main routing gate. Bridges brain, safety, tools, and verification.
Injects callbacks into tool_loop to maintain strict layer boundaries.
"""

import concurrent.futures
import logging
import re
import sys
import threading
import asyncio
from collections import deque

import autonomous.activity_log
import autonomous.task_queue
import settings
from core.event_bus import event_bus
from autonomous.approval_gate import ApprovalGate
from autonomous.scheduler import Scheduler
from agents.jarvis import run as tool_loop_run
from agents.base_agent import SubAgentTask
from safety import executor as safety
from settings import ITERATION_CAPS
from skills.skill_store import get_active_skills, search_by_intent
from skills.skill_store import init_db as init_skills
from tools import TOOL_REGISTRY
from indexer.state_monitor import read_pc_state
from verification.verifier import verify_action

from core.classifier import classify, is_special_command
from core.console import cli_input
from core.reporter import report
from core.system_state import SystemState

logger = logging.getLogger(__name__)


class Orchestrator:
    MAX_HISTORY = 40

    def __init__(self, memory=None):
        self._history = deque(maxlen=self.MAX_HISTORY)
        self._state = SystemState()
        self._mode = "interactive_cloud"
        self._approval_gate = ApprovalGate()
        autonomous.task_queue.init_db()
        self._memory = memory
        self._history_hydrated = False
        self._scheduler = Scheduler(self.handle)
        self._scheduler.start()
        self.running = True

        self.event_bus = event_bus
        self._last_tool_calls: list[dict] = []
        init_skills()

        # Inject safety-gated execute/verify into all registered sub-agents
        from agents.sub_agent_registry import registry
        import agents.sub_agents  # noqa: F401 — triggers agent registration
        registry.inject_into_agents(self._execute_wrapper, self._verify_wrapper)

    async def async_init(self):
        # Start the event bus after the event loop is running
        self.event_bus.start()

        # Start the ProactiveAgent's monitoring loop
        from agents.sub_agent_registry import registry
        proactive_agent_instance = registry.get("proactive")
        if proactive_agent_instance:
            asyncio.create_task(proactive_agent_instance.run(SubAgentTask(goal="Start proactive monitoring", context={})))
        else:
            logger.warning("ProactiveAgent not found in registry, cannot start monitoring.")

        try:
            from core.heartbeat_monitor import monitor
            monitor.start()
        except Exception:
            logger.warning("Heartbeat monitor unavailable")

        if getattr(settings, "AMBIENT_MONITORING", True):
            try:
                from autonomous import ambient_monitor
                ambient_monitor.start(asyncio.get_running_loop())
                import atexit
                atexit.register(ambient_monitor.stop)
            except Exception:
                logger.warning("Ambient monitor unavailable")


        # Start Clipboard Monitor
        try:
            from autonomous import clipboard_monitor
            clipboard_monitor.start(asyncio.get_running_loop())
            atexit.register(clipboard_monitor.stop)
        except Exception:
            logger.warning("Clipboard monitor unavailable")

        # Start File System Monitor
        try:
            from autonomous import file_system_monitor
            import os
            jarvis_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            file_system_monitor.start(asyncio.get_running_loop(), path=jarvis_path) # Monitor the project directory
            atexit.register(file_system_monitor.stop)
        except Exception:
            logger.warning("File system monitor unavailable")

        self._history_hydrated = False

    def _conversation_history_for_jarvis(self) -> list[dict]:
        """In-session deque merged with persisted episodic turns when memory is enabled."""
        in_memory = [{"role": m["role"], "content": m["content"]} for m in self._history]
        if not self._memory:
            return in_memory
        if not self._history_hydrated and settings.LOAD_CONVERSATION_HISTORY:
            self._history_hydrated = True
        return self._memory.merge_session_history(in_memory)

    # ── Fast-path handlers (no LLM call) ─────────────────────────────────

    def _handle_special(self, text: str) -> str | None:
        cmd = is_special_command(text)
        if cmd is None:
            return None
        if cmd == "skills_status":
            active = get_active_skills()
            if not active:
                return "No active skills yet."
            return "Active skills:\n" + "\n".join(
                f"  {s['intent_label']} (success: {s['success_rate']:.0%})"
                for s in active
            )
        if cmd == "summary":
            from autonomous.activity_log import generate_summary
            return generate_summary()
        if cmd == "status":
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
        if cmd == "task_status":
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

    def _handle_simple_intent(self, text: str) -> str | None:
        intent = classify(text)
        if intent is None:
            return None
        logger.info(f"Classifier matched: {intent.label}")
        result = self._execute_wrapper(intent.tool_name, intent.args)
        if result.get("success"):
            return intent.format_result(result)
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

            simple = self._handle_simple_intent(text)
            if simple is not None:
                self._update_history(user_input, simple)
                return simple

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

            # Run tool loop with a timeout guard
            timeout = settings.LLM_TIMEOUT + 30
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
                future = _pool.submit(
                    tool_loop_run,
                    user_input=text,
                    history=self._conversation_history_for_jarvis(),
                    execute_fn=self._execute_wrapper,
                    verify_fn=self._verify_wrapper,
                    mode=self._mode,
                    memory_context=memory_context,
                    valid_tool_names=set(TOOL_REGISTRY.keys()),
                    pc_state_fn=read_pc_state,
                    state_snapshot_fn=self._state.snapshot,
                    attach_tool_schemas=settings.JARVIS_ATTACH_TOOL_SCHEMAS,
                )
                try:
                    result = future.result(timeout=timeout) or {}
                except concurrent.futures.TimeoutError:
                    logger.error(f"Tool loop timed out after {timeout}s")
                    result = {"response": "Tool loop timed out", "success": False, "error": "TIMEOUT", "tool_calls": []}

            if not result:
                result = {"response": "No response from tool loop", "success": False, "tool_calls": []}

            response = result.get("response", "Done.")
            self._last_tool_calls = result.get("tool_calls", [])

            # ── Verification: cross-check LLM summary against actual tool results ──
            tool_calls_list = result.get("tool_calls", [])
            if tool_calls_list and result.get("success"):
                failed_calls = [
                    tc for tc in tool_calls_list
                    if not tc.get("result", {}).get("success", False)
                ]
                # Only flag if the LAST call failed, or ALL calls for the same tool failed
                last_call = tool_calls_list[-1] if tool_calls_list else None
                if failed_calls:
                    last_failed = last_call and not last_call.get("result", {}).get("success", False)
                    all_same_tool = len({tc.get("tool") for tc in failed_calls}) == 1
                    all_calls_tool_failed = all_same_tool and all(
                        tc.get("tool") == failed_calls[0].get("tool")
                        for tc in tool_calls_list
                    ) and len(tool_calls_list) == len(failed_calls)
                    if last_failed or all_calls_tool_failed:
                        # Skip correction if Jarvis already acknowledged the failure in its response
                        response_lower = response.lower()
                        already_acknowledged = any(
                            tc.get("result", {}).get("error", "").lower() in response_lower
                            or tc.get("tool", "").lower() in response_lower
                            for tc in failed_calls[:3]
                        )
                        ack_phrases = ["isn't open", "not found", "couldn't", "failed to",
                                        "doesn't appear", "not running", "not available"]
                        already_acknowledged = already_acknowledged or any(
                            p in response_lower for p in ack_phrases
                        )
                        if not already_acknowledged:
                            logger.warning(
                                f"Verification: {len(failed_calls)} tool(s) failed, final result wrong"
                            )
                            errors = []
                            for tc in failed_calls[:3]:
                                name = tc.get("tool", "?")
                                err = tc.get("result", {}).get("error", "unknown")
                                errors.append(f"  - {name}: {err[:100]}")
                            correction = (
                                f"\n\n⚠️ Correction: The following tool call(s) actually failed:\n"
                                + "\n".join(errors)
                                + "\nPlease check and try again."
                            )
                            response = response.strip() + correction
                        else:
                            logger.info(
                                f"Verification: {len(failed_calls)} tool(s) failed "
                                f"but Jarvis already acknowledged in response — skipping correction"
                            )
                    result["success"] = False

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
            return {"success": False, "message": f"Unknown tool: {tool_name}", "data": {}, "timestamp": ""}

        # State-aware wait optimization — skip tool call if condition already met
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

        result = safety.execute(
            tool_name,
            TOOL_REGISTRY[tool_name],
            args,
            plan={"confidence": 0.80},
        )
        self._state.update(tool_name, args, result)
        return result

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
