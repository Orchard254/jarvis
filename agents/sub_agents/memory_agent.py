"""
Memory Sub-Agent — persistent preference and context storage.

Handles tasks like:
  - "Remember I prefer dark mode"
  - "What theme do I prefer?"
  - "Search my preferences for 'volume'"
  - "Forget my weather preference"

Routes operations to the memory_manager through the safety executor.
No LLM, no reasoning.
"""

from __future__ import annotations

import logging
import time

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register

logger = logging.getLogger(__name__)


class MemoryAgent(SubAgentBase):
    name = "memory"
    description = (
        "Persistent memory: store and retrieve user preferences, "
        "frequent commands, and cross-session context. Use for any "
        "task that needs to remember or recall user-specific information."
    )
    capabilities = [
        "store_memory",
        "retrieve_memory",
        "search_memory",
        "forget_memory",
    ]

    def run(self, task: SubAgentTask) -> SubAgentResult:
        start = time.time()
        tool_log: list[dict] = []
        goal = task.goal
        ctx = task.context

        self._log.info(f"[{task.task_id}] Memory task: {goal[:100]}")

        operation = ctx.get("operation") or self._infer_operation(goal)
        key = ctx.get("key", "")
        value = ctx.get("value", "")
        query = ctx.get("query") or goal

        if not operation:
            return SubAgentResult(
                success=False,
                summary="No memory operation specified. Pass an 'operation' in context: store, retrieve, search, forget, or context.",
                data={},
                agent_name=self.name,
            )

        records: list[dict] = []
        errors: list[str] = []
        summary = ""

        if operation == "store":
            if not key or not value:
                kv = self._parse_kv(goal)
                key = kv.get("key", key)
                value = kv.get("value", value)
            if key and value:
                ok, result = self._tool_ok("store_memory", key=key, value=value, source="user")
                tool_log.append({"tool": "store_memory", "key": key, **result})
                if ok:
                    summary = f"Stored: {key} = {value}"
                    records.append({"key": key, "value": value, "operation": "store"})
                else:
                    errors.append(f"store_memory: {result.get('error', '?')}")
            else:
                errors.append("Need both 'key' and 'value' to store memory")

        elif operation == "retrieve":
            if not key:
                key = self._extract_key(goal)
            if key:
                ok, result = self._tool_ok("retrieve_memory", key=key)
                tool_log.append({"tool": "retrieve_memory", "key": key, **result})
                if ok:
                    val = result.get("value", "")
                    records.append({"key": key, "value": val, "operation": "retrieve"})
                    summary = f"{key}: {val}" if val else f"No value stored for '{key}'"
                else:
                    errors.append(f"retrieve_memory: {result.get('error', '?')}")
            else:
                errors.append("Need 'key' to retrieve memory")

        elif operation == "search":
            ok, result = self._tool_ok("search_memory", query=query)
            tool_log.append({"tool": "search_memory", **result})
            if ok:
                records = result.get("records", [])
                summary = f"Found {len(records)} memory record(s)" if records else f"No results for '{query}'"
            else:
                errors.append(f"search_memory: {result.get('error', '?')}")

        elif operation == "forget":
            if not key:
                key = self._extract_key(goal)
            if key:
                ok, result = self._tool_ok("forget_memory", key=key)
                tool_log.append({"tool": "forget_memory", "key": key, **result})
                if ok:
                    summary = f"Forgot: {key}"
                    records.append({"key": key, "operation": "forget"})
                else:
                    errors.append(f"forget_memory: {result.get('error', '?')}")
            else:
                errors.append("Need 'key' to forget memory")

        elif operation == "context":
            ok, result = self._tool_ok("retrieve_memory", key="__context_summary")
            tool_log.append({"tool": "retrieve_memory", "key": "__context_summary", **result})
            if ok:
                summary = result.get("value", "No context summary available")
                records.append({"operation": "context", "summary": summary})
            else:
                summary = "Context summary unavailable"

        elapsed = round(time.time() - start, 2)
        success = not errors or bool(records)

        if not summary:
            if records:
                summary = f"Memory operation '{operation}' completed"
            elif errors:
                summary = "; ".join(errors[:2])

        return SubAgentResult(
            success=success,
            summary=summary,
            data={"operation": operation, "records": records, "errors": errors},
            tool_calls=tool_log,
            elapsed_s=elapsed,
            agent_name=self.name,
        )

    @staticmethod
    def _infer_operation(goal: str) -> str:
        g = goal.lower()
        if any(w in g for w in ("remember", "store", "save", "set ", "add ")):
            return "store"
        if any(w in g for w in ("retrieve", "get ", "what", "recall", "fetch")):
            return "retrieve"
        if any(w in g for w in ("search", "find", "look up")):
            return "search"
        if any(w in g for w in ("forget", "delete", "remove", "erase", "clear")):
            return "forget"
        if any(w in g for w in ("context", "summary", "preferences")):
            return "context"
        return ""

    @staticmethod
    def _parse_kv(goal: str) -> dict:
        import re
        patterns = [
            r"(?:remember|store|save|set)\s+(?:that\s+)?(?:my\s+)?(.+?)\s+(?:is|are|as|to be)\s+(.+)",
            r"(?:i\s+(?:prefer|like|use)\s+)(.+?)(?:\s+(?:theme|mode|setting|color|layout))?\s*$",
        ]
        for pat in patterns:
            m = re.search(pat, goal, re.IGNORECASE)
            if m:
                key = m.group(1).strip().lower().replace(" ", "_")[:50]
                value = m.group(2).strip() if m.lastindex >= 2 else "true"
                return {"key": key, "value": value}
        return {}

    @staticmethod
    def _extract_key(goal: str) -> str:
        import re
        m = re.search(r"(?:my\s+)?(.+?)\s+(?:preference|setting|theme|key)", goal, re.IGNORECASE)
        if m:
            return m.group(1).strip().lower().replace(" ", "_")[:50]
        m = re.search(r"(?:key|preference)\s+['\"]?(.+?)['\"]?(?:\s|$)", goal, re.IGNORECASE)
        if m:
            return m.group(1).strip().lower().replace(" ", "_")[:50]
        return ""


register(MemoryAgent())
