"""
Predictive Planner - Leverages LLM's internal knowledge to generate
high-confidence execution plans before acting.
"""
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from jarvis.core.brain import Brain
from jarvis.core.json_utils import (
    parse_json_safely,
    validate_plan_structure,
    normalize_plan_parameters
)

logger = logging.getLogger(__name__)

# Define required parameters for each tool
# Tools not listed here don't require parameters
REQUIRED_PARAMETERS = {
    'create_file': ['path'],
    'write_file': ['path', 'content'],
    'read_file': ['path'],
    'delete_file': ['path'],
    'navigate_to_url': ['url'],
    'fill_input': ['selector', 'value'],
    'click_element': ['selector'],
    'search_web': ['query'],
    'open_app': ['app'],
    'close_app': ['app'],
    'press_key': ['key'],
    'type_text': ['text'],
    'focus_window': ['title'],
    'clear_text': [],  # Optional target_app parameter
}

# Tools that don't require parameters (they work with empty dict)
NO_PARAMETER_TOOLS = {
    'paste_from_clipboard',
    'copy_to_clipboard',
    'get_time',
    'take_screenshot',
    'get_window_list',
}

PLAN_PROMPT = """
You are an expert automation planner. Your goal is to predict the EXACT steps needed to fulfill the user's request.
Use your internal knowledge to correct ambiguities, fix typos, and predict correct URLs/selectors BEFORE executing.

RULES:
1. CORRECT DOMAINS: If user says "kilimall", you KNOW it is "https://www.kilimall.co.ke" (or .cn/.ug depending on context, default .co.ke). Do NOT search for the URL; use your knowledge.
2. PREDICT SELECTORS: Most search inputs are 'input[name="q"]', 'input[type="search"]', or '.search-input'. Predict the most likely one.
3. BE SPECIFIC: Do not say "open site". Say "navigate_to_url: https://www.kilimall.co.ke".
4. HANDLE TYPOS: "refubished" -> "refurbished", "kilimal" -> "kilimall".
5. MINIMIZE STEPS: Combine actions where possible.
6. CHECK RECENT RESULTS: Before planning, review recent successful results below. If the answer is already available in recent results, respond directly without executing tools. DO NOT re-execute tools that have already provided the needed information.
7. AVOID FAILED ACTIONS: Review failed actions below. DO NOT retry tools that failed with the same parameters unless the error is clearly resolved.
8. TEXT CLEARING: To clear text in a text editor, use press_key with "Ctrl+A" then press_key with "Delete". NEVER use hundreds of backspace characters.
9. OUTPUT ONLY JSON: No markdown, no explanations, just raw JSON.
10. ALWAYS INCLUDE REQUIRED PARAMETERS: 
    - open_app requires "app" (e.g., {{"app": "notepad"}})
    - close_app requires "app" (e.g., {{"app": "notepad"}})
    - navigate_to_url requires "url" (e.g., {{"url": "https://example.com"}})
    - press_key requires "key" (e.g., {{"key": "Ctrl+A"}})
    - type_text requires "text" (e.g., {{"text": "hello"}})
    - fill_input requires "selector" and "value"
    - click_element requires "selector"
    - search_web requires "query"
    - focus_window requires "title"
    - create_file/write_file/read_file/delete_file require "path"
11. CLARIFICATION FLAG: Set "needs_clarification": true ONLY if the request is ambiguous, dangerous, or missing critical information that prevents execution. For clear requests like "open notepad", set to false and include the steps. NEVER set needs_clarification to true just because you can generate a plan - only use it when you genuinely cannot proceed without more information.
12. STEP INDEPENDENCE: Each step should be independent. Do NOT include steps that simply retrieve data that was already retrieved in a previous step. If a previous step already obtained the information, use it directly in subsequent steps.
13. MANDATORY STEP GENERATION: If the request is clear and actionable (like opening an app, typing text, navigating to a known website), you MUST generate the steps. Do NOT return empty steps array for straightforward commands. Empty steps are only acceptable for genuinely impossible or dangerously ambiguous requests.

{context_section}
AVAILABLE TOOLS:
{tools_description}

USER REQUEST: "{user_request}"

Output ONLY valid JSON in this exact format (no markdown wrapping):
{{
    "goal": "Clear restatement of the goal",
    "corrections": ["List of typos or ambiguities you fixed"],
    "confidence": "high/medium/low",
    "needs_clarification": false,
    "steps": [
        {{
            "tool": "tool_name",
            "params": {{"param": "value"}},
            "reason": "Why this step is needed"
        }}
    ]
}}
"""

