"""
Interaction Sub-Agent — mouse and keyboard automation.

Handles tasks like:
  - "Click the Save button at (842, 317)"
  - "Type 'Hello' in the search box"
  - "Press Enter"
  - "Scroll down"

Receives already-resolved tool calls from the Director and executes them
through the safety-gated executor. No LLM, no reasoning.
"""

from __future__ import annotations

import logging
import time

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register

logger = logging.getLogger(__name__)

_TOOL_ALIASES = {
    "click": "click",
    "double_click": "double_click",
    "right_click": "right_click",
    "move": "move_mouse",
    "move_mouse": "move_mouse",
    "type": "type_text",
    "type_text": "type_text",
    "press": "press_keys",
    "press_keys": "press_keys",
    "key": "press_keys",
    "scroll": "scroll",
    "drag": "drag",
    "set_volume": "set_volume",
    "set_brightness": "set_brightness",
    "volume": "set_volume",
    "brightness": "set_brightness",
}


class InteractionAgent(SubAgentBase):
    name = "interaction"
    description = (
        "Mouse and keyboard automation: clicks, typing, scrolling, key presses, "
        "volume and brightness control. Use for any task that requires sending "
        "input to the operating system."
    )
    capabilities = [
        "click",
        "double_click",
        "right_click",
        "move_mouse",
        "type_text",
        "press_keys",
        "scroll",
        "drag",
        "set_volume",
        "set_brightness",
    ]

    def run(self, task: SubAgentTask) -> SubAgentResult:
        start = time.time()
        tool_log: list[dict] = []
        goal = task.goal
        ctx = task.context

        self._log.info(f"[{task.task_id}] Interaction task: {goal[:100]}")

        # Focus target window if mentioned in goal
        target_window = ctx.get("window") or self._extract_window(goal)
        if target_window:
            self._log.info(f"Focusing window: {target_window}")
            self._tool("focus_window", title=target_window)
            time.sleep(0.2)

        # Collect actions from context or derive from goal
        actions = ctx.get("actions", [])

        # Accept singular "action" key (from prompt examples) as fallback
        if not actions:
            single_action = ctx.get("action")
            if single_action and isinstance(single_action, str):
                # {"action": "click", "x": 842, "y": 317} → normalize to actions list
                params = {k: v for k, v in ctx.items() if k not in ("action", "actions", "window")}
                actions = [{"tool": single_action, "params": params}]
            elif single_action and isinstance(single_action, dict):
                # {"action": {"tool": "click", "params": {"x": 842, "y": 317}}}
                actions = [single_action]

        if not actions:
            action = self._goal_to_action(goal)
            if action:
                actions = [action]

        if not actions:
            return SubAgentResult(
                success=False,
                summary="No actions provided. Pass an 'actions' list in context with {tool, params} per step.",
                data={},
                agent_name=self.name,
            )

        results: list[dict] = []
        all_success = True

        for i, step in enumerate(actions):
            tool_name = self._resolve_tool(step.get("tool") or step.get("action", ""))
            params = step.get("params", {})

            if not tool_name:
                self._log.warning(f"[{task.task_id}] step {i}: unknown tool '{step.get('tool')}'")
                results.append({"step_index": i, "tool": step.get("tool"), "success": False, "error": "Unknown tool"})
                all_success = False
                continue

            # Coerce list-type keys to string for press_keys (common LLM mistake)
            if tool_name == "press_keys" and isinstance(params.get("keys"), list):
                params = dict(params)
                params["keys"] = "+".join(params["keys"])

            # Execute the tool call through safety executor
            self._log.info(f"[{task.task_id}] step {i}: {tool_name}({list(params.keys())})")
            result = self._execute(tool_name, params)
            tool_log.append({"tool": tool_name, "params": params, **result})
            success = result.get("success", False)

            results.append({
                "step_index": i,
                "tool": tool_name,
                "success": success,
                "params": params,
                "error": result.get("error", "") if not success else "",
            })

            if not success:
                all_success = False
                self._log.warning(f"[{task.task_id}] step {i} {tool_name} failed: {result.get('error', '?')[:100]}")

        elapsed = round(time.time() - start, 2)
        ok_count = sum(1 for r in results if r["success"])
        total = len(results)
        summary = f"Executed {ok_count}/{total} interaction action(s) in {elapsed}s"

        # Record strategy outcome for memory
        task_type = self._classify_task(goal)
        self._record_approach(task_type, "interaction", all_success, summary if not all_success else "")

        if not all_success:
            failed = [r for r in results if not r["success"]]
            summary += "; failures: " + "; ".join(f"step {r['step_index']} {r['tool']}: {r['error'][:80]}" for r in failed[:2])

        return SubAgentResult(
            success=all_success,
            summary=summary,
            data={"results": results},
            tool_calls=tool_log,
            elapsed_s=elapsed,
            agent_name=self.name,
        )

    @staticmethod
    def _resolve_tool(name: str) -> str:
        return _TOOL_ALIASES.get(name, "")

    @staticmethod
    def _goal_to_action(goal: str) -> dict | None:
        goal_lower = goal.lower().strip()
        # Support: "click at (x,y)", "click (x,y)", "click something at (x,y)", "click on (x,y)"
        click_match = __import__("re").search(r"click\b.*?\(?(\d+)\s*,\s*(\d+)\)?", goal_lower)
        if click_match:
            return {"tool": "click", "params": {"x": int(click_match.group(1)), "y": int(click_match.group(2))}}
        type_match = __import__("re").search(r"type\s+['\"](.+?)['\"]", goal_lower)
        if type_match:
            return {"tool": "type_text", "params": {"text": type_match.group(1)}}
        press_match = __import__("re").search(r"press\s+(.+?)(?:\s+key|$)", goal_lower)
        if press_match:
            return {"tool": "press_keys", "params": {"keys": press_match.group(1).strip().title()}}
        return None

    @staticmethod
    def _extract_window(goal: str) -> str:
        """Extract window name from goal string."""
        import re
        patterns = [
            r"\b(?:in|on|of|inside)\s+(?:the\s+)?['\"]?([A-Z]\w+(?:[\s-][A-Z]\w+)*)['\"]?",
            r"(?:the\s+)?['\"]?([A-Z]\w+(?:[\s-][A-Z]\w+)*)['\"]?\s+(?:window|app|application|browser|editor|terminal|dialog)",
        ]
        skip = {"the", "this", "that", "my", "your", "screen", "desktop", "display"}
        for pat in patterns:
            m = re.search(pat, goal)
            if m:
                candidate = m.group(1).strip()
                if candidate.lower() not in skip and len(candidate) > 1:
                    return candidate
        return ""

    def _classify_task(self, goal: str) -> str:
        """Classify the interaction task type for strategy memory."""
        goal_lower = goal.lower()
        if "click" in goal_lower:
            return "click"
        if "type" in goal_lower:
            return "type_text"
        if "press" in goal_lower or "key" in goal_lower:
            return "press_keys"
        if "scroll" in goal_lower:
            return "scroll"
        return "general_interaction"

    def _record_approach(self, task_type: str, approach: str, success: bool, feedback: str = ""):
        """Record whether an approach worked."""
        try:
            from memory import episodic
            episodic.record_strategy(task_type, approach, success, feedback)
        except Exception:
            pass


register(InteractionAgent())
