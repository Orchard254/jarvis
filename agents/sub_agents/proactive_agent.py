import logging
import asyncio
import time

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register
from core.event_bus import event_bus
from core.ambient_state import get_state
from brain import ollama_client
from brain.prompt_builder import build_system_prompt
from brain.response_parser import parse_batch_plan, validate_tool_calls
from tools import TOOL_REGISTRY
from settings import ITERATION_CAPS, MAX_CONTEXT_TOKENS

logger = logging.getLogger(__name__)


class ProactiveAgent(SubAgentBase):
    name = "proactive"
    description = (
        "Monitors system events and user context to initiate proactive actions. "
        "Uses LLM reasoning to decide if an action is warranted and what action to take."
    )
    capabilities = [
        "monitor_events",
        "decide_proactive_action",
        "execute_proactive_plan",
    ]

    def __init__(self, event_source="event_bus"):
        super().__init__()
        self._event_queue = asyncio.Queue()
        self._is_monitoring = False
        self._last_ambient_check = 0.0
        self._ambient_check_interval = 120
        self._debounce_window = 2.0
        self._last_cooldown = {}
        self._cooldown_secs = {"file_system_changed": 120, "clipboard_changed": 60, "window_focus_changed": 60}
        self._event_source = event_source

    async def _event_listener(self, event: dict):
        await self._event_queue.put(event)

    async def _monitor_loop(self):
        self._is_monitoring = True
        if self._event_source == "event_bus":
            event_bus.subscribe("system_alert", self._event_listener)
            event_bus.subscribe("window_focus_changed", self._event_listener)
            event_bus.subscribe("clipboard_changed", self._event_listener)
            event_bus.subscribe("file_system_changed", self._event_listener)
        elif self._event_source == "stdin":
            asyncio.create_task(self._stdin_reader())
        logger.info("ProactiveAgent: monitoring loop started")

        while self._is_monitoring:
            try:
                # Check for ambient state changes periodically
                now = time.time()
                if now - self._last_ambient_check >= self._ambient_check_interval:
                    self._last_ambient_check = now
                    await self._check_ambient_state()

                # Process queued events with coalescing + per-type cooldown
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=30)

                    # Coalesce: drain any additional events that arrived within the debounce window
                    await asyncio.sleep(self._debounce_window)
                    coalesced = [event]
                    while not self._event_queue.empty():
                        try:
                            coalesced.append(self._event_queue.get_nowait())
                            self._event_queue.task_done()
                        except asyncio.QueueEmpty:
                            break

                    # Pick the most significant event from the batch
                    event = self._pick_event(coalesced)

                    # Per-type cooldown check
                    etype = event["event_type"]
                    now = time.time()
                    last = self._last_cooldown.get(etype, 0)
                    if now - last < self._cooldown_secs.get(etype, 0):
                        continue

                    self._last_cooldown[etype] = now

                    # Quick heuristic: skip LLM for low-significance events
                    if not self._is_actionable(event):
                        logger.info(f"ProactiveAgent: skipped {etype} ({len(coalesced)} coalesced) — not actionable")
                        self._event_queue.task_done()
                        continue

                    logger.info(f"ProactiveAgent: event {etype} ({len(coalesced)} coalesced)")
                    await self._process_event(event)
                    self._event_queue.task_done()
                except asyncio.TimeoutError:
                    pass  # no events in 30s, loop back for ambient check

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ProactiveAgent: loop error: {e}")

        logger.info("ProactiveAgent: monitoring loop stopped")

    async def _check_ambient_state(self):
        """Periodic ambient state check — notice issues proactively."""
        try:
            ambient = get_state()
            snap = ambient.snapshot()

            # Quick heuristic checks before calling LLM
            alerts = []
            if snap.get("cpu_percent", 0) > 90:
                alerts.append(f"CPU at {snap['cpu_percent']:.0f}%")
            if snap.get("ram_percent", 0) > 85:
                alerts.append(f"RAM at {snap['ram_percent']:.0f}%")
            if snap.get("disk_percent", 0) > 92:
                alerts.append(f"disk at {snap['disk_percent']:.0f}%")
            battery = snap.get("battery_percent")
            if battery is not None and battery < 20 and not snap.get("battery_plugged"):
                alerts.append(f"battery at {battery:.0f}% (not plugged in)")

            if not alerts:
                return  # nothing to flag

            logger.info(f"ProactiveAgent: ambient alerts detected: {alerts}")
            msg = f"System alert: {'; '.join(alerts)}"
            self._tool("notify", title="F.R.I.D.A.Y.", message=msg)
        except Exception as e:
            logger.debug(f"ProactiveAgent: ambient check error: {e}")

    def _pick_event(self, events: list) -> dict:
        """From a coalesced batch, return the most significant event."""
        priority = {"system_alert": 3, "clipboard_changed": 2, "window_focus_changed": 1, "file_system_changed": 0}
        return max(events, key=lambda e: (priority.get(e.get("event_type", ""), -1), e.get("timestamp", 0)))

    async def _stdin_reader(self):
        import sys, json
        loop = asyncio.get_event_loop()
        while self._is_monitoring:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                event = json.loads(line.strip())
                await self._event_queue.put(event)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.error(f"ProactiveAgent: stdin read error: {e}")

    def _is_actionable(self, event: dict) -> bool:
        """Quick heuristic: skip LLM for low-significance events."""
        etype = event["event_type"]
        if etype == "system_alert":
            return True
        if etype in ("file_system_changed", "clipboard_changed"):
            return False
        return True

    async def _process_event(self, event: dict):
        """Decide whether to act on an event, and execute if warranted."""
        system_prompt = build_system_prompt(agent_name=self.name, prompt_file="proactive")

        # Include current ambient state so the LLM has full context
        try:
            ambient = get_state()
            ambient_context = ambient.format_context()
        except Exception:
            ambient_context = "(ambient state unavailable)"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"Event: {event['event_type']} from {event['source']}. "
                f"Details: {event.get('payload', {})}.\n\n"
                f"{ambient_context}\n\n"
                "Should I take any proactive action? If so, output a BATCH_TOOL_PLAN."
            )}
        ]

        try:
            llm_result = ollama_client.chat_stream(
                messages=messages,
                temperature=0.3,
                reasoning_effort="medium",
            )
            content = llm_result.get("content", "")
            logger.info(f"ProactiveAgent LLM: {content[:300]}")

            batch_plan, plan_err = parse_batch_plan(content, set(TOOL_REGISTRY.keys()))
            if batch_plan:
                calls = batch_plan.get("calls", [])
                logger.info(f"ProactiveAgent: executing {len(calls)} proactive action(s)")
                for call in calls:
                    tool = call.get("tool", "")
                    params = call.get("params", {})
                    try:
                        result = self._tool(tool, **params)
                        logger.info(f"ProactiveAgent: {tool} -> {result.get('success', False)}")
                    except Exception as exc:
                        logger.error(f"ProactiveAgent: {tool} failed: {exc}")
            elif content and "NO_ACTION" not in content.upper() and len(content) < 200:
                # Only notify for short natural-language messages, not unparseable plan dumps
                if not any(c in content for c in ("|", "```", "BATCH_TOOL_PLAN", "Step", "|------")):
                    self._tool("notify", title="F.R.I.D.A.Y.", message=content)

        except Exception as e:
            logger.error(f"ProactiveAgent: LLM call failed: {e}")

    async def run(self, task: SubAgentTask) -> SubAgentResult:
        if not self._is_monitoring:
            asyncio.create_task(self._monitor_loop())
            return SubAgentResult(
                success=True,
                summary="Proactive agent started monitoring events.",
                data={},
                agent_name=self.name,
            )
        return SubAgentResult(
            success=True,
            summary="Proactive agent is already monitoring events.",
            data={},
            agent_name=self.name,
        )

register(ProactiveAgent())
