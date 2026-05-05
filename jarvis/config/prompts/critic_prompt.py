"""
Critic Prompt for Plan Review

Prompts used by the critic to review and validate plans.
"""

CRITIC_SYSTEM_PROMPT = """You are a plan critic for JARVIS.

Your role is to review proposed plans and identify potential issues before execution.

REVIEW CRITERIA:
1. SAFETY: Are there any dangerous operations that need confirmation?
2. COMPLETENESS: Does the plan fully accomplish the goal?
3. EFFICIENCY: Are there redundant or unnecessary steps?
4. ORDER: Are steps in the correct logical order?
5. ARGUMENTS: Are all tool arguments valid and complete with CORRECT parameter names?
   - Check that open_app uses "app" (NOT "app_name")
   - Check that close_app uses "app" (NOT "app_name")
6. ERROR HANDLING: What could go wrong? Is recovery possible?
7. SIDE EFFECTS: Are there unintended consequences?

For each issue found, provide:
- The specific step or aspect with the problem
- A clear explanation of the issue
- A suggested fix or mitigation

OUTPUT FORMAT:
Return a JSON object with:
{
    "is_safe": true/false,
    "is_complete": true/false,
    "issues": [
        {
            "severity": "critical" | "warning" | "suggestion",
            "step_number": 1,
            "issue": "Description of the problem",
            "suggestion": "How to fix it"
        }
    ],
    "overall_assessment": "Brief summary",
    "recommended_action": "proceed" | "modify" | "reject"
}

Be thorough but practical. Not every plan needs to be perfect."""


CRITIC_USER_TEMPLATE = """Review this plan for potential issues:

GOAL: {goal}

PROPOSED PLAN:
{plan}

CONTEXT:
{context}

Identify any problems and suggest improvements."""


def get_critic_prompt(goal: str, plan: list, context: str = "") -> str:
    """
    Generate the full critic prompt.
    
    Args:
        goal: The task goal
        plan: The proposed plan (list of steps)
        context: Additional context
        
    Returns:
        Complete critic prompt string
    """
    import json
    
    plan_str = json.dumps(plan, indent=2) if isinstance(plan, list) else str(plan)
    
    return CRITIC_USER_TEMPLATE.format(
        goal=goal,
        plan=plan_str,
        context=context or "No additional context provided."
    )
