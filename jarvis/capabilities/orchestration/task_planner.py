"""
task_planner: Breaks goal into steps

Uses GPT-OSS 120B to decompose complex goals into executable steps
using available capabilities.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Any
import time

logger = logging.getLogger(__name__)


@dataclass
class TaskStep:
    """A single step in a task plan."""
    step_id: int
    description: str
    capability: str
    parameters: dict
    dependencies: list[int] = field(default_factory=list)
    expected_output: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "step_id": self.step_id,
            "description": self.description,
            "capability": self.capability,
            "parameters": self.parameters,
            "dependencies": self.dependencies,
            "expected_output": self.expected_output
        }


@dataclass 
class TaskPlan:
    """Complete plan for accomplishing a goal."""
    goal: str
    steps: list[TaskStep]
    estimated_duration: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "goal": self.goal,
            "steps": [step.to_dict() for step in self.steps],
            "estimated_duration": self.estimated_duration,
            "created_at": self.created_at
        }


class TaskPlanner:
    """
    Decomposes high-level goals into executable capability steps.
    
    This is the strategic component that breaks down complex user requests
    into a sequence of capability invocations. It uses GPT-OSS 120B for
    intelligent planning when available, with fallback heuristics.
    """
    
    def __init__(self, available_capabilities: list[str], reasoning_model=None):
        """
        Initialize the TaskPlanner.
        
        Args:
            available_capabilities: List of capability names available for use
            reasoning_model: GPT-OSS 120B model instance for planning
        """
        self.available_capabilities = available_capabilities
        self.reasoning_model = reasoning_model
        self._plan_history = []
    
    def execute(self, goal: str, context: Optional[dict] = None,
                **kwargs) -> dict:
        """
        Execute task planning.
        
        Args:
            goal: The high-level goal to accomplish
            context: Optional context about current state
            
        Returns:
            Planning result with ordered steps
        """
        try:
            plan = self.plan(goal, context)
            
            # Store in history
            self._plan_history.append({
                "goal": goal,
                "timestamp": time.time(),
                "num_steps": len(plan.steps)
            })
            
            return {
                "success": True,
                "output": plan.to_dict()
            }
        except Exception as e:
            logger.error(f"Task planning failed: {e}")
            return {"success": False, "error": str(e)}
    
    def plan(self, goal: str, context: Optional[dict] = None) -> TaskPlan:
        """
        Decompose a goal into executable steps.
        
        Args:
            goal: The high-level goal to accomplish
            context: Optional context about current state
            
        Returns:
            TaskPlan with ordered steps and dependencies
        """
        logger.info(f"Planning task: {goal[:50]}...")
        
        # Use reasoning model if available
        if self.reasoning_model:
            plan = self._plan_with_model(goal, context)
        else:
            # Fallback to heuristic planning
            plan = self._plan_heuristic(goal, context)
        
        logger.info(f"Generated plan with {len(plan.steps)} steps")
        return plan
    
    def _plan_with_model(self, goal: str, context: Optional[dict]) -> TaskPlan:
        """
        Generate plan using GPT-OSS 120B model.
        
        Args:
            goal: The high-level goal
            context: Optional context information
            
        Returns:
            TaskPlan from model inference
        """
        prompt = self._build_planning_prompt(goal, context)
        
        # Use GPT-OSS 120B for complex planning (better reasoning)
        try:
            from jarvis.models import get_reasoning_model
            planner = get_reasoning_model()
            
            response = planner.generate_json(prompt)
            return self._parse_model_plan_dict(response, goal)
        except Exception as e:
            logger.warning(f"Model planning failed, falling back to heuristic: {e}")
            return self._plan_heuristic(goal, context)
    
    def _plan_heuristic(self, goal: str, context: Optional[dict]) -> TaskPlan:
        """
        Generate plan using rule-based heuristics.
        
        Args:
            goal: The high-level goal
            context: Optional context information
            
        Returns:
            TaskPlan based on pattern matching
        """
        text_lower = goal.lower()
        steps = []
        step_id = 1
        
        # Pattern: Search and save information
        if any(word in text_lower for word in ["search", "find"]) and \
           any(word in text_lower for word in ["save", "write", "store"]):
            steps.extend([
                TaskStep(
                    step_id=step_id,
                    description="Search for information",
                    capability="web_search",
                    parameters={"query": goal},
                    expected_output="Search results"
                ),
                TaskStep(
                    step_id=step_id + 1,
                    description="Save findings to file",
                    capability="file_writer",
                    parameters={"content": "${search_results}"},
                    dependencies=[step_id],
                    expected_output="Saved file path"
                )
            ])
            step_id += 2
        
        # Pattern: Open application and do something
        elif any(word in text_lower for word in ["open", "launch"]) and \
             any(word in text_lower for word in ["app", "program", "application"]):
            app_name = self._extract_app_name(goal)
            steps.append(TaskStep(
                step_id=step_id,
                description=f"Launch {app_name} application",
                capability="process_manager",
                parameters={"action": "start", "process_name": app_name},
                expected_output="Process started"
            ))
            step_id += 1
        
        # Pattern: Take screenshot and analyze
        elif any(word in text_lower for word in ["screenshot", "capture"]) and \
             any(word in text_lower for word in ["analyze", "what do you see"]):
            steps.extend([
                TaskStep(
                    step_id=step_id,
                    description="Capture screen",
                    capability="screen_capture",
                    parameters={},
                    expected_output="Screenshot image"
                ),
                TaskStep(
                    step_id=step_id + 1,
                    description="Analyze screen content",
                    capability="vision_analyzer",
                    parameters={"image": "${screenshot}"},
                    dependencies=[step_id],
                    expected_output="Analysis results"
                )
            ])
            step_id += 2
        
        # Pattern: System status check
        elif any(word in text_lower for word in ["status", "check", "system info"]):
            steps.append(TaskStep(
                step_id=step_id,
                description="Get system information",
                capability="system_info",
                parameters={"info_type": "all"},
                expected_output="System metrics"
            ))
        
        # Pattern: File operations
        elif any(word in text_lower for word in ["read", "open file"]):
            steps.append(TaskStep(
                step_id=step_id,
                description="Read file content",
                capability="file_reader",
                parameters={"path": self._extract_path(goal)},
                expected_output="File content"
            ))
        
        # Pattern: Terminal command execution
        elif any(word in text_lower for word in ["run", "execute", "command"]):
            steps.append(TaskStep(
                step_id=step_id,
                description="Execute terminal command",
                capability="run_terminal_command",
                parameters={"command": self._extract_command(goal)},
                expected_output="Command output"
            ))
        
        # Default: Single step analysis
        if not steps:
            steps.append(TaskStep(
                step_id=step_id,
                description=f"Process: {goal}",
                capability="reasoning_engine",
                parameters={"query": goal},
                expected_output="Response"
            ))
        
        # Estimate duration (5 seconds per step baseline)
        estimated_duration = len(steps) * 5.0
        
        return TaskPlan(
            goal=goal,
            steps=steps,
            estimated_duration=estimated_duration
        )
    
    def _build_planning_prompt(self, goal: str, context: Optional[dict]) -> str:
        """Build prompt for GPT-OSS 120B planning."""
        prompt = f"""You are a task planner for JARVIS, a desktop assistant.
