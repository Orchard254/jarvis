import logging
import asyncio

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register
from core.event_bus import event_bus
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

    def __init__(self):
        super().__init__()
        self._event_queue = asyncio.Queue()
        self._is_monitoring = False

    async def _event_listener(self, event: dict):
        await self._event_queue.put(event)

    async def _monitor_loop(self):
        self._is_monitoring = True
        event_bus.subscribe("system_alert", self._event_listener)
        event_bus.subscribe("window_focus_changed", self._event_listener)
        event_bus.subscribe("clipboard_changed", self._event_listener)
        event_bus.subscribe("file_system_changed", self._event_listener)
        # event_bus.subscribe("email_received", self._event_listener)

        while self._is_monitoring:
            try:
                event = await self._event_queue.get()
                logger.info(f"ProactiveAgent: Received event: {event['event_type']} from {event['source']}")
                # Process event with LLM for proactive decision
                await self._process_event_with_llm(event)
                self._event_queue.task_done()
            except asyncio.CancelledError:
                logger.info("ProactiveAgent: Monitoring loop cancelled.")
                break
            except Exception as e:
                logger.error(f"ProactiveAgent: Error in monitoring loop: {e}")

    async def _process_event_with_llm(self, event: dict):
        # Build context for LLM
        system_prompt = build_system_prompt(agent_name=self.name, prompt_file="proactive.yaml")
        # Fetch user preferences from memory (conceptual)
        # from memory import semantic
        # user_prefs = semantic.get_all()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"An event has occurred: {event['event_type']}. Source: {event['source']}. Details: {event['payload']}. Current context: (add current system/user context here). Should I take any proactive action? If so, what action?"}
        ]

        try:
            llm_result = await ollama_client.chat_stream(
                messages=messages,
                temperature=0.5,
                reasoning_effort="medium",
            )
            content = llm_result.get("content", "")
            logger.info(f"ProactiveAgent LLM response: {content[:500]}")

            batch_plan, plan_err = parse_batch_plan(content, set(TOOL_REGISTRY.keys()))
            if batch_plan:
                logger.info(f"ProactiveAgent: Executing proactive plan: {batch_plan}")
                # In a real scenario, this would delegate to agents.execution.run_plan
                # For now, just log the intent
                # await self._execute_proactive_plan(batch_plan)
            elif content and "NO_ACTION" not in content.upper():
                # If LLM suggests a response but not a tool plan, notify user
                self._tool("notify", message=content, title="Jarvis Proactive Alert")

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
