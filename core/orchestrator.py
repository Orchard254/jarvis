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
from autonomous.learner import AutoLearner

from agents.jarvis import run as tool_loop_run
from agents.base_agent import SubAgentTask
from safety import executor as safety
from settings import ITERATION_CAPS
from skills.skill_store import get_active_skills, search_by_intent
from skills.skill_store import init_db as init_skills
from tools import TOOL_REGISTRY
from indexer.state_monitor import read_pc_state
from verification.verifier import verify_action

from core.classifier import is_special_command
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

        self._learner = AutoLearner(
            TOOL_REGISTRY, self._execute_wrapper,
            idle_threshold_minutes=settings.AUTO_LEARNER_IDLE_MINUTES,
            min_practice_interval_minutes=settings.AUTO_LEARNER_INTERVAL_MINUTES,
        )
        if settings.ENABLE_AUTO_LEARNER:
            self._learner.start()

        self.running = True

        self.event_bus = event_bus
        self._last_tool_calls: list[dict] = []
        init_skills()

        # Inject safety-gated execute/verify into all registered sub-agents
        from agents.sub_agent_registry import registry
        import agents.sub_agents  # noqa: F401 — triggers agent registration
        registry.inject_into_agents(self._execute_wrapper, self._verify_wrapper)

        # Start a background event loop thread for async monitors
        self._loop = asyncio.new_event_loop()
        def _run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        self._loop_thread = threading.Thread(target=_run_loop, daemon=True, name="jarvis-async-loop")
        self._loop_thread.start()

        # Schedule async_init to run in the background event loop
        asyncio.run_coroutine_threadsafe(self.async_init(), self._loop)

    async def async_init(self):
        try:
            # Start the event bus after the event loop is running
            self.event_bus.start()

            # Launch ProactiveAgent in a separate shell process
            self._launch_proactive_shell()

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

            # Start Context Recorder
            try:
                from autonomous import context_recorder
                import atexit
                context_recorder.start(asyncio.get_running_loop())
                atexit.register(context_recorder.stop)
            except Exception as e:
                logger.warning(f"Context recorder unavailable: {e}")

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
                file_system_monitor.start(asyncio.get_running_loop(), path=jarvis_path)
                atexit.register(file_system_monitor.stop)
            except Exception:
                logger.warning("File system monitor unavailable")

            # Start Window Monitor
            try:
                from autonomous import window_monitor
                window_monitor.start(asyncio.get_running_loop())
                atexit.register(window_monitor.stop)
            except Exception:
                logger.warning("Window monitor unavailable")

            self._history_hydrated = False
        except Exception as e:
            logger.error("Error in async_init", exc_info=True)

    def stop(self):
        """Clean teardown of scheduler, learner, event bus, loop thread, and background monitors."""
        logger.info("Orchestrator: stopping all services...")
        self.running = False

        # 1. Stop scheduler and learner
        try:
            self._scheduler.stop()
        except Exception as e:
            logger.warning(f"Orchestrator: failed to stop scheduler: {e}")

        try:
            self._learner.stop()
        except Exception as e:
            logger.warning(f"Orchestrator: failed to stop learner: {e}")

        # 2. Stop monitors
        for monitor_name in ("ambient_monitor", "context_recorder", "clipboard_monitor", "file_system_monitor", "window_monitor"):
            try:
                mod = __import__("autonomous." + monitor_name, fromlist=[monitor_name])
                if hasattr(mod, "stop"):
                    mod.stop()
            except Exception as e:
                logger.warning(f"Orchestrator: failed to stop monitor '{monitor_name}': {e}")

        # Also heartbeat monitor if available
        try:
            from core.heartbeat_monitor import monitor
            monitor.stop()
        except Exception:
            pass

        # 2.5 Kill the proactive shell subprocess
        self._stop_proactive_shell()

        # 3. Stop Event Bus inside the loop
        if self._loop and self._loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self.event_bus.stop(), self._loop)
                fut.result(timeout=2.0)
            except Exception as e:
                logger.warning(f"Orchestrator: failed to stop event bus asynchronously: {e}")

            # 4. Stop the loop and thread
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._loop_thread.join(timeout=2.0)
            except Exception as e:
                logger.warning(f"Orchestrator: failed to stop loop thread: {e}")

    def _launch_proactive_shell(self):
        import subprocess
        import os
        shell_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "proactive_shell.py")
        if not os.path.exists(shell_path):
            logger.warning("proactive_shell.py not found, running ProactiveAgent in-process")
            from agents.sub_agent_registry import registry
            agent = registry.get("proactive")
            if agent:
                asyncio.create_task(agent.run(SubAgentTask(goal="Start proactive monitoring", context={})))
            return
        try:
            self._proactive_proc = subprocess.Popen(
                [sys.executable, "-u", shell_path],
                stdin=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            self._proactive_forward_task = asyncio.create_task(self._forward_events_to_shell())
            logger.info("ProactiveAgent launched in separate shell (PID %d)", self._proactive_proc.pid)
        except Exception as e:
            logger.error(f"Failed to launch proactive shell: {e}")

    async def _forward_events_to_shell(self):
        import json
        loop = asyncio.get_event_loop()
        async def _forward(event: dict):
            try:
                line = json.dumps(event) + "\n"
                await loop.run_in_executor(None, self._proactive_proc.stdin.write, line.encode())
                await loop.run_in_executor(None, self._proactive_proc.stdin.flush)
            except Exception as e:
                logger.debug(f"Forward to proactive shell: {e}")

        event_bus.subscribe("system_alert", _forward)
        event_bus.subscribe("window_focus_changed", _forward)
        event_bus.subscribe("clipboard_changed", _forward)
        event_bus.subscribe("file_system_changed", _forward)

    def _stop_proactive_shell(self):
        proc = getattr(self, "_proactive_proc", None)
        if proc and proc.poll() is None:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            logger.info("Proactive shell terminated")

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
                    code = match.get("code", "")
                    language = match.get("language", "python")
                    try:
                        skill_result = self._execute_wrapper(
                            "execute_code",
                            {"code": code, "language": language, "timeout": 30},
                        )
                        if skill_result and skill_result.get("success"):
                            skill_hint = (
                                f"✅ Auto-ran saved skill for intent '{text}' ({language}):\n"
                                f"  result: {str(skill_result.get('stdout', skill_result.get('result', '')))[:500]}"
                            )
                        else:
                            skill_hint = (
                                f"⚠ Saved skill for intent '{text}' failed:\n"
                                f"  error: {skill_result.get('error', 'unknown')[:300]}\n"
                                f"  code: {code[:300]}"
                            )
                    except Exception as e:
                        skill_hint = (
                            f"⚠ Saved skill for intent '{text}' raised exception:\n"
                            f"  error: {e}\n"
                            f"  code: {code[:300]}"
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
                from verification.state_checks import verify_window_visible
                if verify_window_visible(target):
                    return {"success": True, "message": f"Wait skipped: '{target}' already visible", "data": {}, "timestamp": ""}
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
            plan={"confidence": 0.80, "tool_name": tool_name},
        )
        self._state.update(tool_name, args, result)
        return result

    def _verify_wrapper(self, tool_name: str, result: dict, expected: str, pre_img=None, post_img=None) -> dict:
        return verify_action(tool_name, result, expected=expected, pre_img=pre_img, post_img=post_img)

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