class PredictivePlanner:
    def __init__(self, brain: Brain):
        self.brain = brain

    def generate_plan(self, user_request: str, available_tools: Dict[str, Any], 
                      recent_results: Optional[List[Dict[str, Any]]] = None,
                      failed_actions: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict]:
        """Generate a high-confidence plan using LLM's internal knowledge."""
        
        # Build tools description for context
        tools_desc = "\n".join([
            f"- {name}: {desc.get('description', 'No description')}" 
            for name, desc in available_tools.items()
        ])
        
        # Build context section with recent results and failed actions
        context_section = ""
        if recent_results or failed_actions:
            context_parts = []
            
            if recent_results:
                # Show last 5 successful results
                recent = recent_results[-5:] if len(recent_results) > 5 else recent_results
                results_text = "\n".join([
                    f"  - {r['tool']} returned: {r['result'][:150]}..." if len(r['result']) > 150 else f"  - {r['tool']} returned: {r['result']}"
                    for r in recent
                ])
                context_parts.append(f"[RECENT SUCCESSFUL RESULTS]:\n{results_text}")
            
            if failed_actions:
                # Show last 5 failed actions
                failed = failed_actions[-5:] if len(failed_actions) > 5 else failed_actions
                failed_text = "\n".join([
                    f"  - {f['tool']} failed: {f['error'][:150]}... [DO NOT retry]" if len(f['error']) > 150 else f"  - {f['tool']} failed: {f['error']} [DO NOT retry]"
                    for f in failed
                ])
                context_parts.append(f"[FAILED ACTIONS - AVOID]:\n{failed_text}")
            
            if context_parts:
                context_section = "\n\n".join(context_parts) + "\n\n"
        
        prompt = PLAN_PROMPT.format(
            context_section=context_section,
            tools_description=tools_desc,
            user_request=user_request
        )
        
        try:
            # Force JSON output via prompt engineering (json_mode not supported by all models)
            # Disable tool calling to get raw text response for JSON parsing
            max_retries = 3
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    response = self.brain.chat(
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,  # Low temp for deterministic planning
                        include_tools=False  # Don't include tool schemas - we want raw JSON text
                    )
                    
                    # Extract content from brain response dict
                    if isinstance(response, dict):
                        if not response.get('success', False):
                            logger.error(f"Brain chat failed: {response.get('error', 'Unknown error')}")
                            last_error = response.get('error', 'Unknown error')
                            if attempt < max_retries - 1:
                                logger.info(f"Retrying brain chat (attempt {attempt + 2}/{max_retries})...")
                                continue
                            return None
                        # Get the actual content string from the response dict
                        response_content = response.get('content', '')
                        if not response_content:
                            logger.warning(f"Empty content in brain response (attempt {attempt + 1}/{max_retries})")
                            last_error = "Empty LLM response content"
                            if attempt < max_retries - 1:
                                logger.info(f"Retrying brain chat due to empty content (attempt {attempt + 2}/{max_retries})...")
                                continue
                            logger.error("Empty content in brain response after all retries")
                            return None
                        response = response_content
                    
                    # Use robust JSON parsing with multiple fallback strategies
                    plan = parse_json_safely(response, default=None, max_json_length=5000)
                    
                    if plan is None:
                        logger.error(f"Failed to parse JSON from LLM response (attempt {attempt + 1}/{max_retries})")
                        last_error = "Failed to parse JSON from LLM response"
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying due to JSON parse failure (attempt {attempt + 2}/{max_retries})...")
                            continue
                        logger.error("Failed to parse JSON from LLM response after all retries")
                        return None
                    
                    # Validate plan structure
                    is_valid, error_msg = validate_plan_structure(plan)
                    if not is_valid:
                        logger.error(f"Invalid plan structure: {error_msg}")
                        last_error = f"Invalid plan structure: {error_msg}"
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying due to invalid plan structure (attempt {attempt + 2}/{max_retries})...")
                            continue
                        logger.error(f"Invalid plan structure after all retries: {error_msg}")
                        # If plan has no steps but LLM requested clarification, return it anyway for user confirmation
                        if error_msg == "Plan has no steps" and plan.get('needs_clarification', False):
                            logger.warning("Returning plan with no steps for user clarification")
                            return plan
                        return None
                    
                    logger.info(f"Plan generated with {len(plan['steps'])} steps (Confidence: {plan.get('confidence', 'unknown')})")
                    if plan.get('corrections'):
                        logger.info(f"Corrections made: {plan['corrections']}")
                    
                    # Validate and filter steps to remove invalid ones
                    plan = self._validate_and_filter_steps(plan)
                    
                    # Check if we have any valid steps left
                    if not plan.get('steps'):
                        logger.warning("All plan steps were filtered out as invalid")
                        if plan.get('invalid_step_details'):
                            invalid_reasons = [s['reason'] for s in plan['invalid_step_details']]
                            logger.warning(f"Invalid steps reasons: {invalid_reasons}")
                    
                    return plan
                    
                except Exception as e:
                    logger.warning(f"Plan generation error (attempt {attempt + 1}/{max_retries}): {e}")
                    last_error = str(e)
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying after exception (attempt {attempt + 2}/{max_retries})...")
                        continue
                    logger.error(f"Plan generation failed after all retries: {e}")
                    return None
            
            return None  # Should not reach here, but safety fallback
            
        except Exception as e:
            logger.error(f"Failed to generate plan: {e}")
            return None

    def _validate_and_filter_steps(self, plan: Dict) -> Dict:
        """
        Validate plan steps and filter out invalid ones.
        
        Returns plan with only valid steps, plus warnings for filtered steps.
        """
        if 'steps' not in plan or not isinstance(plan['steps'], list):
            return plan
        
        valid_steps = []
        invalid_steps = []
        
        for i, step in enumerate(plan.get('steps', [])):
            # Get tool name
            tool_name = step.get('tool') or step.get('tool_name')
            if not tool_name:
                invalid_steps.append({
                    'step': i,
                    'reason': 'Missing tool name',
                    'step_data': step
                })
                continue
            
            # Get parameters
            params = step.get('params') or step.get('parameters') or step.get('arguments') or {}
            
            # Normalize parameters
            normalized_params = normalize_plan_parameters(step, tool_name)
            
            # Check if this tool requires parameters
            if tool_name in NO_PARAMETER_TOOLS:
                # These tools don't need parameters - ensure empty dict
                normalized_params = {}
            else:
                # Check for required parameters for other tools
                required = REQUIRED_PARAMETERS.get(tool_name, [])
                missing_params = [p for p in required if p not in normalized_params or not normalized_params[p]]
                
                if missing_params:
                    invalid_steps.append({
                        'step': i,
                        'tool': tool_name,
                        'reason': f'Missing required parameters: {", ".join(missing_params)}',
                        'params': normalized_params
                    })
                    logger.warning(f"Step {i}: {tool_name} is missing required parameters: {missing_params}")
                    continue
            
            # Valid step - update with normalized parameters
            valid_step = dict(step)
            valid_step['params'] = normalized_params
            valid_steps.append(valid_step)
        
        # Log filtering results
        if invalid_steps:
            logger.warning(f"Filtered out {len(invalid_steps)} invalid steps from plan")
            for invalid in invalid_steps:
                logger.debug(f"  - Step {invalid['step']}: {invalid['reason']}")
        
        # Update plan with valid steps only
        plan['steps'] = valid_steps
        plan['filtered_steps'] = len(invalid_steps)
        plan['invalid_step_details'] = invalid_steps
        
        return plan

    def execute_plan(self, plan: Dict, tool_executor) -> Dict[str, Any]:
        """Execute a validated plan step-by-step, passing results between dependent steps."""
        results = []
        success = True
        step_outputs = {}  # Store outputs for inter-step dependencies
        
        logger.info(f"Starting execution of planned task: {plan.get('goal')}")
        
        for i, step in enumerate(plan.get("steps", [])):
            tool_name = step.get("tool")
            params = step.get("params", {})
            
            if not tool_name:
                logger.warning(f"Step {i+1} missing tool name, skipping.")
                continue
            
            # Replace placeholders with actual outputs from previous steps
            # Look for patterns like [list of apps], {result}, etc.
            params = self._resolve_placeholders(params, step_outputs)
            
            # Ensure reason text is ASCII-safe for Windows console logging
            reason = step.get('reason', '')
            if reason:
                # Replace non-breaking hyphens and other special chars with standard ASCII
                reason = reason.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-')
            
            logger.info(f"Step {i+1}/{len(plan['steps'])}: {tool_name}({params}) - {reason}")
            
            try:
                # Execute tool
                result = tool_executor.execute(tool_name, **params)
                results.append({
                    "step": i + 1,
                    "tool": tool_name,
                    "success": True,
                    "result": result
                })
                # Store result for potential use by subsequent steps
                step_outputs[f"step_{i+1}"] = result
                step_outputs[f"last_result"] = result
                logger.debug(f"Step {i+1} completed successfully.")
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Step {i+1} failed: {error_msg}")
                
                # If confidence was high, this might be a transient error -> retry once
                if plan.get("confidence") == "high":
                    logger.info(f"Retrying step {i+1} due to high confidence plan...")
                    try:
                        result = tool_executor.execute(tool_name, **params)
                        results.append({"step": i+1, "tool": tool_name, "success": True, "result": result, "retried": True})
                        step_outputs[f"step_{i+1}"] = result
                        step_outputs[f"last_result"] = result
                        continue
                    except Exception as retry_err:
                        error_msg = str(retry_err)
                
                results.append({
                    "step": i + 1,
                    "tool": tool_name,
                    "success": False,
                    "error": error_msg
                })
                
                # If critical failure, stop? Or continue? 
                # For now, mark success=False but continue to next step if independent
                success = False
        
        return {
            "success": success,
            "goal": plan.get("goal"),
            "results": results,
            "summary": self._generate_summary(plan, results)
        }

    def _resolve_placeholders(self, params: Dict, step_outputs: Dict) -> Dict:
        """
        Resolve placeholders in parameters using outputs from previous steps.
        
        Handles patterns like:
        - [list of apps] -> replaced with the first non-trivial result (typically data retrieval)
        - {step_1} -> replaced with specific step output
        - {last_result} -> replaced with most recent result
        - {first_result} -> replaced with the first meaningful data result
        """
        import re
        
        resolved_params = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved_value = value
                
                # Replace {last_result} or {step_X} placeholders first (explicit references)
                for step_key, step_output in step_outputs.items():
                    if step_output is not None:
                        output_str = str(step_output)
                        resolved_value = resolved_value.replace(f"{{{step_key}}}", output_str)
                
                # Handle bracketed placeholders like [list of apps], [results], etc.
                # These should use the FIRST meaningful data result, not the last one
                bracket_pattern = r'\[([^\]]+)\]'
                matches = re.findall(bracket_pattern, resolved_value)
                if matches:
                    # Find the first meaningful result (skip trivial responses like "Success" or "Opened X")
                    meaningful_result = None
                    for i in range(1, len(step_outputs) + 1):
                        step_key = f"step_{i}"
                        if step_key in step_outputs and step_outputs[step_key] is not None:
                            result_str = str(step_outputs[step_key])
                            # Skip trivial results
                            if not any(trivial in result_str.lower() for trivial in ['success', 'opened ', 'closed ', 'done']):
                                meaningful_result = result_str
                                break
                    
                    # If no meaningful result found, use the first non-None result
                    if meaningful_result is None and "step_1" in step_outputs:
                        meaningful_result = str(step_outputs["step_1"])
                    
                    if meaningful_result:
                        # Replace all bracket placeholders with the meaningful result
                        resolved_value = re.sub(bracket_pattern, meaningful_result, resolved_value)
                
                resolved_params[key] = resolved_value
            else:
                resolved_params[key] = value
        
        return resolved_params

    def _generate_summary(self, plan: Dict, results: List[Dict]) -> str:
        """Generate a natural language summary of the execution."""
        successful_steps = sum(1 for r in results if r["success"])
        total_steps = len(results)
        
        if successful_steps == total_steps:
            # Extract actual outputs from successful tool executions
            outputs = []
            for r in results:
                if r.get("result"):
                    result_obj = r["result"]
                    # Handle ToolResult objects
                    if hasattr(result_obj, 'output'):
                        outputs.append(result_obj.output)
                    elif isinstance(result_obj, dict):
                        outputs.append(result_obj.get('output', str(result_obj)))
                    else:
                        outputs.append(str(result_obj))
            
            # If we have actual outputs, include them in the summary
            if outputs:
                return ". ".join(outputs)
            else:
                return f"Successfully completed '{plan.get('goal')}' in {total_steps} steps."
        else:
            failed_tools = [r["tool"] for r in results if not r["success"]]
            return f"Partially completed '{plan.get('goal')}'. Failed at: {', '.join(failed_tools)}."
