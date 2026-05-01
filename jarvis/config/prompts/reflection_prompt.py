"""
Reflection Prompt for Outcome Analysis

Prompts used by the reflector to analyze completed tasks.
"""

REFLECTION_SYSTEM_PROMPT = """You are a reflection assistant for JARVIS.

Your role is to analyze completed tasks and extract learnings for future improvement.

ANALYSIS AREAS:
1. OUTCOME: Was the goal achieved? To what degree?
2. EFFICIENCY: Could it have been done with fewer steps?
3. ERRORS: What went wrong? How was it handled?
4. ALTERNATIVES: Were there better approaches?
5. PATTERNS: Is this a repeatable pattern for similar tasks?
6. USER PREFERENCES: Did the user express any preferences during execution?

OUTPUT FORMAT:
Return a JSON object with:
{
    "success": true/false,
    "goal_achieved": "Description of outcome",
    "what_went_well": ["List of things that worked"],
    "what_went_wrong": ["List of issues encountered"],
    "lessons_learned": ["Key takeaways"],
    "suggested_improvements": ["How to do better next time"],
    "pattern_extracted": "Generalizable pattern if applicable",
    "confidence_score": 0.0-1.0 (how confident in success assessment)
}

Be honest about failures - they are valuable learning opportunities."""


REFLECTION_USER_TEMPLATE = """Analyze this completed task:

ORIGINAL GOAL: {goal}

EXECUTED PLAN:
{plan}

ACTUAL RESULTS:
{results}

USER FEEDBACK:
{feedback}

Extract lessons learned and suggestions for improvement."""


def get_reflection_prompt(goal: str, plan: list, results: list, 
                         feedback: str = "") -> str:
    """
    Generate the full reflection prompt.
    
    Args:
        goal: The original task goal
        plan: The plan that was executed
        results: The actual results from each step
        feedback: Any user feedback received
        
    Returns:
        Complete reflection prompt string
    """
    import json
    
    plan_str = json.dumps(plan, indent=2) if isinstance(plan, list) else str(plan)
    results_str = json.dumps(results, indent=2) if isinstance(results, list) else str(results)
    
    return REFLECTION_USER_TEMPLATE.format(
        goal=goal,
        plan=plan_str,
        results=results_str,
        feedback=feedback or "No explicit feedback provided."
    )
