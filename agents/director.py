"""
Jarvis Agent — Conversation + Strategic Planning with Deep Reasoning.

Handles:
  - Deep reasoning cycle BEFORE any tool consideration
  - Natural conversation and multi-perspective analysis
  - Tool necessity assessment (can this be solved by reasoning alone?)
  - Strategic planning with minimal tool usage
  - Memory/context integration

Does NOT call tools directly — that's the Execution Agent's job.

REASONING-FIRST PHILOSOPHY:
  1. Think deeply before acting
  2. Complete full reasoning cycles before tool consideration
  3. Minimize tool calls — use reasoning for logical tasks
  4. Batch necessary tools instead of sequential loops
"""

import json
import logging
from typing import Optional, Dict, Any, List

from brain import ollama_client
from brain.context_manager import prune_history
from brain.prompt_builder import build_system_prompt
from settings import ITERATION_CAPS, MAX_CONTEXT_TOKENS, TOOL_LOOP_HISTORY_MESSAGES

logger = logging.getLogger(__name__)


class ReasoningTrace:
    """Captures the complete reasoning process before any tool use."""
    
    def __init__(
        self,
        problem_decomposition: List[str],
        perspectives: List[Dict[str, str]],
        hypotheses: List[Dict[str, Any]],
        validation_results: Dict[str, Any],
        solution_plan: List[Dict[str, Any]],
        tool_necessity: str,
        confidence_score: float,
        raw_reasoning: str
    ):
        self.problem_decomposition = problem_decomposition
        self.perspectives = perspectives
        self.hypotheses = hypotheses
        self.validation_results = validation_results
        self.solution_plan = solution_plan
        self.tool_necessity = tool_necessity  # 'PURE_REASONING', 'COMPUTATIONAL_ASSIST', 'EXTERNAL_DATA_REQUIRED', 'EXECUTION_REQUIRED'
        self.confidence_score = confidence_score
        self.raw_reasoning = raw_reasoning
    
    def to_dict(self) -> dict:
        return {
            'decomposition': self.problem_decomposition,
            'perspectives': self.perspectives,
            'hypotheses': self.hypotheses,
            'validation': self.validation_results,
            'plan': self.solution_plan,
            'tool_necessity': self.tool_necessity,
            'confidence': self.confidence_score,
            'raw_trace': self.raw_reasoning
        }


