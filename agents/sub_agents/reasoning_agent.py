"""
Reasoning Agent — Tree of Thoughts Architecture.

Handles complex, multi-step queries by exploring multiple solution paths, 
evaluating them, and then picking the best path before committing to tool execution.
"""

from __future__ import annotations

import logging
import time

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register
from brain import ollama_client

logger = logging.getLogger(__name__)

class ReasoningAgent(SubAgentBase):
    name = "reasoning"
    description = (
        "Tree of Thoughts reasoning engine. Use this agent for complex tasks "
        "like deep research, complex coding, or architectural decisions that "
        "require exploring multiple paths before acting."
    )
    capabilities = [
        "brainstorm_paths",
        "evaluate_paths",
        "execute_best_path",
    ]

    def run(self, task: SubAgentTask) -> SubAgentResult:
        start = time.time()
        tool_log: list[dict] = []
        goal = task.goal
        
        self._log.info(f"[{task.task_id}] Reasoning task: {goal[:100]}")

        # Step 1: Brainstorm
        system_prompt = (
            "You are a Tree of Thoughts reasoner. Given a complex problem, "
            "propose 3 completely different high-level paths to solve it. "
            "Format your output clearly with Path 1:, Path 2:, Path 3:"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Problem: {goal}"}
        ]
        
        self._log.info("Brainstorming paths...")
        llm_result = ollama_client.chat_stream(messages=messages, temperature=0.7)
        paths_text = llm_result.get("content", "")
        tool_log.append({"tool": "brainstorm", "paths": paths_text})
        
        if not paths_text:
            return SubAgentResult(success=False, summary="Brainstorming failed.", data={}, agent_name=self.name)

        # Step 2: Evaluate
        eval_prompt = (
            "You are an expert evaluator. Review the following proposed paths "
            "to solve the user's problem. Evaluate each path's feasibility, "
            "safety, and efficiency. Then, explicitly state which path is the BEST."
        )
        messages = [
            {"role": "system", "content": eval_prompt},
            {"role": "user", "content": f"Problem: {goal}\n\nProposed Paths:\n{paths_text}"}
        ]
        
        self._log.info("Evaluating paths...")
        eval_result = ollama_client.chat_stream(messages=messages, temperature=0.3)
        evaluation_text = eval_result.get("content", "")
        tool_log.append({"tool": "evaluate", "evaluation": evaluation_text})

        elapsed = round(time.time() - start, 2)
        summary = f"Explored and evaluated multiple paths for '{goal[:50]}...'"
        
        return SubAgentResult(
            success=True,
            summary=summary,
            data={"paths": paths_text, "evaluation": evaluation_text},
            tool_calls=tool_log,
            elapsed_s=elapsed,
            agent_name=self.name,
        )

register(ReasoningAgent())
