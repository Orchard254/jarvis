"""
Director Agent — CEO. Conversational frontend. Delegates actions to Execution.
"""

import json
import logging

from brain import ollama_client
from brain.prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)

DELEGATE_TOOL = {
    "type": "function",
    "function": {
        "name": "delegate",
        "description": "Pass a task to the execution agent when the user needs something done on the computer — opening apps, typing, searching, clicking, checking system info, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task to execute. Be specific about what the user wants."
                }
            },
            "required": ["task"],
        },
    },
}

GET_SYSTEM_INFO_TOOL = {
    "type": "function",
    "function": {
        "name": "get_system_info",
        "description": "Get live information about the system — how many tools are available, what domains they cover, and what agents exist.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}


class JarvisAgent:
    """Director — conversational CEO. Chats or delegates to Execution."""

    def process(
        self,
        user_input: str,
        history: list[dict],
    ) -> dict:
        messages = [{"role": "system", "content": build_system_prompt()}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        llm_result = ollama_client.chat(
            messages=messages,
            tools=[DELEGATE_TOOL, GET_SYSTEM_INFO_TOOL],
            temperature=0.3,
        )

        content = (llm_result.get("content") or "").strip()
        tool_calls = llm_result.get("tool_calls")

        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")

                if name == "get_system_info":
                    from core.agent_registry import AgentRegistry
                    info = AgentRegistry.get_info()
                    lines = [
                        f"The system has {info['tool_count']} tools across these domains:",
                        info["tool_domains"],
                        "",
                        f"Agents ({info['agent_count']}):",
                        info["agent_info"],
                    ]
                    return {"response": "\n".join(lines), "delegate_task": "", "success": True}

                if name == "delegate":
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    task = args.get("task", "")
                    if task:
                        return {"response": content, "delegate_task": task, "success": True}

        return {"response": content or "I'm not sure how to help with that.", "success": True}

    def summarize(self, task: str, exec_results: list[dict], history: list[dict]) -> str:
        messages = [{"role": "system", "content": build_system_prompt()}]
        messages.extend(history)
        messages.append({
            "role": "user",
            "content": (
                f"I delegated this task to my operations team: '{task}'. "
                f"Here are the results:\n{json.dumps(exec_results, indent=2)}\n"
                "Summarize what happened for the user in natural language. "
                "Be honest — if a tool failed, say exactly what went wrong. "
                "Do not pretend failures are successes."
            ),
        })

        result = ollama_client.chat(messages=messages, tools=None, temperature=0.3)
        return (result.get("content") or "").strip() or "Done."
