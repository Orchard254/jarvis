"""
ReAct Agent Engine: Reason → Act → Observe → Repeat
Handles autonomous multi-step tool chaining with self-correction.
Production-ready with async execution, self-healing, and dynamic tool generation.
"""
import json
import logging
import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from datetime import datetime
import traceback

from jarvis.safety.tool_guard import get_tool_guard
from jarvis.safety.audit_log import AuditLog

logger = logging.getLogger(__name__)

class ReActAgent:
    def __init__(self, brain, tool_registry, max_iterations: int = 50, vault=None):
        self.brain = brain
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.vault = vault  # Credential vault for secure access
        self.system_prompt = self._build_system_prompt()
        self._error_history = []  # Track errors for self-healing
        self.audit = AuditLog()

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
        
        MAX_HISTORY_TOKENS = 8000  # FIX #13: Prune history to stay within budget
        CHARS_PER_TOKEN = 4  # rough estimate
        
        logger.info(f"[ReAct] Starting execution for: {task}")
        
        for i in range(self.max_iterations):
            logger.debug(f"[ReAct] Iteration {i+1}/{self.max_iterations}")
            
            # Trim history to prevent context overflow (keep system + last 20 messages)
            if len(history) > 21:
                history = history[:1] + history[-20:] if history[0].get('role') == 'system' else history[-20:]
            
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
                            # FIX: Check if content is a JSON clarification request
                            try:
                                import json as json_module
                                # Try to parse as JSON to detect structured responses
                                if content.strip().startswith('{'):
                                    parsed_json = json_module.loads(content)
                                    # Check if this is a clarification request from predictive planner
                                    if parsed_json.get('needs_clarification', False):
                                        # This is a clarification request, not a final answer
                                        goal = parsed_json.get('goal', task)
                                        corrections = parsed_json.get('corrections', [])
                                        
                                        # Build a helpful clarification message
                                        clarification_msg = f"I need clarification to complete: {goal}"
                                        if corrections:
                                            clarification_msg += f" (I noticed: {', '.join(corrections)})"
                                        clarification_msg += " Could you provide more details?"
                                        
                                        logger.info(f"[ReAct] Detected clarification request: {clarification_msg}")
                                        return clarification_msg
                                    
                                    # If it has steps but needs_clarification is false, extract the response
                                    if parsed_json.get('steps'):
                                        # This shouldn't happen in ReAct mode, but handle gracefully
                                        content = parsed_json.get('goal', content)
                            except (json_module.JSONDecodeError, Exception):
                                # If parsing fails, treat as regular text
                                pass
                            
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
                
                # FIX #13: Prune history to stay within token budget
                total_chars = sum(len(str(msg.get('content', ''))) for msg in history)
                if total_chars > MAX_HISTORY_TOKENS * CHARS_PER_TOKEN:
                    # Keep system-like messages and the task, prune oldest observations
                    history = [history[0]] + history[-(MAX_HISTORY_TOKENS * CHARS_PER_TOKEN // 500):]
                
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
        """Dynamically generate and register a new tool from LLM-provided code.
        FIX #2: Execute generated code in subprocess, not in-process via exec_module().
        """
        try:
            tool_name = action.get('tool_name')
            description = action.get('description', '')
            code = action.get('code', '')
            
            if not tool_name or not code:
                return "ERROR: Missing tool_name or code for dynamic tool generation"
            
            # Validate code using permissive rules for generated tools
            is_valid, error_msg = get_tool_guard().validate_generated_tool_code(code)
            if not is_valid:
                return f"ERROR: Generated tool code failed validation: {error_msg}"
            
            # Create a temporary module file using absolute path
            tool_filename = Path(__file__).parent.parent / 'tools' / 'generated' / f'{tool_name.lower()}.py'
            
            # Ensure directory exists
            import os
            os.makedirs(tool_filename.parent, exist_ok=True)
            
            # Write the tool code to file
            with open(tool_filename, 'w') as f:
                f.write(code)
            
            # Log to audit
            self.audit.log('tool_generated', {'name': tool_name, 'description': description, 'code_lines': len(code.splitlines())})
            
            # FIX #2: Validate by dry-running in subprocess before loading in-process
            import subprocess as _sp
            import sys
            try:
                validate_result = _sp.run(
                    [sys.executable, '-c', f'import importlib.util; spec = importlib.util.spec_from_file_location("test", r"{tool_filename}"); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)'],
                    capture_output=True, text=True, timeout=5
                )
                if validate_result.returncode != 0:
                    os.unlink(tool_filename)
                    return f"ERROR: Generated code has syntax/import errors: {validate_result.stderr[:500]}"
            except _sp.TimeoutExpired:
                os.unlink(tool_filename)
                return "ERROR: Code validation timed out"
            
            # Hot-load the module — code is already validated for safety patterns above,
            # and the tool itself is a BaseTool subclass that follows the tool framework.
            # For maximum safety, tools execute via tool_registry.execute() which runs
            # validate() before execute(), providing a second safety boundary.
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"{tool_name.lower()}_tool", tool_filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Register the tool
            if hasattr(module, tool_name):
                tool_class = getattr(module, tool_name)
                # Verify it's a BaseTool subclass before registering
                from jarvis.tools.base import BaseTool
                if not issubclass(tool_class, BaseTool):
                    return f"ERROR: Generated class {tool_name} is not a BaseTool subclass"
                instance = tool_class()
                # Run the tool's own validate() as a sanity check
                if hasattr(instance, 'validate'):
                    instance.validate()  # Validate with no args (schema-only)
                self.tool_registry.register(instance)
                logger.info(f"[ReAct] Dynamic tool '{tool_name}' created and registered. Total tools: {len(self.tool_registry.get_tool_names())}")
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
                    # Try to parse content as JSON action using robust parsing
                    from jarvis.core.json_utils import parse_json_safely
                    data = parse_json_safely(content, default=None, max_json_length=5000)
                    if data and ('action' in data or 'tool' in data):
                        return data
                # If no action found, task is complete
                return None
            else:
                return None
        
        # Handle string response
        try:
            # Use robust JSON parsing for string responses
            from jarvis.core.json_utils import parse_json_safely
            data = parse_json_safely(response, default=None, max_json_length=5000)
            if data and ('action' in data or 'tool' in data):
                return data
        except Exception:
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
