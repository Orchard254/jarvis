"""
Planner Agent - Tier 3 Multi-Agent System

Breaks complex goals into dependency-aware steps.
Analyzes task requirements and creates executable plans.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from brain.ollama_client import chat
from brain.prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    Responsible for decomposing complex goals into ordered, dependency-aware steps.
    
    Capabilities:
    - Task complexity analysis
    - Step decomposition with dependency tracking
    - Resource requirement identification
    - Plan validation and optimization
    """
    
    def __init__(self, shared_context=None):
        self._shared_context = shared_context
        self._name = "PlannerAgent"
        
    def analyze_task(self, goal: str) -> Dict[str, any]:
        """
        Analyze a task to determine complexity and requirements.
        
        Returns:
            Dict with complexity_score, estimated_steps, required_resources, is_simple
        """
        # Simple heuristic analysis first
        simple_indicators = [
            "open", "close", "list", "show", "find", "search",
            "what", "when", "where", "who", "set", "get", "check"
        ]
        
        goal_lower = goal.lower()
        is_simple = any(
            goal_lower.startswith(ind) or f" {ind} " in goal_lower 
            for ind in simple_indicators
        ) and len(goal.split()) < 15
        
        # Check for compound tasks (multiple actions)
        compound_connectors = [" then ", " after that ", " and then ", " followed by "]
        is_compound = any(conn in goal_lower for conn in compound_connectors)
        
        # Estimate steps based on complexity markers
        if is_simple and not is_compound:
            return {
                "complexity_score": 1,
                "estimated_steps": 1,
                "required_resources": [],
                "is_simple": True,
                "recommendation": "direct_execution"
            }
        
        # Use LLM for complex task analysis
        try:
            messages = [
                {"role": "system", "content": build_system_prompt()},
                {"role": "system", "content": self._get_analyzer_instruction()},
                {"role": "user", "content": goal}
            ]
            
            result = chat(messages=messages, tools=[], temperature=0.1)
            content = (result.get("content") or "").strip()
            
            return self._parse_analysis(content, goal)
            
        except Exception as e:
            logger.warning(f"PlannerAgent analysis failed: {e}")
            return {
                "complexity_score": 2,
                "estimated_steps": 2,
                "required_resources": [],
                "is_simple": False,
                "recommendation": "decompose"
            }
    
    def decompose(self, goal: str, context: Optional[Dict] = None) -> List[str]:
        """
        Break down a complex goal into ordered steps.
        
        Args:
            goal: The high-level goal to decompose
            context: Optional context from previous agent work
            
        Returns:
            List of step descriptions, each actionable by Coder/Executor agents
        """
        if self._shared_context:
            self._shared_context.set_agent_state(self._name, {
                "action": "decompose",
                "goal": goal
            })
        
        try:
            messages = [
                {"role": "system", "content": build_system_prompt()},
                {"role": "system", "content": self._get_decomposer_instruction()},
            ]
            
            # Add context if available
            if context:
                ctx_str = f"Context from previous work:\n{context}\n\n"
                messages.append({"role": "system", "content": ctx_str})
            
            messages.append({"role": "user", "content": goal})
            
            result = chat(messages=messages, tools=[], temperature=0.2)
            content = (result.get("content") or "").strip()
            
            steps = self._parse_steps(content)
            
            if self._shared_context:
                self._shared_context.record_execution(
                    self._name, "decompose", 
                    {"steps": steps}, 
                    success=len(steps) > 0
                )
            
            logger.info(f"PlannerAgent decomposed '{goal[:50]}...' into {len(steps)} steps")
            return steps
            
        except Exception as e:
            logger.error(f"PlannerAgent decomposition failed: {e}")
            return [goal]  # Fallback: treat whole goal as single step
    
    def validate_plan(self, steps: List[str], goal: str) -> Tuple[bool, str]:
        """
        Validate that a plan will achieve the goal.
        
        Returns:
            (is_valid, reason) tuple
        """
        if not steps:
            return False, "Empty plan"
        
        if len(steps) > 10:
            return False, "Plan too complex (>10 steps)"
        
        # Check for dependency ordering issues
        # (simplified check - full validation would need semantic analysis)
        step_text = " ".join(steps).lower()
        
        # Check for obvious issues
        if "before" in step_text or "after" in step_text:
            # Verify temporal ordering makes sense
            pass
        
        # Each step should be actionable
        for i, step in enumerate(steps):
            if len(step.strip()) < 5:
                return False, f"Step {i+1} too vague"
        
        return True, "Plan validated"
    
    def optimize_plan(self, steps: List[str]) -> List[str]:
        """
        Optimize a plan by merging redundant steps and improving efficiency.
        """
        if len(steps) <= 1:
            return steps
        
        optimized = []
        prev_step = ""
        
        for step in steps:
            step = step.strip()
            # Skip duplicate consecutive steps
            if step.lower() == prev_step.lower():
                continue
            # Merge very short related steps
            if len(step) < 20 and prev_step and len(prev_step) < 50:
                optimized[-1] = f"{prev_step}; {step}"
            else:
                optimized.append(step)
            prev_step = step
        
        return optimized if optimized else steps
    
    def _get_analyzer_instruction(self) -> str:
        return (
            "You are a task analysis expert. Analyze the user's request and determine:\n"
            "1. Complexity (1=simple single action, 5=complex multi-step workflow)\n"
            "2. Estimated number of steps needed\n"
            "3. Required resources/tools\n"
            "4. Whether it can be done directly or needs decomposition\n"
            "\n"
            "Respond in this exact format:\n"
            "COMPLEXITY: <number 1-5>\n"
            "STEPS: <estimated count>\n"
            "RESOURCES: <comma-separated list or 'none'>\n"
            "RECOMMENDATION: <'direct_execution' or 'decompose'>\n"
        )
    
    def _get_decomposer_instruction(self) -> str:
        return (
            "You are an expert task planner for an AI desktop agent.\n"
            "Break down the user's goal into clear, actionable steps.\n"
            "\n"
            "Rules:\n"
            "- Each step must be independently executable\n"
            "- Order matters: step N can use output from step N-1\n"
            "- Maximum 8 steps per plan\n"
            "- Be specific about what each step should accomplish\n"
            "- Do NOT include verification steps (the system handles that)\n"
            "- Do NOT include greetings or conversational filler\n"
            "\n"
            "Format: Numbered list like:\n"
            "1. First step description\n"
            "2. Second step description\n"
            "..."
        )
    
    def _parse_analysis(self, content: str, goal: str) -> Dict:
        """Parse LLM analysis response."""
        result = {
            "complexity_score": 2,
            "estimated_steps": 2,
            "required_resources": [],
            "is_simple": False,
            "recommendation": "decompose"
        }
        
        for line in content.split("\n"):
            line = line.strip().upper()
            if line.startswith("COMPLEXITY:"):
                try:
                    result["complexity_score"] = int(line.split(":")[1].strip())
                except (ValueError, TypeError, IndexError):
                    pass
            elif line.startswith("STEPS:"):
                try:
                    result["estimated_steps"] = int(line.split(":")[1].strip())
                except (ValueError, TypeError, IndexError):
                    pass
            elif line.startswith("RESOURCES:"):
                res = line.split(":")[1].strip()
                if res != "NONE":
                    result["required_resources"] = [r.strip() for r in res.split(",")]
            elif line.startswith("RECOMMENDATION:"):
                rec = line.split(":")[1].strip().lower()
                result["recommendation"] = rec
                result["is_simple"] = (rec == "direct_execution")
        
        return result
    
    def _parse_steps(self, content: str) -> List[str]:
        """Parse numbered steps from LLM response."""
        steps = []
        for line in content.split("\n"):
            line = line.strip()
            match = re.match(r"^(\d+)[.)]\s*(.+)", line)
            if match:
                steps.append(match.group(2).strip())
        return steps
