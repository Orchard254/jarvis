"""
Predictive Planner - Leverages LLM's internal knowledge to generate
high-confidence execution plans before acting.
"""
import json
import logging
from typing import Dict, List, Optional, Any
from jarvis.core.brain import Brain
from jarvis.core.json_utils import (
    parse_json_safely,
    validate_plan_structure,
    normalize_plan_parameters
)

logger = logging.getLogger(__name__)

PLAN_PROMPT = """
You are an expert automation planner. Your goal is to predict the EXACT steps needed to fulfill the user's request.
Use your internal knowledge to correct ambiguities, fix typos, and predict correct URLs/selectors BEFORE executing.

RULES:
1. CORRECT DOMAINS: If user says "kilimall", you KNOW it is "https://www.kilimall.co.ke" (or .cn/.ug depending on context, default .co.ke). Do NOT search for the URL; use your knowledge.
2. PREDICT SELECTORS: Most search inputs are 'input[name="q"]', 'input[type="search"]', or '.search-input'. Predict the most likely one.
3. BE SPECIFIC: Do not say "open site". Say "navigate_to_url: https://www.kilimall.co.ke".
4. HANDLE TYPOS: "refubished" -> "refurbished", "kilimal" -> "kilimall".
5. MINIMIZE STEPS: Combine actions where possible.
6. CHECK RECENT RESULTS FIRST: If information was already obtained recently, DO NOT re-execute the tool. Use the existing result.
7. AVOID FAILED ACTIONS: If a tool recently failed, do NOT retry it with the same parameters.
8. OUTPUT ONLY JSON: No markdown, no explanations, just raw JSON.

AVAILABLE TOOLS:
{tools_description}

{context_section}

USER REQUEST: "{user_request}"

Output ONLY valid JSON in this exact format (no markdown wrapping):
{{
    "goal": "Clear restatement of the goal",
    "corrections": ["List of typos or ambiguities you fixed"],
    "confidence": "high/medium/low",
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
                     recent_results: Optional[List[Dict]] = None, 
                     failed_actions: Optional[List[Dict]] = None) -> Optional[Dict]:
        """Generate a high-confidence plan using LLM's internal knowledge."""
        
        # Build tools description for context
        tools_desc = "\n".join([
            f"- {name}: {desc.get('description', 'No description')}" 
            for name, desc in available_tools.items()
        ])
        
        # Build context section with recent results and failures
        context_section = ""
        if recent_results:
            result_lines = []
            for r in recent_results[-5:]:
                tool_name = r.get('tool', 'tool')
                output = r.get('output', '')[:150] if r.get('output') else ''
                if output:
                    result_lines.append(f"- {tool_name}: {output}")
            if result_lines:
                context_section += "RECENT SUCCESSFUL RESULTS (use these instead of re-executing):\n" + "\n".join(result_lines) + "\n\n"
        
        if failed_actions:
            fail_lines = []
            for f in failed_actions[-5:]:
                tool_name = f.get('tool', 'tool')
                error = f.get('error', 'failed')[:100]
                params = f.get('parameters', {})
                param_str = f" with {params}" if params else ""
                fail_lines.append(f"- {tool_name}{param_str} failed: {error}")
            if fail_lines:
                context_section += "RECENT FAILURES (DO NOT retry these):\n" + "\n".join(fail_lines) + "\n\n"
        
        prompt = PLAN_PROMPT.format(
            tools_description=tools_desc,
            context_section=context_section.strip() if context_section.strip() else "No recent context available.",
            user_request=user_request
        )
        
        try:
            # Force JSON output via prompt engineering (json_mode not supported by all models)
            response = self.brain.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Low temp for deterministic planning
            )
            
            # Extract content from brain response dict
            if isinstance(response, dict):
                if not response.get('success', False):
                    logger.error(f"Brain chat failed: {response.get('error', 'Unknown error')}")
                    return None
                # Get the actual content string from the response dict
                response_content = response.get('content', '')
                if not response_content:
                    logger.error("Empty content in brain response")
                    return None
                response = response_content
            
            # Use robust JSON parsing with multiple fallback strategies
            plan = parse_json_safely(response, default=None)
            
            if plan is None:
                logger.error(f"Failed to parse JSON from LLM response")
                return None
            
            # Validate plan structure
            is_valid, error_msg = validate_plan_structure(plan)
            if not is_valid:
                logger.error(f"Invalid plan structure: {error_msg}")
                return None
                
            logger.info(f"Plan generated with {len(plan['steps'])} steps (Confidence: {plan.get('confidence', 'unknown')})")
            if plan.get('corrections'):
                logger.info(f"Corrections made: {plan['corrections']}")
            
            return plan
            
        except Exception as e:
            logger.error(f"Failed to generate plan: {e}")
            return None

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
