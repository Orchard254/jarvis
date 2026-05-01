"""
Planner - Task decomposer and plan generator.
Breaks complex goals into executable tool steps.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class TaskPlanner:
    """
    Decomposes complex goals into sequences of tool calls.
    Uses LLM for planning with structured output.
    """
    
    def __init__(self, ollama_client=None, tool_registry=None):
        """
        Initialize the task planner.
        
        Args:
            ollama_client: OllamaClient instance for planning
            tool_registry: ToolRegistry instance for available tools
        """
        self.ollama_client = ollama_client
        self.tool_registry = tool_registry
        self.plan_history = []
    
    def set_client(self, client) -> None:
        """Set the Ollama client."""
        self.ollama_client = client
    
    def set_tool_registry(self, registry) -> None:
        """Set the tool registry."""
        self.tool_registry = registry
    
    def create_plan(self, goal: str, context: str = None,
                    max_steps: int = 10) -> Dict[str, Any]:
        """
        Create a plan to achieve a goal.
        
        Args:
            goal: The goal to achieve
            context: Additional context or constraints
            max_steps: Maximum number of steps in the plan
            
        Returns:
            Dictionary with plan:
            {
                'success': bool,
                'goal': str,
                'steps': list of step dictionaries,
                'estimated_duration': str,
                'complexity': 'simple' | 'moderate' | 'complex',
                'reasoning': str
            }
        """
        if self.ollama_client is None:
            return {
                'success': False,
                'error': 'No Ollama client configured',
                'steps': []
            }
        
        # Get available tools
        available_tools = []
        if self.tool_registry:
            tools = self.tool_registry.list_tools()
            available_tools = [
                {
                    'name': t['name'],
                    'description': t['description'],
                    'params': list(t.get('parameters', {}).keys())
                }
                for t in tools
            ]
        
        # Build planning prompt
        tools_str = "\n".join([
            f"- {t['name']}: {t['description']} (params: {', '.join(t['params'])})"
            for t in available_tools[:30]  # Limit to prevent token overflow
        ])
        
        context_str = f"\nContext: {context}" if context else ""
        
        prompt = f"""You are a task planner. Break down the following goal into specific tool calls.

Goal: "{goal}"{context_str}

Available Tools:
{tools_str}

Create a step-by-step plan. Each step should use exactly one tool with its parameters.
Consider:
- Prerequisites (what must be done first)
- Dependencies between steps
- Error handling where appropriate
- Verification after important actions

Respond in JSON format:
{{
    "success": true,
    "goal": "the original goal",
    "steps": [
        {{
            "step_number": 1,
            "tool": "tool_name",
            "params": {{"param1": "value1", "param2": "value2"}},
            "description": "what this step does",
            "expected_outcome": "what we expect to happen"
        }}
    ],
    "estimated_duration": "e.g., 30 seconds, 2 minutes",
    "complexity": "simple/moderate/complex",
    "reasoning": "explanation of the plan strategy"
}}

