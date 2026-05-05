"""
Base Skill - Abstract base class for all JARVIS skills.
Skills are specialized capabilities with their own prompts and state management.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
from dataclasses import dataclass


@dataclass
class SkillResult:
    """Result of a skill execution."""
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @classmethod
    def ok(cls, output: str = None, metadata: Dict[str, Any] = None) -> 'SkillResult':
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata)
    
    @classmethod
    def fail(cls, error: str = None, metadata: Dict[str, Any] = None) -> 'SkillResult':
        """Create a failed result."""
        return cls(success=False, error=error, metadata=metadata)


class RecoveryAction(Enum):
    """Actions that can be taken during error recovery."""
    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"
    ALTERNATIVE = "alternative"


@dataclass
class SkillStep:
    """Represents a single step in a skill's execution plan."""
    id: str
    name: str
    action: str
    params: Dict[str, Any]
    completed: bool = False
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class Recovery:
    """Represents a recovery strategy after a step failure."""
    action: RecoveryAction
    message: str
    retry_count: int = 0
    max_retries: int = 3
    alternative_step: Optional[SkillStep] = None
    skip_to_step: Optional[str] = None


class BaseSkill(ABC):
    """
    Abstract base class for all JARVIS skills.
    
    Skills differ from tools in that they:
    - Have their own specialized system prompts
    - Maintain state across multiple interactions
    - Can execute multiple tools in sequence
    - Have failure recovery mechanisms
    - Support rollback of multi-step operations
    """
    
    def __init__(self, name: str = None, description: str = None):
        """
        Initialize the skill.
        
        Args:
            name: Skill name (defaults to class name)
            description: Skill description
        """
        self.name = name or self.__class__.__name__
        self.description = description or ""
        self.state = {}
        self.history = []
        self.created_at = datetime.now()
        self.last_used = None
        self.executed_steps: List[SkillStep] = []
        self.rollback_stack: List[Tuple[str, Any]] = []
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the specialized system prompt for this skill.
        
        Returns:
            System prompt string
        """
        pass
    
    @abstractmethod
    def can_handle(self, task: str) -> float:
        """
        Check if this skill can handle the given request.
        
        Args:
            task: User's request/task description
            
        Returns:
            Confidence score from 0.0 to 1.0
        """
        pass
    
    @abstractmethod
    def plan(self, task: str) -> List[SkillStep]:
        """
        Create an ordered plan of steps to accomplish the task.
        
        Args:
            task: User's request/task description
            
        Returns:
            Ordered list of SkillStep objects
        """
        pass
    
    @abstractmethod
    def execute(self, plan: List[SkillStep]) -> Dict[str, Any]:
        """
        Execute the skill with state tracking.
        
        Args:
            plan: List of SkillStep objects to execute
            
        Returns:
            Result dictionary with success, output, error keys
        """
        pass
    
    @abstractmethod
    def handle_failure(self, step: SkillStep, error: Exception) -> Recovery:
        """
        Handle a failure during step execution.
        
        Args:
            step: The step that failed
            error: The exception that occurred
            
        Returns:
            Recovery object with action (RETRY, SKIP, ABORT, or ALTERNATIVE)
        """
        pass
    
    @abstractmethod
    def rollback(self) -> Dict[str, Any]:
        """
        Undo completed steps in reverse order.
        
        Returns:
            Result dictionary describing what was rolled back
        """
        pass
    
    @abstractmethod
    def summarize(self) -> str:
        """
        Provide a one-sentence summary of what was accomplished.
        
        Returns:
            One sentence summary string
        """
        pass
    
    def _execute_step(self, step: SkillStep) -> Dict[str, Any]:
        """
        Execute a single step with error handling.
        
        Args:
            step: The step to execute
            
        Returns:
            Step result dictionary
        """
        try:
            # Mark step as in progress
            step.completed = False
            
            # Execute the step (to be implemented by subclass)
            result = self._run_step_action(step)
            
            # Mark as completed
            step.completed = True
            step.result = result
            
            # Add to rollback stack if the step made changes
            if result.get('makes_changes', False):
                self.rollback_stack.append((step.id, result.get('undo_data')))
            
            return {
                'success': True,
                'step_id': step.id,
                'result': result
            }
            
        except Exception as e:
            step.error = str(e)
            
            # Get recovery strategy
            recovery = self.handle_failure(step, e)
            
            return {
                'success': False,
                'step_id': step.id,
                'error': str(e),
                'recovery': recovery
            }
    
    def _run_step_action(self, step: SkillStep) -> Dict[str, Any]:
        """
        Run the actual action for a step. Override in subclasses.
        
        Args:
            step: The step to run
            
        Returns:
            Action result dictionary
        """
        # Default implementation - should be overridden
        return {'output': f'Step {step.name} executed', 'makes_changes': False}
    
    def initialize(self, context: Dict[str, Any] = None) -> None:
        """
        Initialize the skill state.
        Called before execute().
        
        Args:
            context: Initial context
        """
        self.state = {
            'started_at': datetime.now().isoformat(),
            'step': 0,
            'context': context or {}
        }
        self.executed_steps = []
        self.rollback_stack = []
    
    def cleanup(self) -> None:
        """
        Clean up after skill execution.
        Called after execute() regardless of success/failure.
        """
        self.last_used = datetime.now()
        
        # Store in history
        self.history.append({
            'timestamp': self.last_used.isoformat(),
            'state': self.state.copy(),
            'steps_executed': len(self.executed_steps)
        })
        
        # Keep history bounded
        if len(self.history) > 100:
            self.history = self.history[-100:]
    
    def save_state(self, key: str, value: Any) -> None:
        """
        Save a value to skill state.
        
        Args:
            key: State key
            value: Value to store
        """
        self.state[key] = value
        self.state['last_updated'] = datetime.now().isoformat()
    
    def load_state(self, key: str, default: Any = None) -> Any:
        """
        Load a value from skill state.
        
        Args:
            key: State key
            default: Default value if key not found
            
        Returns:
            Stored value or default
        """
        return self.state.get(key, default)
    
    def update_step(self, step: int, description: str = None) -> None:
        """
        Update the current step counter.
        
        Args:
            step: Step number
            description: Optional step description
        """
        self.state['step'] = step
        if description:
            self.state[f'step_{step}_description'] = description
        self.state['last_updated'] = datetime.now().isoformat()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the skill.
        
        Returns:
            Status dictionary
        """
        return {
            'name': self.name,
            'active': bool(self.state),
            'current_step': self.state.get('step', 0),
            'created_at': self.created_at.isoformat(),
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'history_length': len(self.history),
            'steps_executed': len(self.executed_steps)
        }
    
    def reset(self) -> None:
        """Reset the skill state."""
        self.state = {}
        self.executed_steps = []
        self.rollback_stack = []
    
    def validate_input(self, user_input: str, 
                       context: Dict[str, Any] = None) -> tuple:
        """
        Validate input before execution.
        
        Args:
            user_input: User's request
            context: Additional context
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not user_input or not user_input.strip():
            return False, "Empty input"
        return True, ""
    
    def log_action(self, action: str, details: Dict[str, Any] = None) -> None:
        """
        Log an action performed by this skill.
        
        Args:
            action: Action description
            details: Additional details
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'details': details or {},
            'step': self.state.get('step', 0)
        }
        
        if 'action_log' not in self.state:
            self.state['action_log'] = []
        
        self.state['action_log'].append(log_entry)
        
        # Keep log bounded
        if len(self.state['action_log']) > 50:
            self.state['action_log'] = self.state['action_log'][-50:]


# Registry for skills
_registered_skills = {}

def register_skill(skill_class: type) -> type:
    """Decorator to register a skill class."""
    _registered_skills[skill_class.__name__] = skill_class
    return skill_class

def get_registered_skills() -> Dict[str, type]:
    """Get all registered skill classes."""
    return _registered_skills.copy()
