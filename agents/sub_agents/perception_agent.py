"""
Perception Sub-Agent — screen analysis via vision, UI detection, and OCR.

Handles tasks like:
  - "How many tabs are open in Chrome?"
  - "What dialog is showing right now?"
  - "Find the search box on this page"
  - "Is the Save button visible?"

Reports structured screen state back to Jarvis.
"""

from __future__ import annotations

import logging
import re
import time

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register

logger = logging.getLogger(__name__)


class PerceptionAgent(SubAgentBase):
    name = "perception"
    description = (
        "Screen analysis: vision queries, UI element detection, OCR text "
        "extraction. Use for any task that needs to understand what is "
        "currently on the user's screen."
    )
    capabilities = [
        "vision_query",
        "detect_ui_elements",
        "read_screen",
        "screenshot",
        "focus_window",
        "get_active_window",
    ]

    def run(self, task: SubAgentTask) -> SubAgentResult:
        start = time.time()
        tool_log: list[dict] = []
        goal = task.goal
        ctx = task.context

        self._log.info(f"[{task.task_id}] Perception task: {goal[:100]}")

        # Check strategy memory for this task type
        task_type = self._classify_task(goal)
        failed_approaches = self._get_failed_approaches(task_type)
        successful_approaches = self._get_successful_approaches(task_type)

        # Phase 0 — focus target window if the goal names one
        target_window = ctx.get("window") or self._extract_window(goal)
        win_bounds = None
        if target_window:
            self._log.info(f"Focusing window: {target_window}")
            fw_result = self._tool("focus_window", title=target_window)
            time.sleep(0.3)
            # Extract window bounds for region cropping
            if fw_result.get("success"):
                data = fw_result.get("data", fw_result)
                if all(k in data for k in ("left", "top", "width", "height")):
                    win_bounds = {
                        "left": data["left"],
                        "top": data["top"],
                        "width": data["width"],
                        "height": data["height"],
                    }

        # Auto-crop to tab bar region for tab-counting goals
        is_tab_count = "tab" in goal.lower() and any(kw in goal.lower() for kw in ("count", "how many", "detect", "find"))
        if is_tab_count and win_bounds:
            region = {
                "left": win_bounds["left"] + 10,
                "top": win_bounds["top"] + 5,
                "width": win_bounds["width"] - 20,
                "height": 55,
            }
            self._log.info(f"Auto-cropping to tab bar region: {region}")
            ctx["region"] = region
        elif is_tab_count and not ctx.get("region"):
            # Fallback: use top-of-screen region for tab detection
            ctx["region"] = {"left": 0, "top": 0, "width": 1920, "height": 80}
            self._log.info(f"Using default tab bar region: {ctx['region']}")

        # Phase 1 — vision_query with gemma3 (best effort)
        # Skip vision if it has failed before for this task type
        skip_vision = "vision_query" in failed_approaches
        region = ctx.get("region")
        ok = False
        vision_answer = ""
        is_fallback = True
        if skip_vision:
            self._log.info(f"[{task.task_id}] Skipping vision_query — failed before for {task_type}")

        if not skip_vision:
            vq_params = {"question": goal}
            if region:
                vq_params["region"] = region
            ok, vq = self._tool_ok("vision_query", **vq_params)
            tool_log.append({"tool": "vision_query", **vq})

            vision_answer = vq.get("answer", "") if ok else ""
            is_fallback = vq.get("fallback", False) or "[Vision model unavailable" in vision_answer
            first_vq_elapsed = time.time() - start

            # Retry once on any failure (total failure or fallback) — but only if
            # the first call didn't already take >30s (likely a persistent cloud issue)
            if not (ok and not is_fallback and vision_answer.strip()) and first_vq_elapsed < 30:
                self._log.info(f"[{task.task_id}] vision_query retrying (first took {first_vq_elapsed:.0f}s)...")
                time.sleep(1)
                ok, vq = self._tool_ok("vision_query", **vq_params)
                tool_log.append({"tool": "vision_query", **vq})
                vision_answer = vq.get("answer", "") if ok else ""
                is_fallback = vq.get("fallback", False) or "[Vision model unavailable" in vision_answer
            elif not (ok and not is_fallback and vision_answer.strip()):
                self._log.info(f"[{task.task_id}] vision_query skipped retry (first took {first_vq_elapsed:.0f}s, likely persistent failure)")

            if ok and not is_fallback and vision_answer.strip():
                self._log.info(f"[{task.task_id}] vision_query succeeded")
                self._record_approach(task_type, "vision_query", True)
                return SubAgentResult(
                    success=True,
                    summary=vision_answer[:500],
                    data={
                        "source": "vision",
                        "answer": vision_answer,
                        "active_window": target_window or "",
                    },
                    tool_calls=tool_log,
                    elapsed_s=round(time.time() - start, 2),
                    agent_name=self.name,
                )
            else:
                # Record vision failure for strategy memory
                self._record_approach(task_type, "vision_query", False, "model fallback or empty answer")

        # Phase 2 — fallback to detect_ui_elements
        self._log.info(f"[{task.task_id}] vision unavailable, trying detect_ui_elements")
        du_params = {}
        search_text = ctx.get("search_text") or self._extract_search_term(goal)
        if search_text:
            du_params["search_text"] = search_text
        element_type = ctx.get("element_type")
        if element_type:
            du_params["element_type"] = element_type
        if region:
            du_params["region"] = region

        ok, du = self._tool_ok("detect_ui_elements", **du_params)
        tool_log.append({"tool": "detect_ui_elements", **du})
        elements = du.get("elements", []) if ok else []

        # Phase 3 — fallback to read_screen (OCR raw text)
        ocr_text = ""
        if not elements:
            self._log.info(f"[{task.task_id}] no elements found, trying read_screen OCR")
            ok, rs = self._tool_ok("read_screen")
            tool_log.append({"tool": "read_screen", **rs})
            ocr_text = rs.get("text", "")[:3000] if ok else ""

        # Phase 4 — build structured result
        elapsed = round(time.time() - start, 2)
        data = {
            "source": "elements" if elements else "ocr" if ocr_text else "none",
            "elements": elements,
            "ocr_text": ocr_text,
            "active_window": target_window or "",
            "vision_attempted": True,
            "vision_fallback": is_fallback,
        }

        if elements:
            element_texts = [e.get("text", "") for e in elements[:20]]
            summary = f"Found {len(elements)} UI element(s): {', '.join(element_texts)}"
            if search_text:
                matches = [e for e in elements if search_text.lower() in e.get("text", "").lower()]
                if matches:
                    summary += f" — {len(matches)} match(es) for '{search_text}'"
            success = True
            self._record_approach(task_type, "detect_ui_elements", True)
        elif ocr_text:
            preview = ocr_text[:200].replace("\n", " | ")
            summary = f"Screen text: {preview}"
            success = True
            self._record_approach(task_type, "read_screen", True)
        else:
            summary = "Unable to analyze screen content — all perception backends exhausted"
            success = False
            self._record_approach(task_type, "detect_ui_elements", False, "no elements found")

        return SubAgentResult(
            success=success,
            summary=summary,
            data=data,
            tool_calls=tool_log,
            elapsed_s=elapsed,
            agent_name=self.name,
        )

    @staticmethod
    def _extract_window(goal: str) -> str:
        patterns = [
            r"\b(?:in|on|of|inside)\s+(?:the\s+)?['\"]?([A-Z]\w+(?:[\s-][A-Z]\w+)*)['\"]?",
            r"(?:the\s+)?['\"]?([A-Z]\w+(?:[\s-][A-Z]\w+)*)['\"]?\s+(?:window|app|application|browser|editor|terminal)",
            r"([A-Z]\w+)\s+(?:window|tab|editor)\s+(?:is|shows|has|displays)",
            r"([A-Z]\w+)\s+(?:tabs?|tab\s+bar|tab\s+strip)",
        ]
        skip = {"the", "this", "that", "my", "your", "his", "her", "its", "our", "their", "a", "an", "on", "in", "of", "to", "for", "with", "at", "by", "from", "screen", "desktop", "display", "monitor"}
        for pat in patterns:
            m = re.search(pat, goal)
            if m:
                candidate = m.group(1).strip()
                if candidate.lower() not in skip and len(candidate) > 1:
                    return candidate
        return ""

    @staticmethod
    def _extract_search_term(goal: str) -> str:
        patterns = [
            r"(?:find|locate|search for|look for|spot|find me)\s+['\"]?(.+?)['\"]?(?:\s+in|\s+on|\s+at|\s*$)",
            r"['\"]?(.+?)['\"]?\s+(?:button|icon|tab|link|field|input|text|label)",
            r"(?:the|a|an)\s+['\"]?(.+?)['\"]?\s+(?:is|appears|shows|visible)",
        ]
        for pat in patterns:
            m = re.search(pat, goal, re.IGNORECASE)
            if m:
                return m.group(1).strip()[:60]
        return ""

    def _classify_task(self, goal: str) -> str:
        """Classify the perception task type for strategy memory."""
        goal_lower = goal.lower()
        if "tab" in goal_lower and any(kw in goal_lower for kw in ("count", "how many", "detect", "find")):
            return "chrome_tab_count"
        if "button" in goal_lower and ("click" in goal_lower or "find" in goal_lower):
            return "find_button"
        if "dialog" in goal_lower or "window" in goal_lower:
            return "detect_dialog"
        if "text" in goal_lower or "read" in goal_lower:
            return "read_text"
        return "general_perception"

    def _get_failed_approaches(self, task_type: str) -> list[str]:
        """Get approaches that failed before for this task type."""
        try:
            from memory import episodic
            return [s["approach"] for s in episodic.get_failed_strategies(task_type)]
        except Exception:
            return []

    def _get_successful_approaches(self, task_type: str) -> list[str]:
        """Get approaches that worked before for this task type."""
        try:
            from memory import episodic
            return [s["approach"] for s in episodic.get_successful_strategies(task_type)]
        except Exception:
            return []

    def _record_approach(self, task_type: str, approach: str, success: bool, feedback: str = ""):
        """Record whether an approach worked."""
        try:
            from memory import episodic
            episodic.record_strategy(task_type, approach, success, feedback)
        except Exception:
            pass


register(PerceptionAgent())
