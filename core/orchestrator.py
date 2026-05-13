"""
Main routing gate. Bridges brain, safety, tools, and verification.
Injects callbacks into tool_loop to maintain strict layer boundaries.
"""

import logging
import os
import re
import sys

import autonomous.activity_log
import autonomous.task_queue
import settings
from autonomous.approval_gate import ApprovalGate
from autonomous.scheduler import Scheduler
from brain.planner import build_plan
from brain.tool_loop import run as tool_loop_run
from core.feedback_collector import FeedbackCollector, FeedbackType
from safety import executor as safety
from settings import ITERATION_CAPS, TOOL_LOOP_HISTORY_MESSAGES
from skills.skill_store import get_active_skills
from skills.skill_store import init_db as init_skills
from tools import TOOL_REGISTRY, TOOL_SCHEMAS
from tools.read_pc_state import read_pc_state
from verification.verifier import verify_action

from core.console import cli_input
from core.reporter import report

_TOOL_CONFIDENCE: dict[str, float] = {
    "screen": 0.90,
    "input": 0.80,
    "window": 0.85,
    "browser": 0.75,
    "memory": 0.85,
    "exec": 0.80,
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
    def __init__(self, memory=None, long_term_memory=None):
        self._history: list[dict] = CappedList(max_len=40)
        self._mode = "interactive_cloud"
        self._approval_gate = ApprovalGate()
        autonomous.task_queue.init_db()
        self._scheduler = Scheduler(self.handle)
        self._scheduler.start()
        self._memory = memory
        self._long_term_memory = long_term_memory
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
                prefs = memory.get_context_summary()
                if prefs:
                    self._history.append({
                        "role": "system",
                        "content": f"Session restored. User preferences from memory: {prefs}",
                    })
                    logger.info("Loaded memory context summary (no conversation history)")
            except Exception as _e:
                logger.debug(f"Could not load memory context: {_e}")

        self._feedback = FeedbackCollector(storage_path=str(settings.DATA_DIR / "feedback"))

        # ── Implicit feedback loop (retry/abandon detection) ─────────────
        self._implicit_feedback = None
        if getattr(settings, "ENABLE_IMPLICIT_FEEDBACK", False):
            try:
                from core.feedback_loop import get_collector as get_implicit
                self._implicit_feedback = get_implicit()
                logger.info("Implicit feedback loop enabled")
            except Exception as _fb_exc:
                logger.warning(f"Implicit feedback loop unavailable: {_fb_exc}")

        # ── Self-reflection (opt-in, off by default) ─────────────────────
        self._reflector = None
        if getattr(settings, "ENABLE_SELF_REFLECTION", False):
            try:
                from core.self_reflection import SelfReflector
                self._reflector = SelfReflector()
                logger.info("Self-reflection enabled")
            except Exception as _sr_exc:
                logger.warning(f"Self-reflection unavailable: {_sr_exc}")

        # ── Checkpoint manager (resumable autonomous tasks) ──────────────
        self._checkpoint_mgr = None
        try:
            from core.checkpoint_manager import CheckpointManager
            self._checkpoint_mgr = CheckpointManager(
                storage_path=os.path.join(getattr(settings, "DATA_DIR", "data"), "checkpoints")
            )
            logger.info("Checkpoint manager enabled")
        except Exception as _cp_exc:
            logger.warning(f"Checkpoint manager unavailable: {_cp_exc}")

        # ── Skill versioning ─────────────────────────────────────────────
        self._skill_versions = None
        if getattr(settings, "ENABLE_SKILL_VERSIONING", False):
            try:
                from core.skill_versioning import VersionRegistry
                self._skill_versions = VersionRegistry()
                logger.info("Skill versioning enabled")
            except Exception as _sv_exc:
                logger.warning(f"Skill versioning unavailable: {_sv_exc}")

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

            # ── Direct dispatch (skip LLM for common patterns) ─────────────
            try:
                from core.direct_dispatch import try_direct_dispatch
                direct_result = try_direct_dispatch(clean_input, self._execute_tool)
                if direct_result is not None:
                    logger.info("Command handled via direct dispatch")
                    return direct_result
            except Exception as _dd_exc:
                logger.debug(f"Direct dispatch unavailable: {_dd_exc}")

            memory_context = ""
            if self._memory:
                memory_context = self._memory.get_context_summary()

            # Also enrich with long-term semantic memories when available
            if self._long_term_memory:
                try:
                    ltm_context = self._long_term_memory.get_relevant_context(clean_input, max_memories=3)
                    if ltm_context:
                        memory_context = (memory_context + "\n" + ltm_context) if memory_context else ltm_context
                except Exception:
                    pass

            with self._handle_lock:
                history_snapshot = list(self._history)

            # ── Pre-execution planning ──────────────────────────────────────────
            # For action-oriented requests, generate a structured plan before
            # the tool loop executes anything. This avoids the expensive
            # 1-tool-call-per-iteration pattern.
            plan = None
            if _should_plan(clean_input):
                # Include notes from previous planner failures so the LLM learns
                plan_history_context = memory_context or ""
                if self._memory:
                    try:
                        planner_insights = self._memory.get_preference("planner_lessons", "")
                        if planner_insights:
                            plan_history_context += "\n[Planning lessons learned from past failures]:\n" + str(planner_insights)
                    except Exception:
                        pass

                # Ground the planner in live system state
                live_state = ""
                try:
                    from tools.window import window
                    state_result = window(action="state")
                    if state_result.get("success"):
                        parts = []
                        windows = state_result.get("windows", [])
                        processes = state_result.get("processes", [])
                        if windows:
                            parts.append(f"Windows: {' | '.join(w.get('title','?') for w in windows[:6])}")
                        if processes:
                            names = sorted(set(p.get("name","?") for p in processes[:8]))
                            parts.append(f"Processes: {', '.join(names)}")
                        focused = state_result.get("focused_window")
                        if focused:
                            parts.append(f"Focused: {focused}")
                        if parts:
                            live_state = " === LIVE STATE ===\n" + "\n".join(parts)
                except Exception:
                    pass

                try:
                    plan = build_plan(
                        user_input=clean_input,
                        history=history_snapshot,
                        memory_context=plan_history_context,
                        tool_schemas=TOOL_SCHEMAS,
                        live_state=live_state,
                    )
                    if not plan.get("success") or not plan.get("steps"):
                        plan = None
                        logger.info(f"Planner returned no steps for '{clean_input[:50]}' — using ReAct loop")
                    else:
                        logger.info(
                            f"Planner: {len(plan['steps'])} steps for '{clean_input[:50]}'"
                        )
                except Exception as _plan_exc:
                    logger.info(f"Planner failed for '{clean_input[:50]}': {_plan_exc}")
                    plan = None

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
                plan=plan,
            )

            # ── Learn from planner failures ────────────────────────────────────
            # If the plan failed but ReAct succeeded, store a lesson for next time
            if plan and not result.get("plan_executed") and result.get("success") and self._memory:
                plan_steps = [s["tool"] for s in plan.get("steps", [])]
                actual_tools = list({tc["tool"] for tc in result.get("tool_calls", [])})
                lesson = (
                    f"Planned: {plan_steps} | "
                    f"Succeeded with: {actual_tools}"
                )
                try:
                    existing = self._memory.get_preference("planner_lessons", "")
                    updated = lesson if not existing else existing + "\n" + lesson
                    updated = "\n".join(updated.split("\n")[-5:])  # keep last 5
                    self._memory.set_preference("planner_lessons", updated)
                    logger.info(f"Planner lesson stored: {lesson}")
                except Exception:
                    pass

            response = result.get("response", "Done.")

            # ── Self-reflection (opt-in via ENABLE_SELF_REFLECTION) ────────
            if self._reflector and result.get("success"):
                try:
                    reflection = self._reflector.reflect(
                        task_id=clean_input[:40],
                        output=response,
                        user_intent=clean_input,
                    )
                    if reflection and reflection.revised_output:
                        response = reflection.revised_output
                        logger.info(f"Self-reflection revised response (score: {reflection.overall_score:.2f})")
                except Exception as _ref_exc:
                    logger.debug(f"Self-reflection skipped: {_ref_exc}")

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

            # Store successful interactions in long-term memory for cross-session recall
            if self._long_term_memory and result.get("tool_calls"):
                try:
                    self._long_term_memory.remember_interaction(
                        user_input=user_input,
                        agent_response=response,
                        success=result.get("success", False),
                    )
                except Exception:
                    pass

            # ── Record feedback for tool tasks ──────────────────────────────────
            if result.get("tool_calls"):
                try:
                    fb_type = FeedbackType.THUMBS_UP if result.get("success") else FeedbackType.THUMBS_DOWN
                    self._feedback.submit_feedback_sync(
                        task_id=clean_input[:40],
                        feedback_type=fb_type,
                        value=result.get("success"),
                        context={
                            "iterations": result.get("iterations", 0),
                            "tool_count": len(result.get("tool_calls", [])),
                            "plan_executed": result.get("plan_executed", False),
                        },
                    )
                except Exception:
                    pass

            # ── Implicit feedback: track retries and success ─────────────────
            if self._implicit_feedback and result.get("tool_calls"):
                task_key = clean_input[:40]
                tool_names = [tc.get("tool", "") for tc in result.get("tool_calls", [])]
                skill_name = tool_names[0] if tool_names else "unknown"
                try:
                    self._implicit_feedback.start_task(
                        task_key, skill_name, {"input": clean_input[:80]}
                    )
                    if result.get("success"):
                        self._implicit_feedback.record_success(task_key)
                    else:
                        self._implicit_feedback.record_retry(task_key)
                except Exception:
                    pass

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
            result = self.handle(command)
            # Save checkpoint for resumability
            if self._checkpoint_mgr:
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self._checkpoint_mgr.save_checkpoint(
                        task_id=task_id,
                        step_index=0,
                        state={"command": command, "result": result[:500], "success": True},
                        context={"confidence": confidence},
                        force=True,
                    ))
                    loop.close()
                except Exception as _cp_exc:
                    logger.debug(f"Checkpoint save failed: {_cp_exc}")
            return result
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


