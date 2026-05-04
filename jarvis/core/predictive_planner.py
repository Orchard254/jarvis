"""
Predictive Planner - Leverages LLM's internal knowledge to generate
high-confidence execution plans before acting.
"""
import json
import logging
from typing import Dict, List, Optional, Any
from jarvis.core.brain import Brain

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
6. OUTPUT ONLY JSON: No markdown, no explanations, just raw JSON.

AVAILABLE TOOLS:
{tools_description}

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

    def generate_plan(self, user_request: str, available_tools: Dict[str, Any]) -> Optional[Dict]:
        """Generate a high-confidence plan using LLM's internal knowledge."""
        
        # Build tools description for context
        tools_desc = "\n".join([
            f"- {name}: {desc.get('description', 'No description')}" 
            for name, desc in available_tools.items()
        ])
        
        prompt = PLAN_PROMPT.format(
            tools_description=tools_desc,
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
            
            # Parse JSON from the content string
            if isinstance(response, str):
                # Extract JSON from markdown code blocks if present
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0]
                
                plan = json.loads(response.strip())
            else:
                plan = response
            
            # Validate plan structure
            if not isinstance(plan, dict):
                logger.error(f"Invalid plan structure (not a dict): {type(plan)}")
                return None
            
            if "steps" not in plan:
                logger.error(f"Invalid plan structure (no 'steps' key): {plan.keys() if hasattr(plan, 'keys') else 'N/A'}")
                return None
                
            logger.info(f"Plan generated with {len(plan['steps'])} steps (Confidence: {plan.get('confidence', 'unknown')})")
            if plan.get('corrections'):
                logger.info(f"Corrections made: {plan['corrections']}")
            
            return plan
            
        except Exception as e:
            logger.error(f"Failed to generate plan: {e}")
            return None

    def execute_plan(self, plan: Dict, tool_executor) -> Dict[str, Any]:
        """Execute a validated plan step-by-step."""
        results = []
        success = True
        
        logger.info(f"Starting execution of planned task: {plan.get('goal')}")
        
        for i, step in enumerate(plan.get("steps", [])):
            tool_name = step.get("tool")
            params = step.get("params", {})
            
            if not tool_name:
                logger.warning(f"Step {i+1} missing tool name, skipping.")
                continue
            
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

    def _generate_summary(self, plan: Dict, results: List[Dict]) -> str:
        """Generate a natural language summary of the execution."""
        successful_steps = sum(1 for r in results if r["success"])
        total_steps = len(results)
        
        if successful_steps == total_steps:
            return f"Successfully completed '{plan.get('goal')}' in {total_steps} steps."
        else:
            failed_tools = [r["tool"] for r in results if not r["success"]]
            return f"Partially completed '{plan.get('goal')}'. Failed at: {', '.join(failed_tools)}."