class JarvisAgent:
    """Conversation + high-level planning agent with deep reasoning (the brain)."""

    # Tool necessity categories
    PURE_REASONING = 'PURE_REASONING'
    COMPUTATIONAL_ASSIST = 'COMPUTATIONAL_ASSIST'
    EXTERNAL_DATA_REQUIRED = 'EXTERNAL_DATA_REQUIRED'
    EXECUTION_REQUIRED = 'EXECUTION_REQUIRED'

    def process(
        self,
        user_input: str,
        history: list[dict],
        memory_context: str = "",
        mode: str = "interactive_cloud",
        intent_handler=None,
    ) -> dict:
        """
        Process user input through Jarvis with reasoning-first approach.

        Args:
            user_input: The user's message
            history: Conversation history
            memory_context: Memory summary
            mode: Agent mode (iteration cap)
            intent_handler: Called when Jarvis outputs INTENT.
                           Receives (intent_dict) -> returns response string.

        Returns:
            dict with response, success, iterations, tool_calls, reasoning_trace
        """
        cap = ITERATION_CAPS.get(mode, 4)
        messages = self._build_messages(user_input, history, memory_context)
        tool_log = []
        reasoning_trace = None

        for iteration in range(1, cap + 1):
            if len(json.dumps(messages)) > (MAX_CONTEXT_TOKENS * 4):
                messages = prune_history(messages)

            # Phase 1: Deep Reasoning (iterations 1-2 focus on reasoning, no tools)
            # Use higher reasoning effort early to ensure thorough thinking
            llm_result = ollama_client.chat(
                messages=messages,
                tools=None,  # No tools in reasoning phase
                temperature=0.3,
                reasoning_effort="high" if iteration <= 2 else "medium",
            )

            content = (llm_result.get("content") or "").strip()

            if not content and iteration >= cap:
                return {
                    "response": "I'm not sure how to help with that.",
                    "success": True,
                    "iterations": iteration,
                    "tool_calls": tool_log,
                    "reasoning_trace": reasoning_trace,
                }

            # Phase 2: Parse and assess tool necessity
            intent = self._parse_intent(content)

            if intent and intent_handler:
                # Assess if this truly needs tool execution or can be reasoned
                tool_category = self._assess_tool_necessity(intent, content)
                
                # If pure reasoning, respond directly without tool execution
                if tool_category == self.PURE_REASONING:
                    # Extract reasoning from content and respond
                    reasoning_response = self._extract_reasoning_response(content)
                    if reasoning_response:
                        return {
                            "response": reasoning_response,
                            "success": True,
                            "iterations": iteration,
                            "tool_calls": tool_log,
                            "reasoning_trace": self._build_reasoning_trace(content, intent, tool_category),
                        }
                
                # Execute via intent handler for tool-requiring actions
                messages.append({"role": "assistant", "content": content})
                exec_result = intent_handler(intent)
                tool_log.append({
                    "action": intent.get("action", "?"),
                    "target": intent.get("target", ""),
                    # Check for both "failed" and "partial" outcomes.
                    # Previously only "failed" was checked, so partial failures
                    # (e.g. "Overall: partial") were silently treated as success.
                    "status": "failed" if ("failed" in exec_result.lower() or "partial" in exec_result.lower()) else "ok",
                    "error": exec_result if ("failed" in exec_result.lower() or "partial" in exec_result.lower()) else None,
                })
                messages.append({"role": "user", "content": exec_result})
                
                # Build reasoning trace for tracking
                if not reasoning_trace:
                    reasoning_trace = self._build_reasoning_trace(content, intent, tool_category)
                continue

            # Chat response — Jarvis completed via reasoning alone
            if content:
                # Try to extract structured reasoning trace from content
                reasoning_trace = self._try_extract_reasoning_trace(content)
                
                return {
                    "response": content,
                    "success": True,
                    "iterations": iteration,
                    "tool_calls": tool_log,
                    "reasoning_trace": reasoning_trace,
                }

        return {
            "response": "Task complete.",
            "success": True,
            "iterations": cap,
            "tool_calls": tool_log,
            "reasoning_trace": reasoning_trace,
        }

    def _assess_tool_necessity(self, intent: dict, content: str) -> str:
        """
        Assess whether an intent truly requires tool execution or can be handled by reasoning.
        
        Categories:
        - PURE_REASONING: Logical analysis, code review, explanations, planning
        - COMPUTATIONAL_ASSIST: Complex calculations, data processing
        - EXTERNAL_DATA_REQUIRED: Real-time info, file system, API calls
        - EXECUTION_REQUIRED: System commands, code execution, deployments
        """
        action = intent.get("action", "").lower()
        target = intent.get("target", "").lower()
        
        # Pure reasoning tasks - no tools needed
        reasoning_keywords = [
            'explain', 'analyze', 'review', 'compare', 'suggest', 'recommend',
            'why', 'how', 'what if', 'pros', 'cons', 'benefits', 'risks'
        ]
        
        # Check if the content suggests reasoning-only task
        content_lower = content.lower()
        if any(kw in content_lower for kw in reasoning_keywords):
            # Verify it's not asking for actual execution
            if not any(a in action for a in ['open', 'close', 'execute', 'run', 'click', 'type']):
                return self.PURE_REASONING
        
        # Computational tasks
        computational_actions = ['calculate', 'compute', 'convert', 'count']
        if any(a in action for a in computational_actions):
            return self.COMPUTATIONAL_ASSIST
        
        # External data required
        external_actions = ['read_file', 'write_file', 'search_web', 'get_info', 
                          'screenshot', 'read_screen', 'list_apps']
        if any(a in action for a in external_actions):
            return self.EXTERNAL_DATA_REQUIRED
        
        # Execution required (default for most actions)
        return self.EXECUTION_REQUIRED

    def _extract_reasoning_response(self, content: str) -> str | None:
        """Extract clean reasoning response from LLM output."""
        # Remove INTENT markers if present
        if content.startswith("INTENT"):
            return None  # This is an intent, not pure reasoning
        
        # Return the content as-is if it's reasoning
        return content if content.strip() else None

    def _build_reasoning_trace(self, content: str, intent: dict, category: str) -> ReasoningTrace:
        """Build a structured reasoning trace from the LLM response."""
        return ReasoningTrace(
            problem_decomposition=[intent.get("action", "unknown")],
            perspectives=[{"source": "llm", "content": content[:500]}],
            hypotheses=[{"action": intent}],
            validation_results={"category": category},
            solution_plan=[intent],
            tool_necessity=category,
            confidence_score=0.85 if category == self.PURE_REASONING else 0.70,
            raw_reasoning=content
        )

    def _try_extract_reasoning_trace(self, content: str) -> ReasoningTrace | None:
        """Try to extract a reasoning trace from conversational content."""
        # Simple heuristic: if no INTENT marker, treat as reasoning
        if "INTENT" not in content and content.strip():
            return ReasoningTrace(
                problem_decomposition=["conversational_response"],
                perspectives=[{"type": "direct_answer"}],
                hypotheses=[],
                validation_results={"method": "reasoning_only"},
                solution_plan=[],
                tool_necessity=self.PURE_REASONING,
                confidence_score=0.90,
                raw_reasoning=content
            )
        return None

    def _build_messages(self, user_input, history, memory_context):
        messages = [{"role": "system", "content": build_system_prompt()}]
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        messages.extend(history[-TOOL_LOOP_HISTORY_MESSAGES:])
        messages.append({"role": "user", "content": user_input})
        return messages

    def _parse_intent(self, content: str) -> dict | None:
        """Parse INTENT JSON from Jarvis's response.

        Handles two formats:
          1. Canonical:  INTENT {"action": "open", ...}
          2. Bare JSON:  {"action": "open", ...}   (LLM skipped the prefix)

        Format 2 is a fallback — the model sometimes outputs raw JSON without
        the INTENT keyword. Without this fallback the JSON gets returned as a
        chat response and nothing executes.
        """
        stripped = content.strip() if content else ""
        if not stripped:
            return None

        decoder = json.JSONDecoder()

        # Format 1: canonical INTENT prefix
        if stripped.startswith("INTENT"):
            try:
                json_str = stripped[len("INTENT"):].strip()
                obj, _ = decoder.raw_decode(json_str)
                if isinstance(obj, dict) and "action" in obj:
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

        # Format 2: bare JSON object with an "action" key (no prefix)
        if stripped.startswith("{"):
            try:
                obj, _ = decoder.raw_decode(stripped)
                if isinstance(obj, dict) and "action" in obj:
                    logger.debug("_parse_intent: matched bare JSON intent (no INTENT prefix)")
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

        return None
