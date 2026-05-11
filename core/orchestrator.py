"""
Main routing gate. Bridges brain, safety, tools, and verification.
Injects callbacks into tool_loop to maintain strict layer boundaries.
"""

import inspect
import logging
import re
import sys
import time as _time
from typing import Optional

import autonomous.activity_log
import autonomous.task_queue
import settings
from autonomous.approval_gate import ApprovalGate
from autonomous.scheduler import Scheduler
from brain.tool_loop import run as tool_loop_run
from safety import executor as safety
from settings import ENABLE_PLANNING, ENABLE_REFLECTION, ITERATION_CAPS, TOOL_LOOP_HISTORY_MESSAGES
from skills.skill_runner import run_skill
from skills.skill_store import get_active_skills, search_by_intent
from skills.skill_store import init_db as init_skills
from tools import TOOL_REGISTRY
from verification.verifier import verify_action

from core.console import cli_input
from core.recovery import RecoveryManager
from core.reporter import report

# Per-tool confidence values used by the safety gate.
# Read-only tools get high confidence; mutating/control tools get lower
# so the gate actually exercises its threshold for risky actions.
_TOOL_CONFIDENCE: dict[str, float] = {
    "query_pc_index": 0.95,
    "read_pc_state": 0.95,
    "capture_screen": 0.95,
    "notify_user": 0.95,
    "read_file": 0.90,
    "write_file": 0.80,
    "execute_code": 0.80,
    "control_window": 0.80,
    "control_input": 0.75,  # direct HID control is the most sensitive
    "search_web": 0.95,  # read-only web search
    "fetch_url": 0.95,  # read-only URL fetch
    "browser": 0.75,  # browser control can have side effects
    "clipboard": 0.90,  # clipboard read/write
    "process_manager": 0.70,  # killing processes is high-risk
    "system_settings": 0.80,  # changing system settings
    "file_ops": 0.75,  # file operations (delete/move are risky)
    "find_on_screen": 0.90,  # vision-guided, read-mostly
}

logger = logging.getLogger(__name__)


