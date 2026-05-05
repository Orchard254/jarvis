"""
core/orchestrator_patch.py — Minimal patch for new tool execution flow

This shows the minimal changes needed in the orchestrator to implement
the new deterministic tool selection and execution pipeline.

NEW FLOW:
Input → Tool Hint Filter → LLM (with 3-5 tools) → Structured JSON Parse → 
Validation → Execution

REPLACES:
Input → All Tools → LLM → TOOL: pattern parse → Execute
"""

import json
import logging
from typing import Any, Dict, List, Optional

from jarvis.tools.registry_refactored import (
    get_registry,
    filter_tools,
    get_filtered_schemas,
    TOOL_HINTS,
)
from jarvis.tools.validator import validate_tool_call, get_validator
from jarvis.core.tool_call_parser import (
    parse_tool_call_json,
    is_valid_tool_call_json,
    build_system_prompt_with_tools,
    format_tool_call_for_llm,
)

logger = logging.getLogger("orchestrator_patch")


class OrchestratorToolPatch:
    """
    Minimal patch class showing how to integrate the new tool system
    into the existing orchestrator.
    
    Usage: Mix into or replace relevant methods in Orchestrator class
    """
    
    def __init__(self):
        self.tool_registry = get_registry()
        self.tool_validator = get_validator()
    
    # =========================================================================
    # NEW METHOD 1: Filter tools before sending to LLM
    # =========================================================================
    
    def _get_filtered_tools_for_llm(self, user_input: str, max_tools: int = 5) -> List[dict]:
        """
        Get filtered tool schemas based on user input hints.
        
        This is the KEY change for deterministic tool selection.
        Instead of sending ALL tools to the LLM, we send only 3-5 relevant ones.
        
        Args:
            user_input: User's natural language request
            max_tools: Maximum tools to include (default: 5)
            
        Returns:
            List of filtered tool schemas for LLM function calling
        """
        return get_filtered_schemas(user_input, max_tools)
    
    # =========================================================================
    # NEW METHOD 2: Build prompt with filtered tools + strict JSON format
    # =========================================================================
    
    def _build_strict_json_prompt(self, user_input: str) -> str:
        """
        Build system prompt with filtered tools and strict JSON output requirement.
        
        This replaces _build_single_loop_prompt in the original orchestrator.
        """
        # Get filtered tools based on user input
        filtered_schemas = self._get_filtered_tools_for_llm(user_input)
        
        # Build tools section
        tools_section = build_system_prompt_with_tools(filtered_schemas)
        
        # Get app context if available
        app_ctx = getattr(self, 'get_app_context', lambda: {})()
        app_context_str = ""
        if app_ctx:
            if app_ctx.get('current_app'):
                app_context_str += f"\nCurrent active app: {app_ctx['current_app']}"
            if app_ctx.get('last_active_app'):
                app_context_str += f"\nLast active app: {app_ctx['last_active_app']}"
        
        return f"""You are JARVIS, an AI assistant that can use tools to help users.
{app_context_str}

CRITICAL OUTPUT FORMAT:
You MUST respond with valid JSON ONLY. No explanatory text.

For tool calls, use this EXACT format:
{{
    "action": "tool_call",
    "tool": "<tool_name>",
    "args": {{...}},
    "thought": "optional reasoning"
}}

Example:
{{
    "action": "tool_call",
    "tool": "app.open",
    "args": {{"app_name": "chrome"}},
    "thought": "User wants to browse the web"
}}

RULES:
1. Output ONLY ONE tool call per response
2. Use STRICT JSON format - no markdown, no explanations
3. Wait for tool result before next action
4. When task is complete, give final answer naturally (not as tool call)
5. Only use tools from the AVAILABLE TOOLS list below

{tools_section}

User request: {user_input}"""
    
    # =========================================================================
    # NEW METHOD 3: Parse and validate LLM response
    # =========================================================================
    
    def _parse_and_validate_tool_call(
        self,
        llm_response: str,
    ) -> tuple[Optional[Dict[str, Any]], str]:
        """
        Parse LLM response and validate the tool call.
        
        This replaces the old TOOL: pattern parsing.
        
        Args:
            llm_response: Raw LLM output
            
        Returns:
            Tuple of (parsed_call_dict, error_message)
            If successful: (dict, "")
            If failed: (None, "error description")
        """
        # Step 1: Check if it looks like valid JSON tool call
        if not is_valid_tool_call_json(llm_response):
            # Try to parse anyway (handles markdown blocks etc.)
            parsed, error = parse_tool_call_json(llm_response)
            if not parsed:
                return None, f"Invalid JSON format: {error}. Respond with: {{\"action\": \"tool_call\", \"tool\": \"...\", \"args\": {{}}}}"
        else:
            parsed, error = parse_tool_call_json(llm_response)
            if not parsed:
                return None, f"Parse error: {error}"
        
        # Step 2: Validate tool exists and args match schema
        tool_name = parsed.get('tool')
        args = parsed.get('args', {})
        
        is_valid, error_msg = validate_tool_call(tool_name, args)
        if not is_valid:
            return None, f"Validation failed: {error_msg}"
        
        logger.info(f"Parsed and validated tool call: {tool_name}({args})")
        return parsed, ""
    
    # =========================================================================
    # NEW METHOD 4: Execute with validation gate
    # =========================================================================
    
    def _execute_validated_tool_call(
        self,
        parsed_call: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a validated tool call.
        
        This is called AFTER parse_and_validate_tool_call succeeds.
        
        Args:
            parsed_call: Validated tool call dict
            
        Returns:
            Execution result dict
        """
        import time
        
        start_time = time.time()
        tool_name = parsed_call['tool']
        args = parsed_call.get('args', {})
        thought = parsed_call.get('thought', '')
        
        logger.info(f"[EXEC] Executing: {tool_name} with args={args}, thought={thought}")
        
        try:
            # Double-check validation right before execution (defense in depth)
            is_valid, error_msg = validate_tool_call(tool_name, args)
            if not is_valid:
                return {
                    'success': False,
                    'output': f"Safety check failed: {error_msg}",
                    'tool_name': tool_name,
                    'args': args,
                    'duration_ms': int((time.time() - start_time) * 1000),
                }
            
            # Execute via registry
            result = self.tool_registry.execute(tool_name, **args)
            
            return {
                'success': result.success,
                'output': result.output if result.success else result.error,
                'tool_name': tool_name,
                'args': args,
                'duration_ms': int((time.time() - start_time) * 1000),
                'verified': result.verified,
                'verify_msg': result.verify_msg,
            }
            
        except Exception as e:
            logger.error(f"[EXEC] Execution failed: {e}")
            return {
                'success': False,
                'output': f"Execution error: {str(e)}",
                'tool_name': tool_name,
                'args': args,
                'duration_ms': int((time.time() - start_time) * 1000),
            }
    
    # =========================================================================
    # INTEGRATION: Main process command flow
    # =========================================================================
    
    def process_command_with_new_flow(self, user_input: str) -> Dict[str, Any]:
        """
        Process a user command using the new deterministic flow.
        
        This shows the complete integration point. Replace your existing
        process_command or similar method with this pattern.
        
        FLOW:
        1. Filter tools by hints (3-5 max)
        2. Build prompt with filtered tools
        3. Call LLM
        4. Parse JSON response
        5. Validate tool call
        6. Execute if valid
        7. Return result
        
        Args:
            user_input: User's natural language request
            
        Returns:
            Result dict with response and metadata
        """
        logger.info(f"[NEW_FLOW] Processing: {user_input}")
        
        # Step 1: Filter tools based on user input hints
        filtered_tools = self._get_filtered_tools_for_llm(user_input)
        logger.info(f"[NEW_FLOW] Filtered to {len(filtered_tools)} tools: {list(filtered_tools.keys())}")
        
        # Step 2: Build prompt with filtered tools
        system_prompt = self._build_strict_json_prompt(user_input)
        
        # Step 3: Call LLM (adapt to your LLM interface)
        # This is pseudocode - adapt to your actual LLM client
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
        
        # Replace this with your actual LLM call
        # llm_response = self.brain.chat(messages, temperature=0)  # Low temp for determinism
        llm_response = '{"action": "tool_call", "tool": "app.open", "args": {"app_name": "notepad"}}'
        
        logger.info(f"[NEW_FLOW] LLM response: {llm_response[:200]}")
        
        # Step 4: Parse and validate
        parsed_call, error = self._parse_and_validate_tool_call(llm_response)
        
        if not parsed_call:
            # Invalid tool call - ask LLM to retry or respond naturally
            logger.warning(f"[NEW_FLOW] Validation failed: {error}")
            return {
                'success': False,
                'response': f"I couldn't understand that. Error: {error}",
                'type': 'error',
            }
        
        # Step 5: Execute validated tool call
        exec_result = self._execute_validated_tool_call(parsed_call)
        
        if exec_result['success']:
            return {
                'success': True,
                'response': exec_result['output'],
                'type': 'tool_result',
                'tool_name': parsed_call['tool'],
                'args': parsed_call.get('args', {}),
                'thought': parsed_call.get('thought', ''),
            }
        else:
            return {
                'success': False,
                'response': f"Tool execution failed: {exec_result['output']}",
                'type': 'error',
                'tool_name': parsed_call['tool'],
            }


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create patch instance
    patch = OrchestratorToolPatch()
    
    # Test cases
    test_inputs = [
        "Open notepad please",
        "Search for weather forecast",
        "Read the file at C:\\test.txt",
        "Lock my computer",
    ]
    
    print("Testing New Tool Execution Flow\n" + "=" * 50)
    
    for user_input in test_inputs:
        print(f"\n--- Input: {user_input} ---")
        result = patch.process_command_with_new_flow(user_input)
        print(f"Result: {json.dumps(result, indent=2)}")
