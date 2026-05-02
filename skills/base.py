"""
Base Skill - Abstract base class for all JARVIS skills.
Skills are specialized capabilities with their own prompts and state management.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime


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
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the specialized system prompt for this skill.
        
        Returns:
            System prompt string
        """
        pass
    
    @abstractmethod
    def can_handle(self, user_input: str, context: Dict[str, Any] = None) -> bool:
        """
        Check if this skill can handle the given request.
        
        Args:
            user_input: User's request
            context: Additional context
            
        Returns:
            True if skill can handle the request
        """
        pass
    
    @abstractmethod
    def execute(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute the skill.
        
        Args:
            user_input: User's request
            context: Additional context
            
        Returns:
            Result dictionary with success, output, error keys
        """
        pass
    
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
    
    def cleanup(self) -> None:
        """
        Clean up after skill execution.
        Called after execute() regardless of success/failure.
        """
        self.last_used = datetime.now()
        
        # Store in history
        self.history.append({
            'timestamp': self.last_used.isoformat(),
            'state': self.state.copy()
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
    
    def rollback(self) -> Dict[str, Any]:
        """
        Rollback any changes made by this skill.
        Override in subclasses that need custom rollback.
        
        Returns:
            Result dictionary
        """
        return {
            'success': True,
            'output': f'Skill {self.name} rolled back successfully',
            'error': None
        }
    
    def recover_from_error(self, error: Exception, 
                           context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Attempt to recover from an error.
        Override in subclasses for custom error recovery.
        
        Args:
            error: The exception that occurred
            context: Error context
            
        Returns:
            Recovery result dictionary
        """
        return {
            'success': False,
            'output': None,
            'error': str(error),
            'recovery_attempted': True
        }
    
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
            'history_length': len(self.history)
        }
    
    def reset(self) -> None:
        """Reset the skill state."""
        self.state = {}
    
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
