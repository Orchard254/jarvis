"""
Advanced ReAct Agent with Tree of Thoughts Integration
Combines ReAct reasoning with ToT multi-path exploration for complex tasks.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from .tot_engine import TreeOfThoughtsEngine, ThoughtNode

logger = logging.getLogger(__name__)

class AdvancedReActAgent:
    """
    Enhanced ReAct agent that uses Tree of Thoughts for:
    1. Complex problem decomposition
    2. Multi-strategy evaluation before execution
    3. Backtracking when paths fail
    """
    
    def __init__(self, llm_interface, tool_executor, use_tot: bool = True):
        self.llm = llm_interface
        self.tools = tool_executor
        self.use_tot = use_tot
        self.tot_engine = TreeOfThoughtsEngine(llm_interface) if use_tot else None
        self.history = []
        
    async def process_task(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Main entry point for task processing."""
        if context is None:
            context = {}
            
        if self.use_tot and self._is_complex_task(task):
            return await self._solve_with_tot(task, context)
        else:
            return await self._solve_standard_react(task, context)
    
    def _is_complex_task(self, task: str) -> bool:
        """Heuristic to determine if a task needs ToT."""
        complexity_keywords = [
            "plan", "strategy", "optimize", "compare", "analyze", 
            "multi-step", "complex", "research", "investigate"
        ]
        return any(keyword in task.lower() for keyword in complexity_keywords)
    
    async def _solve_with_tot(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Solve using Tree of Thoughts approach."""
        print(f"🌳 Using Tree of Thoughts for complex task: {task}")
        
        # Run ToT solver
        solution_path = await self.tot_engine.solve(task, context)
        
        if not solution_path:
            return {
                "success": False,
                "message": "Could not find a viable solution path.",
                "method": "tot"
            }
        
        # Execute the best path found by ToT
        execution_result = await self._execute_solution_path(solution_path, context)
        
        return {
            "success": execution_result.get("success", False),
            "message": execution_result.get("result", ""),
            "method": "tot",
            "solution_path": solution_path,
            "steps_taken": execution_result.get("steps", [])
        }
    
    async def _solve_standard_react(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Standard ReAct loop (Thought -> Action -> Observation)."""
        print(f"⚡ Using standard ReAct for task: {task}")
        
        max_iterations = 10
        history = []
        
        for i in range(max_iterations):
            # Thought: Reason about current state
            thought_prompt = self._build_react_prompt(task, history, context)
            thought = await self.llm.generate_async(thought_prompt)
            
            # Parse action from thought
            action = self._parse_action(thought)
            
            if not action:
                # No action needed, we have an answer
                return {
                    "success": True,
                    "message": thought,
                    "method": "react",
                    "iterations": i + 1
                }
            
            # Action: Execute tool
            observation = await self.tools.execute(action["name"], action["args"])
            
            history.append({
                "thought": thought,
                "action": action,
                "observation": observation
            })
            
            # Check if task is complete
            if self._is_task_complete(task, history):
                return {
                    "success": True,
                    "message": self._synthesize_answer(task, history),
                    "method": "react",
                    "iterations": i + 1,
                    "history": history
                }
        
        return {
            "success": False,
            "message": "Max iterations reached without completing task.",
            "method": "react",
            "history": history
        }
    
    async def _execute_solution_path(self, solution_path: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the steps identified by ToT."""
        steps = solution_path.split("\n")
        executed_steps = []
        
        for step_line in steps:
            # Extract step description
            if ":" in step_line:
                step_desc = step_line.split(":", 1)[1].strip()
                # Remove score annotation if present
                if "(Score:" in step_desc:
                    step_desc = step_desc.split("(Score:")[0].strip()
                
                # Execute as tool call or logical step
                result = await self._execute_single_step(step_desc, context)
                executed_steps.append({
                    "step": step_desc,
                    "result": result
                })
                
                if not result.get("success", False):
                    return {
                        "success": False,
                        "result": f"Failed at step: {step_desc}",
                        "steps": executed_steps
                    }
        
        return {
            "success": True,
            "result": "All steps executed successfully.",
            "steps": executed_steps
        }
    
    async def _execute_single_step(self, step_desc: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single step from the solution path."""
        # Determine if this is a tool call or logical deduction
        # This is simplified - in production, parse more intelligently
        tool_match = self._parse_action(step_desc)
        
        if tool_match:
            return await self.tools.execute(tool_match["name"], tool_match["args"])
        else:
            # Logical step, just record it
            return {"success": True, "result": step_desc}
    
    def _build_react_prompt(self, task: str, history: List[Dict], context: Dict[str, Any]) -> str:
        """Build the ReAct prompt with history."""
        prompt = f"""Task: {task}

"""
        if history:
            prompt += "Previous interactions:\n"
            for i, h in enumerate(history):
                prompt += f"Step {i+1}:\n"
                prompt += f"Thought: {h['thought']}\n"
                prompt += f"Action: {h['action']}\n"
                prompt += f"Observation: {h['observation']}\n\n"
        
        prompt += """Think step by step. Use the format:
Thought: [your reasoning]
Action: [tool_name]
Action Input: {{"arg": "value"}}
Observation: [result from tool]
... (repeat as needed)
Final Answer: [your response]

If you have enough information to answer, provide the Final Answer."""
        
        return prompt
    
    def _parse_action(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse action from LLM response."""
        import re
        import json
        
        # Look for Action: pattern
        action_match = re.search(r'Action:\s*(\w+)', text)
        input_match = re.search(r'Action Input:\s*({.*})', text)
        
        if action_match:
            action_name = action_match.group(1)
            args = {}
            if input_match:
                try:
                    args = json.loads(input_match.group(1))
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse action input JSON: {e}")
                    args = {"raw": input_match.group(1)}
            
            return {"name": action_name, "args": args}
        
        return None
    
    def _is_task_complete(self, task: str, history: List[Dict]) -> bool:
        """Check if task appears complete based on history."""
        if not history:
            return False
        
        last_observation = history[-1].get("observation", "")
        return "error" not in str(last_observation).lower() and len(history) > 0
    
    def _synthesize_answer(self, task: str, history: List[Dict]) -> str:
        """Synthesize final answer from history."""
        if not history:
            return "Task completed."
        
        observations = [h.get("observation", "") for h in history]
        return f"Completed task: {task}\nResults: " + "\n".join(str(o) for o in observations[-3:])
