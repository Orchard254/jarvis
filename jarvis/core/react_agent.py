"""
ReAct Agent Engine: Reason → Act → Observe → Repeat
Handles autonomous multi-step tool chaining with self-correction.
Production-ready with async execution, self-healing, and dynamic tool generation.
"""
import json
import logging
import asyncio
import aiofiles
import time
from typing import Any, Dict, List, Optional, Tuple, Callable
from datetime import datetime
import traceback

logger = logging.getLogger(__name__)

class ReActAgent:
    def __init__(self, brain, tool_registry, max_iterations: int = 50, vault=None):
        self.brain = brain
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.vault = vault  # Credential vault for secure access
        self.system_prompt = self._build_system_prompt()
        self._error_history = []  # Track errors for self-healing

    def _build_system_prompt(self) -> str:
        """Builds a prompt that enforces ReAct behavior and lists available tools."""
        tools_desc = []
        for name, tool in self.tool_registry.get_all_tools().items():
            # Extract schema from tool instance
            schema = tool.get_schema() if hasattr(tool, 'get_schema') else {}
            
            # Get parameters/arguments from schema
            params = schema.get('parameters', {}) or schema.get('arguments', {})
            param_props = params.get('properties', {})
            
            # Format arguments as string
            args_list = []
            for arg_name, arg_info in param_props.items():
                arg_type = arg_info.get('type', 'any')
                arg_desc = arg_info.get('description', '')
                required = arg_name in params.get('required', [])
                req_marker = '*' if required else ''
                args_list.append(f"{req_marker}{arg_name}: {arg_type}")
            
            args = ", ".join(args_list) if args_list else "no args"
            
            # Get description from schema or tool
            desc = schema.get('description', getattr(tool, 'description', 'No description'))
            
            tools_desc.append(f"- {name}({args}): {desc}")
        
        tools_list = "\n".join(tools_desc)
        
        # Add dynamic tool generation capability
        dynamic_tool_instruction = """
**DYNAMIC TOOL GENERATION:**
If you need functionality that doesn't exist, you can request to generate a new tool.
Output: {"action": "generate_tool", "tool_name": "name", "description": "...", "code": "python code"}
The system will create and register the tool automatically.
"""
        
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
6. Use secure credentials from the vault when needed (API keys, passwords).
7. For long-running tasks, use async execution patterns.

{dynamic_tool_instruction}

**OUTPUT FORMAT:**
To call a tool, output a JSON block like this:
{{"action": "tool_name", "arguments": {{"arg1": "value1"}}}}

