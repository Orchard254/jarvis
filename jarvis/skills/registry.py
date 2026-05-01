"""
Skill Registry - Loads and manages all JARVIS skills.
"""

import importlib
from typing import Dict, Any, List, Optional, Type
from pathlib import Path
from datetime import datetime


class SkillRegistry:
    """
    Registry for all available skills.
    Handles loading, discovery, and execution of skills.
    """
    
    def __init__(self):
        """Initialize the skill registry."""
        self.skills = {}
        self.skill_instances = {}
        self.loaded_at = datetime.now()
        self._builtin_path = Path(__file__).parent / 'builtin'
    
    def load_builtin_skills(self) -> int:
        """
        Load all built-in skills from the builtin directory.
        
        Returns:
            Number of skills loaded
        """
        count = 0
        
        if not self._builtin_path.exists():
            return count
        
        # Find all Python files in builtin directory
        for skill_file in self._builtin_path.glob('*.py'):
            if skill_file.name.startswith('_'):
                continue
            
            try:
                module_name = f"jarvis.skills.builtin.{skill_file.stem}"
                module = importlib.import_module(module_name)
                
                # Look for skill classes in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    
                    # Check if it's a skill class (has required methods)
                    if (isinstance(attr, type) and 
                        hasattr(attr, 'can_handle') and
                        hasattr(attr, 'execute')):
                        
                        # Register the skill
                        self.register_skill(attr_name, attr)
                        count += 1
                        
            except Exception as e:
                print(f"Failed to load skill from {skill_file}: {e}")
        
        return count
    
    def register_skill(self, name: str, skill_class: Type) -> None:
        """
        Register a skill class.
        
        Args:
            name: Skill name
            skill_class: Skill class
        """
        self.skills[name] = skill_class
        self.skill_instances[name] = None  # Lazy instantiation
    
    def get_skill(self, name: str) -> Optional[Any]:
        """
        Get a skill instance by name.
        
        Args:
            name: Skill name
            
        Returns:
            Skill instance or None
        """
        if name not in self.skills:
            return None
        
        # Lazy instantiation
        if self.skill_instances.get(name) is None:
            try:
                self.skill_instances[name] = self.skills[name]()
            except Exception as e:
                print(f"Failed to instantiate skill {name}: {e}")
                return None
        
        return self.skill_instances[name]
    
    def find_skill_for_input(self, user_input: str, 
                             context: Dict[str, Any] = None) -> Optional[str]:
        """
        Find a skill that can handle the given input.
        
        Args:
            user_input: User's request
            context: Additional context
            
        Returns:
            Skill name or None
        """
        for name, skill_class in self.skills.items():
            try:
                # Create temporary instance for checking
                skill = skill_class()
                if skill.can_handle(user_input, context):
                    return name
            except Exception:
                continue
        
        return None
    
    def execute_skill(self, name: str, user_input: str,
                      context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a skill.
        
        Args:
            name: Skill name
            user_input: User's request
            context: Additional context
            
        Returns:
            Execution result
        """
        skill = self.get_skill(name)
        
        if skill is None:
            return {
                'success': False,
                'error': f'Skill not found: {name}',
                'output': None
            }
        
        try:
            # Validate input
            is_valid, error_msg = skill.validate_input(user_input, context)
            if not is_valid:
                return {
                    'success': False,
                    'error': error_msg,
                    'output': None
                }
            
            # Initialize skill
            skill.initialize(context)
            
            # Execute
            result = skill.execute(user_input, context)
            
            # Cleanup
            skill.cleanup()
            
            return result
            
        except Exception as e:
            # Attempt recovery
            try:
                recovery = skill.recover_from_error(e, context)
                if recovery.get('success'):
                    return recovery
            except:
                pass
            
            # Rollback if possible
            try:
                skill.rollback()
            except:
                pass
            
            return {
                'success': False,
                'error': str(e),
                'output': None,
                'skill': name
            }
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """
        List all registered skills.
        
        Returns:
            List of skill info dictionaries
        """
        result = []
        
        for name, skill_class in self.skills.items():
            try:
                skill = skill_class()
                result.append({
                    'name': name,
                    'description': skill.description,
                    'active': self.skill_instances.get(name) is not None
                })
            except:
                result.append({
                    'name': name,
                    'description': '',
                    'active': False
                })
        
        return result
    
    def get_status(self) -> Dict[str, Any]:
        """Get registry status."""
        active_count = sum(
            1 for inst in self.skill_instances.values() 
            if inst is not None
        )
        
        return {
            'total_skills': len(self.skills),
            'active_instances': active_count,
            'loaded_at': self.loaded_at.isoformat(),
            'skills': list(self.skills.keys())
        }
    
    def reload_skill(self, name: str) -> bool:
        """
        Reload a skill (useful for development).
        
        Args:
            name: Skill name
            
        Returns:
            True if reloaded successfully
        """
        if name not in self.skills:
            return False
        
        # Remove existing instance
        self.skill_instances[name] = None
        
        # Re-import the module
        try:
            module_name = f"jarvis.skills.builtin.{name.lower()}"
            module = importlib.import_module(module_name)
            
            # Reload the module
            importlib.reload(module)
            
            # Get the new class
            skill_class = getattr(module, name, None)
            if skill_class:
                self.skills[name] = skill_class
                return True
        except Exception:
            pass
        
        return False
    
    def clear_cache(self) -> None:
        """Clear all cached skill instances."""
        self.skill_instances = {name: None for name in self.skills}


# Singleton instance
_registry_instance = None

def get_skill_registry() -> SkillRegistry:
    """Get the singleton SkillRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = SkillRegistry()
        _registry_instance.load_builtin_skills()
    return _registry_instance
