"""
Planner - Task decomposer and plan generator.
Breaks complex goals into executable tool steps.

ONLY used for complex multi-step tasks (4+ tools or multi-step with dependencies).
Not for simple single-tool requests.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict


@dataclass
class ExecutionStep:
    """
    A single step in an execution plan.
    
    Attributes:
        id: Unique identifier for this step
        tool_or_skill: Name of the tool or skill to execute
        params: Parameters to pass to the tool
        depends_on: List of step IDs that must complete before this step
        success_criteria: How to verify this step succeeded
        fallback_strategy: What to do if this step fails
        parallelizable: Whether this step can run in parallel with others
    """
    id: str
    tool_or_skill: str
    params: Dict[str, Any]
    depends_on: List[str] = field(default_factory=list)
    success_criteria: str = ""
    fallback_strategy: str = ""
    parallelizable: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'tool_or_skill': self.tool_or_skill,
            'params': self.params,
            'depends_on': self.depends_on,
            'success_criteria': self.success_criteria,
            'fallback_strategy': self.fallback_strategy,
            'parallelizable': self.parallelizable
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionStep':
        """Create from dictionary."""
        return cls(
            id=data.get('id', ''),
            tool_or_skill=data.get('tool_or_skill', ''),
            params=data.get('params', {}),
            depends_on=data.get('depends_on', []),
            success_criteria=data.get('success_criteria', ''),
            fallback_strategy=data.get('fallback_strategy', ''),
            parallelizable=data.get('parallelizable', False)
        )


@dataclass
class ExecutionGraph:
    """
    A directed acyclic graph representing an execution plan.
    
    Attributes:
        goal: The overall goal to achieve
        steps: List of execution steps
        max_depth: Maximum depth of the dependency graph (max 10)
        total_estimated_duration: Estimated total duration in seconds
    """
    goal: str
    steps: List[ExecutionStep] = field(default_factory=list)
    max_depth: int = 0
    total_estimated_duration: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'goal': self.goal,
            'steps': [step.to_dict() for step in self.steps],
            'max_depth': self.max_depth,
            'total_estimated_duration': self.total_estimated_duration
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionGraph':
        """Create from dictionary."""
        steps = [ExecutionStep.from_dict(s) for s in data.get('steps', [])]
        return cls(
            goal=data.get('goal', ''),
            steps=steps,
            max_depth=data.get('max_depth', 0),
            total_estimated_duration=data.get('total_estimated_duration', 0.0)
        )
    
    def get_parallel_groups(self) -> List[List[str]]:
        """
        Get groups of step IDs that can be executed in parallel.
        Returns list of lists, where each inner list contains step IDs
        that can run concurrently.
        """
        if not self.steps:
            return []
        
        # Build dependency map
        step_map = {step.id: step for step in self.steps}
        completed = set()
        groups = []
        
        while len(completed) < len(self.steps):
            # Find all steps whose dependencies are satisfied
            ready = []
            for step in self.steps:
                if step.id not in completed:
                    if all(dep in completed for dep in step.depends_on):
                        ready.append(step.id)
            
            if not ready:
                # Circular dependency or error
                break
            
            groups.append(ready)
            completed.update(ready)
        
        return groups
    
    def calculate_depth(self) -> int:
        """Calculate the maximum depth of the dependency graph."""
        if not self.steps:
            return 0
        
        step_map = {step.id: step for step in self.steps}
        depths = {}
        
        def get_depth(step_id: str, visited: set) -> int:
            if step_id in depths:
                return depths[step_id]
            
            if step_id in visited:
                return 0  # Circular dependency
            
            visited.add(step_id)
            step = step_map.get(step_id)
            if not step:
                return 0
            
            if not step.depends_on:
                depths[step_id] = 1
                return 1
            
            max_dep_depth = 0
            for dep_id in step.depends_on:
                dep_depth = get_depth(dep_id, visited)
                max_dep_depth = max(max_dep_depth, dep_depth)
            
            depths[step_id] = max_dep_depth + 1
            return depths[step_id]
        
        max_depth = 0
        for step in self.steps:
            depth = get_depth(step.id, set())
            max_depth = max(max_depth, depth)
        
        self.max_depth = max_depth
        return max_depth
    
    def validate_max_depth(self, max_allowed: int = 10) -> bool:
        """Validate that the plan depth does not exceed the maximum."""
        depth = self.calculate_depth()
        return depth <= max_allowed


class TaskPlanner:
    """
    Decomposes complex goals into sequences of tool calls.
    Uses LLM for planning with structured output.
    
    IMPORTANT: Only use for complex multi-step tasks.
    For simple single-tool requests, use direct execution instead.
    """
    
    MAX_PLAN_DEPTH = 10
    
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
        Create an ExecutionGraph plan to achieve a goal.
        
        Args:
            goal: The goal to achieve
            context: Additional context or constraints
            max_steps: Maximum number of steps in the plan (default 10)
            
        Returns:
            Dictionary with ExecutionGraph:
            {
                'success': bool,
                'execution_graph': ExecutionGraph object,
                'estimated_duration': str,
                'complexity': 'simple' | 'moderate' | 'complex',
                'reasoning': str,
                'parallel_groups': list of step ID groups for parallel execution
            }
        """
        # Enforce maximum plan depth
        if max_steps > self.MAX_PLAN_DEPTH:
            max_steps = self.MAX_PLAN_DEPTH
        
        if self.ollama_client is None:
            return {
                'success': False,
                'error': 'No Ollama client configured',
                'execution_graph': None
            }
        
        # Get ALL available tools - critical for proper planning
        available_tools = []
        if self.tool_registry:
            all_tools = self.tool_registry.get_all_tools()
            for tool in all_tools.values():
                available_tools.append({
                    'name': tool.name,
                    'description': tool.description,
                    'parameters': tool.parameters,
                    'required_params': getattr(tool, 'required_parameters', [])
                })
        
        # Build comprehensive planning prompt with FULL tool list
        tools_str = "\n".join([
            f"- {t['name']}: {t['description']}\n"
            f"  Parameters: {', '.join(t['parameters'].keys()) if t['parameters'] else 'none'}\n"
            f"  Required: {', '.join(t.get('required_params', [])) or 'none'}"
            for t in available_tools
        ])
        
        context_str = f"\nContext: {context}" if context else ""
        
        prompt = f"""You are a task planner for a complex multi-step task. Break down the following goal into specific tool calls.

Goal: "{goal}"{context_str}

Available Tools (FULL LIST - you MUST use only these tool names):
{tools_str}

IMPORTANT RULES:
1. Each step must use exactly one tool from the list above
2. Specify dependencies between steps using step IDs
3. Steps with NO dependencies should be marked as parallelizable
4. Include success criteria for each step (how to verify it worked)
5. Include fallback strategy for each step (what to do if it fails)
6. Maximum {max_steps} steps allowed
7. Plan depth cannot exceed {self.MAX_PLAN_DEPTH} levels

Consider:
- Prerequisites (what must be done first)
- Dependencies between steps
- Error handling and fallback strategies
- Verification after important actions
- Opportunities for parallel execution

Respond in JSON format:
{{
    "success": true,
    "goal": "the original goal",
    "steps": [
        {{
            "id": "step_1",
            "tool_or_skill": "exact_tool_name_from_list",
            "params": {{"param1": "value1", "param2": "value2"}},
            "depends_on": [],
            "success_criteria": "file exists with correct content",
            "fallback_strategy": "retry once then skip",
            "parallelizable": true
        }},
        {{
            "id": "step_2",
            "tool_or_skill": "another_tool",
            "params": {{"param": "value"}},
            "depends_on": ["step_1"],
            "success_criteria": "output contains expected data",
            "fallback_strategy": "use alternative approach",
            "parallelizable": false
        }}
    ],
    "estimated_duration_seconds": 120,
    "complexity": "simple/moderate/complex",
    "reasoning": "explanation of the plan strategy and why these steps were chosen"
}}

Ensure all tool names match EXACTLY from the available tools list above."""
        
        try:
            response = self.ollama_client.chat(
                messages=[{'role': 'user', 'content': prompt}],
                
            )
            
            content = response.get('content', '{}')
            
            import json
            try:
                result = json.loads(content)
                
                # Convert to ExecutionGraph
                execution_graph = self._build_execution_graph(result, goal)
                
                # Validate plan depth
                if not execution_graph.validate_max_depth(self.MAX_PLAN_DEPTH):
                    return {
                        'success': False,
                        'error': f'Plan depth ({execution_graph.max_depth}) exceeds maximum ({self.MAX_PLAN_DEPTH})',
                        'execution_graph': None
                    }
                
                # Mark steps with no dependencies as parallelizable
                for step in execution_graph.steps:
                    if not step.depends_on:
                        step.parallelizable = True
                
                # Calculate parallel groups
                parallel_groups = execution_graph.get_parallel_groups()
                
                validated_result = {
                    'success': result.get('success', False),
                    'execution_graph': execution_graph,
                    'estimated_duration': f"{execution_graph.total_estimated_duration}s",
                    'complexity': result.get('complexity', 'moderate'),
                    'reasoning': result.get('reasoning', ''),
                    'parallel_groups': parallel_groups
                }
                
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
                    'execution_graph': None
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'execution_graph': None
            }
    
    def _build_execution_graph(self, plan: Dict[str, Any], 
                                goal: str) -> ExecutionGraph:
        """Build an ExecutionGraph from a plan dictionary."""
        steps_data = plan.get('steps', [])
        steps = []
        
        for i, step_data in enumerate(steps_data):
            step = ExecutionStep(
                id=step_data.get('id', f'step_{i+1}'),
                tool_or_skill=step_data.get('tool_or_skill', step_data.get('tool', '')),
                params=step_data.get('params', {}),
                depends_on=step_data.get('depends_on', []),
                success_criteria=step_data.get('success_criteria', ''),
                fallback_strategy=step_data.get('fallback_strategy', ''),
                parallelizable=step_data.get('parallelizable', False)
            )
            steps.append(step)
        
        graph = ExecutionGraph(
            goal=plan.get('goal', goal),
            steps=steps,
            total_estimated_duration=float(plan.get('estimated_duration_seconds', 0))
        )
        
        # Calculate and validate depth
        graph.calculate_depth()
        
        return graph
    
    def should_use_planner(self, task_description: str) -> bool:
        """
        Determine if this task requires the full planner.
        
        Returns False for simple single-tool requests.
        Returns True for complex multi-step tasks.
        
        Args:
            task_description: Description of the task
            
        Returns:
            True if planner should be used, False otherwise
        """
        # Sequential indicators that suggest multi-step
        sequential_words = ['then', 'after', 'next', 'finally', 'first', 'second']
        conditional_words = ['if', 'when', 'unless', 'otherwise']
        
        task_lower = task_description.lower()
        
        # Count verbs (actions)
        action_verbs = [
            'open', 'close', 'create', 'delete', 'move', 'copy',
            'run', 'execute', 'install', 'configure', 'find', 'search',
            'download', 'upload', 'send', 'verify', 'check', 'confirm'
        ]
        
        verb_count = sum(1 for verb in action_verbs if verb in task_lower)
        
        has_sequential = any(word in task_lower for word in sequential_words)
        has_conditional = any(word in task_lower for word in conditional_words)
        
        # Complex if: 4+ actions, or has sequencing, or conditionals
        is_complex = (verb_count >= 4) or has_sequential or has_conditional
        
        return is_complex
    
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
        
        execution_graph = plan.get('execution_graph')
        if not execution_graph:
            return plan
        
        goal = execution_graph.goal
        steps = execution_graph.steps
        
        steps_str = "\n".join([
            f"{s.id}. {s.tool_or_skill}: {s.params} (depends on: {s.depends_on})"
            for s in steps
        ])
        
        prompt = f"""Refine this plan based on the feedback.

Original Goal: {goal}

Current Plan:
{steps_str}

Feedback: {feedback}

Provide an improved plan in the same JSON format with ExecutionGraph structure.
Maintain the same step ID format and dependency structure."""
        
        try:
            response = self.ollama_client.chat(
                messages=[{'role': 'user', 'content': prompt}],
                
            )
            
            import json
            result = json.loads(response.get('content', '{}'))
            return self._build_execution_graph(result, goal).to_dict()
            
        except Exception:
            return plan
    
    def replan_after_failure(self, original_plan: Dict[str, Any],
                             failed_step_id: str, error: str) -> Dict[str, Any]:
        """
        Create a new plan after a step failure.
        
        Args:
            original_plan: The original plan
            failed_step_id: ID of the failed step
            error: Error message from the failure
            
        Returns:
            New plan
        """
        execution_graph = original_plan.get('execution_graph')
        if not execution_graph:
            return original_plan
        
        goal = execution_graph.goal
        
        # Find completed steps (those before the failed one with no errors)
        failed_idx = None
        for i, step in enumerate(execution_graph.steps):
            if step.id == failed_step_id:
                failed_idx = i
                break
        
        if failed_idx is None:
            return original_plan
        
        completed_steps = execution_graph.steps[:failed_idx]
        
        completed_str = "\n".join([
            f"{s.id}. {s.tool_or_skill}: {s.params} - COMPLETED"
            for s in completed_steps
        ]) if completed_steps else "None"
        
        if self.ollama_client:
            prompt = f"""The following plan failed at step {failed_step_id}.

Goal: {goal}

Completed Steps:
{completed_str}

Failed Step: {failed_step_id}
Error: {error}

Create a new plan to achieve the original goal, accounting for what's already been done.
You may need to:
- Undo any partial effects from the failed step
- Try an alternative approach
- Skip already-completed steps

Respond in JSON format with the new ExecutionGraph structure."""
            
            try:
                response = self.ollama_client.chat(
                    messages=[{'role': 'user', 'content': prompt}],
                    
                )
                
                import json
                result = json.loads(response.get('content', '{}'))
                return self._build_execution_graph(result, goal).to_dict()
                
            except Exception:
                pass
        
        # Fallback: return remaining steps
        remaining_steps = execution_graph.steps[failed_idx + 1:]
        fallback_graph = ExecutionGraph(
            goal=goal,
            steps=remaining_steps
        )
        return fallback_graph.to_dict()
    
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