Limit to {max_steps} steps maximum. If the goal requires more, note that in reasoning."""
        
        try:
            response = self.ollama_client.chat(
                messages=[{'role': 'user', 'content': prompt}],
                response_format='json'
            )
            
            content = response.get('content', '{}')
            
            import json
            try:
                result = json.loads(content)
                
                # Validate the plan
                validated_result = self._validate_plan(result, goal)
                
                # Store in history
                self.plan_history.append({
                    'goal': goal,
                    'plan': validated_result,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Keep history bounded
                if len(self.plan_history) > 20:
                    self.plan_history = self.plan_history[-20:]
                
                return validated_result
                
            except json.JSONDecodeError as e:
                return {
                    'success': False,
                    'error': f'Failed to parse plan: {str(e)}',
                    'steps': []
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'steps': []
            }
    
    def _validate_plan(self, plan: Dict[str, Any], 
                       goal: str) -> Dict[str, Any]:
        """Validate and normalize a plan."""
        result = {
            'success': plan.get('success', False),
            'goal': plan.get('goal', goal),
            'steps': [],
            'estimated_duration': plan.get('estimated_duration', 'Unknown'),
            'complexity': plan.get('complexity', 'moderate'),
            'reasoning': plan.get('reasoning', '')
        }
        
        steps = plan.get('steps', [])
        
        for i, step in enumerate(steps):
            validated_step = {
                'step_number': step.get('step_number', i + 1),
                'tool': step.get('tool', ''),
                'params': step.get('params', {}),
                'description': step.get('description', ''),
                'expected_outcome': step.get('expected_outcome', '')
            }
            
            # Validate tool exists
            if self.tool_registry and validated_step['tool']:
                if not self.tool_registry.tool_exists(validated_step['tool']):
                    validated_step['warning'] = f"Unknown tool: {validated_step['tool']}"
            
            result['steps'].append(validated_step)
        
        return result
    
    def refine_plan(self, plan: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        """
        Refine a plan based on feedback.
        
        Args:
            plan: Original plan
            feedback: Feedback about what to improve
            
        Returns:
            Refined plan
        """
        if self.ollama_client is None:
            return plan
        
        goal = plan.get('goal', '')
        steps = plan.get('steps', [])
        
        steps_str = "\n".join([
            f"{i+1}. {s.get('tool', '')}: {s.get('params', {})}"
            for i, s in enumerate(steps)
        ])
        
        prompt = f"""Refine this plan based on the feedback.

Original Goal: {goal}

Current Plan:
{steps_str}

Feedback: {feedback}

Provide an improved plan in the same JSON format as the original."""
        
        try:
            response = self.ollama_client.chat(
                messages=[{'role': 'user', 'content': prompt}],
                response_format='json'
            )
            
            import json
            result = json.loads(response.get('content', '{}'))
            return self._validate_plan(result, goal)
            
        except Exception:
            return plan
    
    def replan_after_failure(self, original_plan: Dict[str, Any],
                             failed_step: int, error: str) -> Dict[str, Any]:
        """
        Create a new plan after a step failure.
        
        Args:
            original_plan: The original plan
            failed_step: Index of the failed step
            error: Error message from the failure
            
        Returns:
            New plan
        """
        goal = original_plan.get('goal', '')
        
        completed_steps = original_plan.get('steps', [])[:failed_step]
        
        completed_str = "\n".join([
            f"{i+1}. {s.get('tool', '')}: {s.get('params', {})} - COMPLETED"
            for i, s in enumerate(completed_steps)
        ]) if completed_steps else "None"
        
        if self.ollama_client:
            prompt = f"""The following plan failed at step {failed_step + 1}.

Goal: {goal}

Completed Steps:
{completed_str}

Failed Step: {original_plan['steps'][failed_step].get('tool', '')}
Error: {error}

Create a new plan to achieve the original goal, accounting for what's already been done.
You may need to:
- Undo any partial effects from the failed step
- Try an alternative approach
- Skip already-completed steps

Respond in JSON format with the new plan."""
            
            try:
                response = self.ollama_client.chat(
                    messages=[{'role': 'user', 'content': prompt}],
                    response_format='json'
                )
                
                import json
                result = json.loads(response.get('content', '{}'))
                return self._validate_plan(result, goal)
                
            except Exception:
                pass
        
        # Fallback: return remaining steps
        remaining_steps = original_plan.get('steps', [])[failed_step + 1:]
        return {
            'success': True,
            'goal': goal,
            'steps': remaining_steps,
            'estimated_duration': 'Unknown',
            'complexity': 'moderate',
            'reasoning': 'Fallback to remaining original steps'
        }
    
    def get_plan_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent plan history."""
        return self.plan_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear plan history."""
        self.plan_history = []


# Singleton instance
_planner_instance = None

def get_planner(ollama_client=None, tool_registry=None) -> TaskPlanner:
    """Get the singleton TaskPlanner instance."""
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = TaskPlanner(ollama_client, tool_registry)
    else:
        if ollama_client:
            _planner_instance.set_client(ollama_client)
        if tool_registry:
            _planner_instance.set_tool_registry(tool_registry)
    return _planner_instance
