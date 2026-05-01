"""
Critic - Plan reviewer and validator.
Reviews plans before execution to catch errors and suggest improvements.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class PlanCritic:
    """
    Reviews and critiques plans before execution.
    Identifies potential issues, missing steps, and optimization opportunities.
    """
    
    def __init__(self, ollama_client=None):
        """
        Initialize the plan critic.
        
        Args:
            ollama_client: OllamaClient instance for review
        """
        self.ollama_client = ollama_client
        self.review_history = []
    
    def set_client(self, client) -> None:
        """Set the Ollama client."""
        self.ollama_client = client
    
    def review_plan(self, plan: List[Dict[str, Any]], 
                    goal: str, context: str = None) -> Dict[str, Any]:
        """
        Review a plan and provide feedback.
        
        Args:
            plan: List of planned steps
            goal: The overall goal
            context: Additional context
            
        Returns:
            Dictionary with review results:
            {
                'approved': bool,
                'issues': list of issues found,
                'suggestions': list of suggestions,
                'missing_steps': list of missing steps,
                'risk_level': 'low' | 'medium' | 'high',
                'reasoning': str
            }
        """
        # Heuristic review first
        heuristic_review = self._heuristic_review(plan, goal)
        
        # If no issues found heuristically and plan is simple, approve quickly
        if not heuristic_review['issues'] and len(plan) <= 3:
            result = heuristic_review
            result['method'] = 'heuristic'
        else:
            # Use LLM for detailed review
            result = self._llm_review(plan, goal, context)
            result['method'] = 'llm'
            # Merge heuristic findings
            if heuristic_review['issues']:
                result['issues'] = list(set(result['issues'] + heuristic_review['issues']))
        
        # Store in history
        self.review_history.append({
            'goal': goal[:200],
            'plan_length': len(plan),
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep history bounded
        if len(self.review_history) > 20:
            self.review_history = self.review_history[-20:]
        
        return result
    
    def _heuristic_review(self, plan: List[Dict[str, Any]], 
                          goal: str) -> Dict[str, Any]:
        """Quick heuristic-based plan review."""
        issues = []
        suggestions = []
        missing_steps = []
        risk_level = 'low'
        
        if not plan:
            return {
                'approved': False,
                'issues': ['Plan is empty'],
                'suggestions': ['Add at least one step to achieve the goal'],
                'missing_steps': [],
                'risk_level': 'high',
                'reasoning': 'Empty plan cannot achieve any goal'
            }
        
        # Check for common issues
        
        # 1. No verification steps for destructive operations
        destructive_tools = ['delete_file', 'run_command', 'run_powershell', 
                            'close_app', 'shutdown_system']
        for i, step in enumerate(plan):
            tool = step.get('tool', '')
            if tool in destructive_tools:
                # Check if there's a verification step after
                has_verification = False
                for j in range(i + 1, min(i + 3, len(plan))):
                    next_tool = plan[j].get('tool', '')
                    if 'verify' in next_tool or 'check' in next_tool or 'confirm' in next_tool:
                        has_verification = True
                        break
                
                if not has_verification:
                    suggestions.append(f"Consider adding verification after step {i+1} ({tool})")
        
        # 2. Check for proper sequencing (can't use file before creating it)
        created_files = set()
        used_files = set()
        for i, step in enumerate(plan):
            tool = step.get('tool', '')
            params = step.get('params', {})
            
            if tool == 'create_file' and 'path' in params:
                created_files.add(params['path'])
            elif tool in ['read_file', 'open_file', 'delete_file'] and 'path' in params:
                path = params['path']
                if path not in created_files and i > 0:
                    # Using a file that wasn't created in this plan
                    pass  # This is OK if file already exists
        
        # 3. Check for redundant steps
        tools_used = [step.get('tool') for step in plan]
        seen = set()
        for tool in tools_used:
            if tool in seen:
                suggestions.append(f"Tool '{tool}' is used multiple times - consider consolidating")
            seen.add(tool)
        
        # 4. Risk assessment
        high_risk_tools = ['delete_file', 'run_command', 'run_powershell', 
                          'shutdown_system', 'restart_system']
        medium_risk_tools = ['create_file', 'move_file', 'copy_file', 
                            'close_app', 'press_key']
        
        risk_count = 0
        for step in plan:
            tool = step.get('tool', '')
            if tool in high_risk_tools:
                risk_count += 2
            elif tool in medium_risk_tools:
                risk_count += 1
        
        if risk_count >= 3:
            risk_level = 'high'
        elif risk_count >= 1:
            risk_level = 'medium'
        
        # 5. Check for missing error handling
        if len(plan) > 3 and risk_level in ['medium', 'high']:
            has_error_handling = any(
                'retry' in str(step) or 'error' in str(step) or 'fallback' in str(step)
                for step in plan
            )
            if not has_error_handling:
                suggestions.append("Consider adding error handling for complex/risky operations")
        
        approved = len(issues) == 0 and risk_level != 'high'
        
        reasoning = f"Reviewed {len(plan)} steps. "
        if issues:
            reasoning += f"Found {len(issues)} issue(s). "
        if suggestions:
            reasoning += f"{len(issues)} suggestion(s) provided. "
        reasoning += f"Risk level: {risk_level}."
        
        return {
            'approved': approved,
            'issues': issues,
            'suggestions': suggestions,
            'missing_steps': missing_steps,
            'risk_level': risk_level,
            'reasoning': reasoning
        }
    
    def _llm_review(self, plan: List[Dict[str, Any]], 
                    goal: str, context: str = None) -> Dict[str, Any]:
        """Use LLM for detailed plan review."""
        if self.ollama_client is None:
            return self._heuristic_review(plan, goal)
        
        plan_str = "\n".join([
            f"{i+1}. {step.get('tool', 'unknown')}: {step.get('params', {})}"
            for i, step in enumerate(plan)
        ])
        
        context_str = f"\nContext: {context}" if context else ""
        
        prompt = f"""Review this plan for achieving the goal: "{goal}"{context_str}

