"""
ReAct Agent Engine: Reason → Act → Observe → Repeat
Handles autonomous multi-step tool chaining with self-correction.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class ReActAgent:
    def __init__(self, brain, tool_registry, max_iterations: int = 15):
        self.brain = brain
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Builds a prompt that enforces ReAct behavior and lists available tools."""
        tools_desc = []
        for name, info in self.tool_registry.get_all_tools().items():
            args = ", ".join([f"{k}: {v}" for k, v in info.get('arguments', {}).items()])
            tools_desc.append(f"- {name}({args}): {info.get('description', 'No description')}")
        
        tools_list = "\n".join(tools_desc)
        
        return f"""You are an autonomous agent controlling a Windows PC. 
You must solve tasks using the ReAct pattern: Thought → Action → Observation → Repeat.

**AVAILABLE TOOLS:**
{tools_list}

**RULES:**
1. Output ONLY ONE tool call at a time.
2. Wait for the observation result before calling the next tool.
3. If a tool fails, analyze the error and try a different approach or fix the arguments.
4. If you don't have a specific tool, compose existing tools to achieve the goal.
5. When the task is complete, respond directly to the user with the final result.

**OUTPUT FORMAT:**
To call a tool, output a JSON block like this:
{{"action": "tool_name", "arguments": {{"arg1": "value1"}}}}

Do not output any text outside the JSON block when acting.
"""

    def execute(self, task: str, context: List[Dict] = None) -> str:
        """Runs the ReAct loop until completion or max iterations."""
        history = (context or [])[-5:]  # Keep last 5 turns for context
        history.append({"role": "user", "content": task})
        
        logger.info(f"[ReAct] Starting execution for: {task}")
        
        for i in range(self.max_iterations):
            logger.debug(f"[ReAct] Iteration {i+1}/{self.max_iterations}")
            
            # 1. REASON: Ask LLM for next step
            response = self.brain.chat(
                messages=history, 
                system_prompt=self.system_prompt,
                temperature=0.0  # Low temp for deterministic tool calls
            )
            
            # 2. ACT: Parse the tool call
            action = self._parse_action(response)
            
            if not action:
                # LLM decided to talk directly (Task Complete)
                logger.info(f"[ReAct] LLM responded with natural language: {response[:100]}...")
                return response
            
            tool_name = action.get('action')
            args = action.get('arguments', {})
            
            # 3. OBSERVE: Execute tool and capture result
            observation = self._execute_tool(tool_name, args)
            
            # Add interaction to history
            history.append({"role": "assistant", "content": json.dumps(action)})
            history.append({"role": "user", "content": f"Observation: {observation}"})
            
            if observation.startswith("ERROR"):
                logger.warning(f"[ReAct] Tool error observed: {observation}")
            
        return "Error: Max iterations reached without completing the task."

    def _parse_action(self, response: str) -> Optional[Dict]:
        """Extracts JSON action from LLM response."""
        try:
            # Handle markdown code blocks if present
            clean_resp = response.strip()
            if clean_resp.startswith("```json"):
                clean_resp = clean_resp[7:]
            if clean_resp.endswith("```"):
                clean_resp = clean_resp[:-3]
            
            data = json.loads(clean_resp.strip())
            if 'action' in data:
                return data
        except json.JSONDecodeError:
            pass
        
        return None

    def _execute_tool(self, tool_name: str, args: Dict) -> str:
        """Executes a tool and returns a string observation."""
        # Check if tool exists
        if not self.tool_registry.has_tool(tool_name):
            available = ", ".join(self.tool_registry.get_all_tools().keys())
            return f"ERROR: Tool '{tool_name}' does not exist. Available tools: [{available}]"
        
        try:
            result = self.tool_registry.execute(tool_name, args)
            
            # Normalize result to string observation
            if hasattr(result, 'success') and not result.success:
                return f"ERROR: {result.error or 'Tool execution failed'}"
            
            # Extract meaningful content from ToolResult
            output = ""
            if hasattr(result, 'output'):
                output = str(result.output)
            elif hasattr(result, 'data'):
                output = str(result.data)
            else:
                output = str(result)
            
            # Truncate long outputs to prevent context overflow
            if len(output) > 2000:
                output = output[:2000] + "... [truncated]"
                
            return output
            
        except Exception as e:
            logger.exception(f"[ReAct] Exception executing {tool_name}")
            return f"ERROR: Exception occurred - {str(e)}"
