"""
Execution Agent — Operations. Plans and executes tool sequences via LLM.
"""

import json
import logging

from brain import ollama_client
from brain.prompt_builder import build_executor_prompt
from core.agent_registry import AgentRegistry
from tools import TOOL_SCHEMAS

logger = logging.getLogger(__name__)


class ExecutionAgent:
    """Operations — plans tool calls via LLM, executes them, reports results."""

    def __init__(self, execute_fn, verify_fn):
        self._execute = execute_fn
        self._verify = verify_fn
        spec = AgentRegistry.get("executor")
        self._model = spec.model if spec else "nemotron-3-nano:30b-cloud"
        self._temperature = spec.temperature if spec else 0.1

    def execute_task(self, task: str) -> list[dict]:
        messages = [
            {"role": "system", "content": build_executor_prompt()},
            {"role": "user", "content": task},
        ]

        llm_result = ollama_client.chat(
            messages=messages,
            tools=TOOL_SCHEMAS,
            model=self._model,
            temperature=self._temperature,
        )

        tool_calls = llm_result.get("tool_calls")
        content = (llm_result.get("content") or "").strip()

        if not tool_calls:
            return [{"tool": "none", "success": True, "message": content or "Done."}]

        results = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not tool_name:
                continue

            result = self._execute(tool_name, args)
            verification = self._verify(tool_name, result, "")
            results.append({
                "tool": tool_name,
                "args": args,
                "success": result.get("success", False),
                "error": result.get("error"),
                "message": result.get("message") or result.get("output") or "",
                "verification": verification.get("status", ""),
            })

        return results