def _should_plan(user_input: str) -> bool:
    """Determine if a request warrants pre-execution planning.

    Planning is triggered for requests that likely need tool execution.
    Chat-only requests (greetings, simple Q&A) skip planning.
    """
    if not user_input or len(user_input) < 3:
        return False

    chat_patterns = (
        "hello", "hi ", "hey", "thanks", "thank you", "good", "bad",
        "yes", "no", "maybe", "okay", "ok ", "sure", "bye", "goodbye",
        "how are you", "what's up", "sup", "nice",
    )
    if user_input.lower().strip().startswith(chat_patterns):
        return False

    # Commands that involve tools should always plan
    action_triggers = (
        "open ", "launch ", "start ", "close ", "quit ", "kill ",
        "focus ", "minimize ", "maximize ", "restore ", "resize ", "move ",
        "click ", "type ", "press ", "scroll ",
        "capture ", "screenshot ", "find ",
        "enter ", "write ", "paste ",
        "search ", "look up ", "find ",
        "create ", "delete ", "remove ", "copy ", "move ",
        "send ", "email ", "schedule ",
        "list ", "show ", "check ", "get ",
        "set ", "change ", "turn ", "enable ", "disable ",
        "download ", "install ", "update ",
        "where ", "what ", "how do ", "can you ",
    )
    return user_input.lower().strip().startswith(action_triggers)