Available capabilities: {', '.join(self.available_capabilities)}

Your job is to break down complex goals into executable steps using these capabilities.

Goal: "{goal}"
{"Context: " + str(context) if context else ""}

Create a step-by-step plan. For each step, specify:
1. step_id: Sequential number
2. description: What this step does
3. capability: Which capability to use
4. parameters: Parameters for the capability
5. dependencies: List of step_ids this depends on (if any)

Respond with JSON array of steps:
[
  {{
    "step_id": 1,
    "description": "...",
    "capability": "...",
    "parameters": {{}},
    "dependencies": []
  }}
]"""
        
        return prompt
    
    def _parse_model_plan(self, response: str, goal: str) -> TaskPlan:
        """Parse model response string into TaskPlan."""
        import json
        try:
            # Extract JSON from response
            start = response.find('[')
            end = response.rfind(']') + 1
            if start >= 0 and end > start:
                steps_data = json.loads(response[start:end])
                
                steps = []
                for step_data in steps_data:
                    steps.append(TaskStep(
                        step_id=step_data.get('step_id', len(steps) + 1),
                        description=step_data.get('description', ''),
                        capability=step_data.get('capability', 'reasoning_engine'),
                        parameters=step_data.get('parameters', {}),
                        dependencies=step_data.get('dependencies', [])
                    ))
                
                return TaskPlan(
                    goal=goal,
                    steps=steps,
                    estimated_duration=len(steps) * 5.0
                )
        except Exception as e:
            logger.warning(f"Failed to parse model plan: {e}")
        
        return self._plan_heuristic(goal, None)
    
    def _parse_model_plan_dict(self, response_dict: dict, goal: str) -> TaskPlan:
        """Parse model response dictionary into TaskPlan."""
        import json
        try:
            # Handle both direct list and dict with 'steps' key
            steps_data = response_dict if isinstance(response_dict, list) else response_dict.get('steps', [])
            
            steps = []
            for step_data in steps_data:
                steps.append(TaskStep(
                    step_id=step_data.get('step_id', len(steps) + 1),
                    description=step_data.get('description', ''),
                    capability=step_data.get('capability', 'reasoning_engine'),
                    parameters=step_data.get('parameters', {}),
                    dependencies=step_data.get('dependencies', [])
                ))
            
            return TaskPlan(
                goal=goal,
                steps=steps,
                estimated_duration=len(steps) * 5.0
            )
        except Exception as e:
            logger.warning(f"Failed to parse model plan dict: {e}")
        
        return self._plan_heuristic(goal, None)
    
    def _extract_app_name(self, text: str) -> str:
        """Extract application name from text."""
        # Simple extraction - would be better with model
        keywords = ["open", "launch", "start", "app", "program", "application"]
        words = text.split()
        for i, word in enumerate(words):
            if word.lower() in keywords and i + 1 < len(words):
                return words[i + 1].strip('\'"')
        return "application"
    
    def _extract_path(self, text: str) -> str:
        """Extract file path from text."""
        import re
        # Look for paths in quotes or common patterns
        match = re.search(r'["\']([^"\']*\.?\w+)["\']', text)
        if match:
            return match.group(1)
        return "/tmp/default.txt"
    
    def _extract_command(self, text: str) -> str:
        """Extract terminal command from text."""
        # Simple extraction after command keywords
        keywords = ["run", "execute", "command"]
        for keyword in keywords:
            if keyword in text.lower():
                idx = text.lower().find(keyword)
                return text[idx + len(keyword):].strip()
        return "echo 'Hello'"
    
    def get_plan_history(self) -> list[dict]:
        """Get history of generated plans."""
        return self._plan_history.copy()
    
    def clear_history(self):
        """Clear plan history."""
        self._plan_history.clear()


# Singleton instance
_task_planner_instance = None


def get_task_planner(available_capabilities: list[str] = None, 
                     reasoning_model=None) -> TaskPlanner:
    """Get or create TaskPlanner singleton."""
    global _task_planner_instance
    if _task_planner_instance is None:
        _task_planner_instance = TaskPlanner(
            available_capabilities=available_capabilities or [],
            reasoning_model=reasoning_model
        )
    return _task_planner_instance