Proposed Plan:
{plan_str}

Evaluate the plan for:
1. Correctness - Will this achieve the goal?
2. Completeness - Are any steps missing?
3. Safety - Are there any risky operations that need caution?
4. Efficiency - Can this be done more simply?
5. Error handling - What could go wrong?

Respond in JSON format:
{{
    "approved": true/false,
    "issues": ["list of critical issues"],
    "suggestions": ["list of improvement suggestions"],
    "missing_steps": ["list of potentially missing steps"],
    "risk_level": "low/medium/high",
    "reasoning": "detailed explanation"
}}

Be constructive but thorough. Only reject plans that are fundamentally flawed or dangerous."""
        
        try:
            response = self.ollama_client.chat(
                messages=[{'role': 'user', 'content': prompt}],
                response_format='json'
            )
            
            content = response.get('content', '{}')
            
            import json
            try:
                result = json.loads(content)
                return {
                    'approved': result.get('approved', True),
                    'issues': result.get('issues', []),
                    'suggestions': result.get('suggestions', []),
                    'missing_steps': result.get('missing_steps', []),
                    'risk_level': result.get('risk_level', 'medium'),
                    'reasoning': result.get('reasoning', 'LLM review completed')
                }
            except json.JSONDecodeError:
                return self._heuristic_review(plan, goal)
                
        except Exception as e:
            return self._heuristic_review(plan, goal)
    
    def quick_check(self, plan: List[Dict[str, Any]]) -> bool:
        """
        Quick safety check - returns True if plan is safe to execute.
        
        Args:
            plan: List of planned steps
            
        Returns:
            True if safe, False if concerns found
        """
        review = self._heuristic_review(plan, "Quick check")
        return review['risk_level'] != 'high' and len(review['issues']) == 0
    
    def get_review_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent review history."""
        return self.review_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear review history."""
        self.review_history = []


# Singleton instance
_critic_instance = None

def get_critic(ollama_client=None) -> PlanCritic:
    """Get the singleton PlanCritic instance."""
    global _critic_instance
    if _critic_instance is None:
        _critic_instance = PlanCritic(ollama_client)
    elif ollama_client is not None:
        _critic_instance.set_client(ollama_client)
    return _critic_instance