Do not output any text outside the JSON block when acting.
"""

    def execute(self, task: str, context: List[Dict] = None) -> str:
        """Runs the ReAct loop until completion or max iterations with self-healing."""
        history = (context or [])[-5:]  # Keep last 5 turns for context
        history.append({"role": "user", "content": task})
        
        logger.info(f"[ReAct] Starting execution for: {task}")
        
        for i in range(self.max_iterations):
            logger.debug(f"[ReAct] Iteration {i+1}/{self.max_iterations}")
            
            try:
                # 1. REASON: Ask LLM for next step with retry logic for empty/malformed responses
                max_retries = 3
                response = None
                
                for attempt in range(max_retries):
                    try:
                        response = self.brain.chat(
                            messages=history, 
                            system_prompt=self.system_prompt,
                            temperature=0.0,  # Low temp for deterministic tool calls
                            include_tools=True  # Enable tool calling for ReAct agent
                        )
                        
                        # Check for successful response
                        if isinstance(response, dict) and not response.get('success', False):
                            logger.warning(f"[ReAct] Brain chat failed (attempt {attempt + 1}/{max_retries}): {response.get('error', 'Unknown error')}")
                            if attempt < max_retries - 1:
                                logger.info(f"[ReAct] Retrying brain chat...")
                                continue
                            return f"Error: LLM service unavailable after {max_retries} attempts"
                        
                        # Check for empty content in natural language responses
                        if isinstance(response, dict):
                            content = response.get('content', '')
                            tool_calls = response.get('tool_calls', [])
                            
                            # If no tool calls and empty/no content, retry
                            if not tool_calls and not content:
                                logger.warning(f"[ReAct] Empty LLM response (attempt {attempt + 1}/{max_retries})")
                                if attempt < max_retries - 1:
                                    logger.info(f"[ReAct] Retrying due to empty response...")
                                    continue
                        
                        # Valid response received
                        break
                        
                    except Exception as e:
                        logger.warning(f"[ReAct] Exception during brain chat (attempt {attempt + 1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            logger.info(f"[ReAct] Retrying after exception...")
                            continue
                        return f"Error: Failed to communicate with LLM after {max_retries} attempts"
                
                if response is None:
                    return "Error: No response from LLM"
                
                # 2. ACT: Parse the tool call
                action = self._parse_action(response)
                
                if not action:
                    # LLM decided to talk directly (Task Complete)
                    logger.info(f"[ReAct] LLM responded with natural language: {str(response)[:100]}...")
                    # Extract content from dict response or return string
                    if isinstance(response, dict):
                        content = response.get('content', '')
                        if content:
                            return content
                        # Check if there was an error
                        if not response.get('success', True):
                            return f"Error: {response.get('error', 'Task failed')}"
                        return 'Task completed.'
                    return str(response) if response else "Task completed."
                
                # Handle dynamic tool generation
                if action.get('action') == 'generate_tool':
                    result = self._generate_tool(action)
                    observation = f"Tool generated and registered: {result}"
                    history.append({"role": "assistant", "content": json.dumps(action)})
                    history.append({"role": "user", "content": f"Observation: {observation}"})
                    continue
                
                tool_name = action.get('action') or action.get('tool')
                args = action.get('arguments') or action.get('args', {})
                
                # 3. OBSERVE: Execute tool with self-healing retry logic
                observation = self._execute_tool_with_retry(tool_name, args, max_retries=3)
                
                # Add interaction to history
                history.append({"role": "assistant", "content": json.dumps(action) if isinstance(action, dict) else str(action)})
                history.append({"role": "user", "content": f"Observation: {observation}"})
                
                # Self-healing: Track errors and inject learning
                if observation.startswith("ERROR"):
                    self._error_history.append({
                        'tool': tool_name,
                        'error': observation,
                        'timestamp': datetime.now().isoformat()
                    })
                    # Keep only last 5 errors
                    self._error_history = self._error_history[-5:]
                    
                    logger.warning(f"[ReAct] Tool error observed: {observation}")
                    
                    # If too many consecutive failures, suggest alternative
                    if len([e for e in self._error_history if e['tool'] == tool_name]) >= 3:
                        alt_msg = f"\n\n[HINT: The tool '{tool_name}' has failed multiple times. Consider using alternative approaches or different tools.]"
                        history.append({"role": "system", "content": alt_msg})
                
            except Exception as e:
                error_msg = f"ERROR: Critical exception in ReAct loop: {str(e)}\n{traceback.format_exc()}"
                logger.exception("[ReAct] Critical error in execution loop")
                history.append({"role": "user", "content": error_msg})
                
                # Self-healing: Try to recover by resetting context
                if i > self.max_iterations - 3:
                    return f"Error: Multiple failures encountered. Last error: {str(e)}"
        
        return f"Error: Max iterations ({self.max_iterations}) reached without completing the task. Consider breaking down the task into smaller steps or checking network connectivity."
    
    def _execute_tool_with_retry(self, tool_name: str, args: Dict, max_retries: int = 3) -> str:
        """Execute tool with exponential backoff retry logic."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                result = self._execute_tool(tool_name, args)
                
                # If successful or non-retryable error, return immediately
                if not result.startswith("ERROR") or "does not exist" in result:
                    return result
                
                # Retryable error - wait with exponential backoff
                last_error = result
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 0.5  # 0.5s, 1s, 2s...
                    logger.warning(f"[ReAct] Tool {tool_name} failed (attempt {attempt+1}/{max_retries}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    
            except Exception as e:
                last_error = f"ERROR: Exception - {str(e)}"
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 0.5
                    logger.warning(f"[ReAct] Exception on {tool_name} (attempt {attempt+1}/{max_retries}), retrying...")
                    time.sleep(wait_time)
        
        return f"ERROR: Tool {tool_name} failed after {max_retries} attempts. Last error: {last_error}"
    
    def _generate_tool(self, action: Dict) -> str:
        """Dynamically generate and register a new tool from LLM-provided code."""
        try:
            tool_name = action.get('tool_name')
            description = action.get('description', '')
            code = action.get('code', '')
            
            if not tool_name or not code:
                return "ERROR: Missing tool_name or code for dynamic tool generation"
            
            # Create a temporary module file
            tool_filename = f"jarvis/tools/generated/{tool_name.lower()}.py"
            
            # Ensure directory exists
            import os
            os.makedirs("jarvis/tools/generated", exist_ok=True)
            
            # Write the tool code
            with open(tool_filename, 'w') as f:
                f.write(code)
            
            # Hot-load the module
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"{tool_name.lower()}_tool", tool_filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Register the tool
            if hasattr(module, tool_name):
                tool_class = getattr(module, tool_name)
                self.tool_registry.register_tool(tool_class())
                return f"Successfully created and registered tool: {tool_name}"
            else:
                return f"ERROR: Generated code does not contain expected class {tool_name}"
                
        except Exception as e:
            return f"ERROR: Failed to generate tool: {str(e)}\n{traceback.format_exc()}"

    def _parse_action(self, response) -> Optional[Dict]:
        """Extracts JSON action from LLM response."""
        # Handle dict response directly (from tool_calls or brain.chat return value)
        if isinstance(response, dict):
            # Check for tool calls in Ollama format
            if 'tool_calls' in response and response['tool_calls']:
                tool_call = response['tool_calls'][0]
                return {
                    'action': tool_call['function']['name'],
                    'arguments': tool_call['function']['arguments']
                }
            # Check for natural language response in content field
            elif 'content' in response:
                content = response.get('content', '')
                if content:
                    # Try to parse content as JSON action
                    try:
                        clean_resp = content.strip()
                        if clean_resp.startswith("```json"):
                            clean_resp = clean_resp[7:]
                        if clean_resp.endswith("```"):
                            clean_resp = clean_resp[:-3]
                        data = json.loads(clean_resp.strip())
                        if 'action' in data or 'tool' in data:
                            return data
                    except (json.JSONDecodeError, AttributeError):
                        pass
                # If no action found, task is complete
                return None
            else:
                return None
        
        # Handle string response
        try:
            # Handle markdown code blocks if present
            clean_resp = response.strip()
            if clean_resp.startswith("```json"):
                clean_resp = clean_resp[7:]
            if clean_resp.endswith("```"):
                clean_resp = clean_resp[:-3]

            data = json.loads(clean_resp.strip())
            if 'action' in data or 'tool' in data:
                return data
        except (json.JSONDecodeError, AttributeError):
            pass

        return None

    def _execute_tool(self, tool_name: str, args: Dict) -> str:
        """Executes a tool and returns a string observation."""
        # Check if tool exists
        if not self.tool_registry.has_tool(tool_name):
            available = ", ".join(self.tool_registry.get_all_tools().keys())
            return f"ERROR: Tool '{tool_name}' does not exist. Available tools: [{available}]"
        
        try:
            result = self.tool_registry.execute(tool_name, **args)
            
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