class CappedList(list):
    """List that enforces a maximum length of 40 (20 turns)."""

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
        self._recovery = RecoveryManager()
        self._mode = "interactive_cloud"  # Default for cloud dev
        self._approval_gate = ApprovalGate()
        autonomous.task_queue.init_db()
        self._scheduler = Scheduler(self.handle)  # Pass handle as callback
        self._scheduler.start()  # Bug fix: start() was never called — tasks never fired
        self._memory = memory
        self.running = True
        self._last_tool_calls: list[dict] = []  # exposed for scheduler action_log
        # Prevents concurrent handle() calls from corrupting _history (CappedList
        # is not thread-safe). Wake-word callbacks run on background threads, so
        # without this a duplicate wake trigger races with the in-flight response.
        self._handle_lock = __import__("threading").Lock()
        init_skills()

        # Cache whether tool_loop_run accepts a 'recovery' kwarg so we don't
        # call inspect.signature() on every handle() invocation.
        _tl_sig = inspect.signature(tool_loop_run)
        self._tool_loop_accepts_recovery: bool = "recovery" in _tl_sig.parameters

        # ── Start Heartbeat Monitor for task tracking ────────────────────────────
        try:
            from core.heartbeat_monitor import monitor
            monitor.start()
            logger.info("Heartbeat monitor started")
        except Exception as _hb_exc:
            logger.warning(f"Heartbeat monitor failed to start: {_hb_exc}")

        # ── Warm up the semantic intent classifier in the background ─────────────
        # The classifier embeds ~150 prototype phrases on first use.  Running this
        # in a daemon thread means the first user command doesn't pay the latency
        # cost — by the time the user speaks, the vectors are ready.
        # REMOVED: intent_classifier warmup - classifier no longer exists
        # All tool selection is now handled directly by the main LLM

        # ── Load recent conversation history from episodic memory ──────────────
        # Pre-populate _history so the LLM sees prior context across restarts.
        if memory:
            try:
                recent = memory.get_recent_episodes(limit=20)
                for ep in reversed(recent):  # oldest first → chronological
                    cmd = ep.get("command_text", "")
                    # response text is stored in tool_result as {"response": ...}
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

        # ── Start ambient system monitor ─────────────────────────────────────────
        # Monitors battery, CPU, RAM, disk and fires notify_user() alerts.
        if getattr(settings, "AMBIENT_MONITORING", True):
            try:
                from autonomous import ambient_monitor

                ambient_monitor.start()
                import atexit

                atexit.register(ambient_monitor.stop)
                logger.info("Ambient monitor started")
            except Exception as _am_exc:
                logger.warning(f"Ambient monitor unavailable: {_am_exc}")

        # ── Restore persisted recurring schedules ──────────────────────────────────
        # Recurring tasks are now persisted to DB so they survive restarts.
        # _load_recurring_from_db() is called inside Scheduler.__init__.

        logger.info(
            "Orchestrator initialized with full pipeline wiring and Skill Store"
        )

    def _check_skill_first(self, intent: dict) -> dict | None:
        """Check skill store for semantic match. Returns result if hit, None if miss."""
        intent_text = (
            intent.get("goal", intent.get("raw_input", "")).lower()
            if isinstance(intent, dict)
            else str(intent).lower()
        )
        logger.debug(f"Skill search: intent='{intent_text}'")

        skill = search_by_intent(intent_text)

        if skill:
            logger.info(
                f"Skill hit: {skill['skill_id'][:8]} — '{skill['intent_label']}' (similarity={skill.get('similarity', 'N/A')})"
            )
            result = run_skill(skill["skill_id"], intent_text)
            if result.get("success"):
                return {
                    "response": f"✅ Ran saved skill: {skill['intent_label']}",
                    "skill_used": True,
                }
            else:
                logger.warning(
                    f"⚠️ Skill failed, falling back to LLM: {skill['skill_id'][:8]} — {result.get('error')}"
                )
        else:
            logger.debug(f"❌ Skill miss: no match for '{intent_text}'")
        return None

    # ── Preference extraction ───────────────────────────────────────────────────
    # Patterns of the form "my name is X", "call me X", etc. are detected and
    # written to semantic memory immediately so JARVIS remembers them in future
    # sessions without having to search the PC or ask again.

    _PREF_PATTERNS: list[tuple[str, str]] = [
        # (regex pattern,  semantic-memory key)
        (r"my (?:real |full |preferred )?name is ([\w]+)", "user_name"),
        (r"(?:call|refer to) me (?:as )?([\w]+)", "user_name"),
        (r"i(?:'m| am) (?:called |named )?([\w]+)", "user_name"),
        (r"people (?:call|know) me (?:as )?([\w]+)", "user_name"),
        (r"my (?:preferred )?language is ([\w]+)", "preferred_language"),
        (r"i (?:prefer|like|use|love) ([\w]+) (?:browser)", "preferred_browser"),
        (r"i (?:prefer|like|use|love) ([\w]+) (?:editor|ide)", "preferred_editor"),
    ]

    def _extract_preferences(self, user_input: str) -> None:
        """
        Scan *user_input* for explicit self-description patterns and save
        any matched values to semantic memory.
        """
        if not self._memory:
            return
        text = user_input.lower().strip()
        for pattern, key in self._PREF_PATTERNS:
            m = re.search(pattern, text)
            if m:
                value = m.group(1).strip().capitalize()
                if len(value) < 2:
                    continue  # skip single-char false-positives
                self._memory.set_preference(
                    key, value, confidence=1.0, source="explicit"
                )
                logger.info("Saved user preference: %s = %s", key, value)
                break  # one preference per turn is enough

    def handle(self, user_input: str) -> str:
        logger.info(f"Orchestrator.handle: '{user_input}'")
        with self._handle_lock:
            try:
                # Strip any leading numbering like "1. " from user input
                clean_input = re.sub(r"^\d+\.\s*", "", user_input).strip()

                # ── Extract and persist user preferences from this turn ─────────────────
                # Done BEFORE writing to episodic so the preference is available
                # immediately if the LLM needs it in the same turn.
                self._extract_preferences(clean_input)

                # Log user input to memory
                if self._memory:
                    self._memory.write_episodic("command", command_text=user_input)

                # Check for skill status command first
                if clean_input.lower() == "skills status":
                    active_skills = get_active_skills()
                    if not active_skills:
                        return "No active skills yet."
                    skill_strings = [
                        f"{s['skill_id']} ({s['intent_label']})" for s in active_skills
                    ]
                    return f"Active skills: {', '.join(skill_strings)}"

                # Check for task status commands
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

                # Check for skill match first with clean input
                skill_result = self._check_skill_first(clean_input)
                if skill_result:
                    # Update history for skill execution
                    skill_response = skill_result.get(
                        "response", "✅ Skill executed successfully"
                    )
                    self._history.append({"role": "user", "content": user_input})
                    self._history.append({"role": "assistant", "content": skill_response})
                    return skill_response

                # Direct to tool loop - let main LLM decide everything
                # No intent routing layer - modern LLMs handle simple, complex, and ambiguous commands
                original_intent = clean_input

                # Fast-path scripts disabled: Modern LLMs handle all commands well
                # with tool calling. The 278-line get_fallback_script() implementation
                # was removed as the complexity wasn't justified for the marginal gain.

                # ── Main LLM Tool-Calling Loop ────────────────────────────────
                memory_context = ""
                if self._memory:
                    parts = []

                    # ── Recent command history — single DB call serves both uses ──────
                    # Fetch limit=5 once; the first 3 are used for the timestamped
                    # history block, all 5 for the "This session:" summary line.
                    recent_episodes = self._memory.get_recent_episodes(limit=5)
                    if recent_episodes:
                        history_lines = []
                        for i, cmd in enumerate(recent_episodes[:3], 1):
                            ts = cmd.get("timestamp", 0)
                            ago = f"{int(_time.time() - ts)}s ago" if ts else ""
                            txt = cmd.get("command_text", "")
                            ok = cmd.get("success")
                            status = "✓" if ok else ("✗" if ok is False else "?")
                            if txt:
                                history_lines.append(f"  {i}. [{ago}] {status} {txt}")
                        if history_lines:
                            parts.append(
                                "Recent commands (use to determine if this is a follow-up):\n"
                                + "\n".join(history_lines)
                            )

                        # ── User identity: always inject first so it's most prominent ──────
                        user_name = self._memory.get_preference("user_name")
                        if user_name:
                            parts.append(f"The user's name is {user_name}.")

                        # Semantic preferences + frequent command summary
                        pref_summary = self._memory.get_context_summary()
                        if pref_summary:
                            parts.append(pref_summary)

                        # Cross-session history (survives restarts)
                    cross_session = self._memory.get_cross_session_context(limit=8)
                    if cross_session:
                        parts.append(cross_session)

                    # Session summary — reuse the episodes already fetched above
                    recent_cmds_text = [
                        e.get("command_text", "") for e in recent_episodes if e.get("command_text")
                    ] if recent_episodes else []
                    recent_str = "; ".join(recent_cmds_text[-3:]) if recent_cmds_text else ""
                    if recent_str:
                        parts.append(f"This session: {recent_str}")

                    # Get reflection insights (learned from previous tasks)
                    try:
                        from memory.semantic import get_relevant_insights

                        insights = get_relevant_insights(
                            [],
                            max_insights=3
                        )
                        if insights:
                            insights_str = "Relevant learnings:\n" + "\n".join(
                                f"• {i}" for i in insights
                            )
                            parts.append(insights_str)
                    except Exception:
                        pass

                    memory_context = "\n".join(parts)

                # ── Optional: Pre-execution planning ───────────────────────────────────
                # For complex multi-step requests, ask the LLM to generate a plan
                # before entering the tool loop. Inject the plan into memory_context
                # so the tool loop LLM has explicit step guidance.
                # Hard timeout: if the planning LLM call takes >20s, skip the plan
                # and proceed immediately. The tool loop handles the task fine without
                # a plan — a 3-minute freeze while "planning" is far worse than no plan.
                if ENABLE_PLANNING:
                    try:
                        from brain.planner import plan as brain_plan
                        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout

                        with ThreadPoolExecutor(max_workers=1) as _plan_pool:
                            _plan_future = _plan_pool.submit(
                                brain_plan, clean_input, list(self._history), memory_context
                            )
                            try:
                                plan_steps = _plan_future.result(timeout=20)
                            except _FutureTimeout:
                                logger.debug("Planning timed out (>20s) — skipping plan")
                                plan_steps = None

                        if plan_steps:
                            plan_str = "Execution plan:\n" + "\n".join(
                                f"  {i + 1}. {step}" for i, step in enumerate(plan_steps)
                            )
                            memory_context = (memory_context + "\n\n" + plan_str).strip()
                            logger.info(
                                f"Plan generated: {len(plan_steps)} steps for "
                                f"'{clean_input[:60]}'"
                            )
                    except Exception as _plan_exc:
                        logger.debug(f"Planning skipped: {_plan_exc}")

                # Conditionally pass recovery if tool_loop supports it (forward-compat)
                _tl_kwargs: dict = {}
                if self._tool_loop_accepts_recovery:
                    _tl_kwargs["recovery"] = self._recovery
                result = tool_loop_run(
                    user_input=clean_input,
                    history=self._history,
                    execute_fn=self._execute_wrapper,
                    verify_fn=self._verify_wrapper,
                    mode=self._mode,
                    tools=[],  # No pre-filtering - let main LLM decide all tools
                    memory_context=memory_context,
                    **_tl_kwargs,
                )

                response = result.get("response", "Done.")
                self._last_tool_calls = result.get("tool_calls", [])

                # Enrich response with reporter formatting if tool calls were made.
                # The reporter reads actual tool stdout (execute_code) and structured
                # results — it is the ground truth for what actually happened on disk /
                # in the OS.  We always prefer it over the LLM's narration, which is
                # based on what the model *expected* to happen and can disagree with
                # the real outcome (e.g. "2x1 grid" when the script found 4 windows).
                # Streaming is already suppressed on iterations 2+ in tool_loop, so
                # users never see the inaccurate narration; only the reporter output
                # reaches the JARVIS: line and the TTS engine.
                if result.get("tool_calls"):
                    try:
                        formatted = report(
                            intent={"goal": original_intent, "raw_input": user_input},
                            results=result.get("tool_calls", []),
                            verification={
                                "status": "CONFIRMED"
                                if result.get("success")
                                else "FAILED",
                                "summary": response,
                            },
                        )
                        # Use reporter output whenever it produces substantive text.
                        # No "!= response" guard — reporter is authoritative for tool results.
                        if formatted and len(formatted) > 5:
                            response = formatted
                    except Exception as _rep_exc:
                        logger.debug(f"Reporter skipped: {_rep_exc}")

                # Log response to memory (store response text in tool_result for retrieval)
                if self._memory:
                    self._memory.write_episodic(
                        "response",
                        command_text=user_input,
                        tool_name="tool_loop",
                        success=result.get("success"),
                        tool_result={"response": response[:500]},
                    )

                # If successful, check for execute_code and save as candidate skill
                if result.get("success"):
                    tool_log = result.get("tool_calls", [])
                    for entry in tool_log:
                        if entry.get("tool") == "execute_code":
                            tool_result = entry.get("result", {})
                            if tool_result.get("success"):
                                args = entry.get("args", {})
                                code = args.get("code", "")
                                language = args.get("language", "python")
                                if code:
                                    from skills.skill_store import save_candidate

                                    # Use original_intent (set before fast-path error
                                    # injection) so skill labels stay clean.
                                    skill_id = save_candidate(
                                        original_intent, code, language
                                    )
                                    if skill_id:
                                        logger.info(
                                            f"Saved candidate skill {skill_id} "
                                            f"for intent: {original_intent}"
                                        )

                    # Observe usage pattern for semantic memory learning
                    if self._memory:
                        self._memory.observe_pattern(
                            "last_successful_command", original_intent[:100]
                        )

                # ── Record route outcome → REMOVED: intent learner no longer exists ──
                # Tool selection is now handled directly by the main LLM without caching


                # ── Post-execution reflection ───────────────────────────────────────
                # Ask the LLM to extract learnable patterns from what just happened.
                # Runs in a daemon thread so it NEVER blocks the CLI response.
                # The comment above claiming "non-blocking" was aspirational — the
                # original code ran synchronously inside the handle lock, causing
                # up to 180s of apparent freeze after every command.
                if ENABLE_REFLECTION and self._memory:
                    _reflect_args = (
                        user_input,
                        result.get("tool_calls", []),
                        result.get("success", False),
                        self._memory,
                    )

                    def _run_reflection(args=_reflect_args):
                        try:
                            from brain.reflection import reflect as brain_reflect
                            brain_reflect(*args)
                        except Exception as _ref_exc:
                            logger.debug(f"Reflection skipped: {_ref_exc}")

                    import threading as _threading
                    _threading.Thread(
                        target=_run_reflection, daemon=True, name="reflection"
                    ).start()

                # Update conversation history (keep last 20 turns = 40 entries)
                self._history.append({"role": "user", "content": user_input})
                self._history.append({"role": "assistant", "content": response})

                # Handle failure/escalation
                if not result.get("success"):
                    error = result.get("error", "Unknown execution error")
                    escalation = self._recovery.escalate(user_input, "tool_loop", error)
                    return escalation or response

                self._recovery.reset()
                return response

            except Exception as e:
                logger.error(f"Orchestrator pipeline error: {e}", exc_info=True)
                return self._recovery.escalate(user_input, "orchestrator", str(e))

    def _execute_wrapper(self, tool_name: str, args: dict) -> dict:
        """Injects safety.execute() into the LLM loop."""
        if tool_name not in TOOL_REGISTRY:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        tool_fn = TOOL_REGISTRY[tool_name]
        # Use per-tool confidence so the safety gate actually differentiates
        # between risky mutating tools and safe read-only ones.
        confidence = _TOOL_CONFIDENCE.get(tool_name, 0.80)
        return safety.execute(tool_name, tool_fn, args, plan={"confidence": confidence})

    def _verify_wrapper(self, tool_name: str, result: dict, expected: str) -> dict:
        """Injects 3-tier verification into the LLM loop."""
        return verify_action(tool_name, result, expected=expected)

    def set_mode(self, mode: str):
        """Switch execution mode (interactive/autonomous + cloud/local)."""
        if mode in ITERATION_CAPS:
            self._mode = mode
            logger.info(f"Execution mode set to: {mode}")
        else:
            logger.warning(f"Unknown mode: {mode}. Defaulting to {self._mode}")

    def handle_autonomous(self, task_id: str, command: str, confidence: float) -> str:
        """Handle a task running in autonomous mode (approval already checked by Scheduler)."""
        # Raise confidence threshold for autonomous — safer execution
        original_threshold = settings.CONFIDENCE_THRESHOLD
        settings.CONFIDENCE_THRESHOLD = settings.AUTONOMOUS_CONFIDENCE_THRESHOLD
        try:
            return self.handle(command)
        finally:
            settings.CONFIDENCE_THRESHOLD = original_threshold

    def check_approval_response(self, task_id: str, user_input: str) -> str | None:
        """
        Legacy polling hook — no longer used.
        Approval is now handled synchronously inside ApprovalGate.request()
        (blocking CLI prompt with timeout).  This method is kept so that any
        external callers do not raise AttributeError, but always returns None.
        """
        return None

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

                # Check for approval responses first
                approval_response = self.check_approval_response("pending", user_input)
                if approval_response:
                    print(f"\nJARVIS: {approval_response}")
                    continue

                # Direct CLI command handlers (never hit LLM)
                if (
                    user_input.lower().startswith("skill")
                    and "status" in user_input.lower()
                ):
                    skills = get_active_skills(limit=10)
                    if skills:
                        print(
                            "\n"
                            + "\n".join(
                                [
                                    f"✅ {s['intent_label']} (success: {s['success_rate']:.0%})"
                                    for s in skills
                                ]
                            )
                        )
                    else:
                        print(
                            "\nNo active skills yet. Use JARVIS normally to teach it new tasks."
                        )
                    continue
                elif user_input.lower() == "summary":
                    from autonomous.activity_log import generate_summary

                    print(f"\n{generate_summary()}")
                    continue
                elif user_input.lower() == "status":
                    # Quick system snapshot (RAM/CPU/Disk)
                    import shutil

                    import psutil

                    ram = psutil.virtual_memory()
                    disk_path = "C:\\" if sys.platform == "win32" else "/"
                    try:
                        disk = shutil.disk_usage(disk_path)
                    except Exception:
                        disk = shutil.disk_usage(".")
                    print(
                        f"\n💻 RAM: {ram.percent}% used | 💾 Disk C: {disk.used // 1e9:.1f}GB / {disk.total // 1e9:.1f}GB"
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
                        print(f"\n📅 Scheduled: '{cmd}' ({tid[:8]})")
                    continue

                # Normal command (fallback to orchestrator.handle())
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
