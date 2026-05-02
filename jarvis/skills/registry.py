"""
Skills Registry - Auto-discovers and manages JARVIS skills.

Features:
- Auto-discover all skills in skills/builtin/
- Allow skills to be added to skills/learned/ at runtime without restart
- Select the best skill for a task based on can_handle() confidence scores
- Fall back to direct tool execution if no skill scores above 0.6
"""

import os
import sys
import importlib.util
import importlib.machinery
from typing import Dict, Any, List, Optional, Type
from pathlib import Path
from datetime import datetime
import threading

from .base import BaseSkill


class SkillsRegistry:
    """
    Registry for managing JARVIS skills with auto-discovery and dynamic loading.
    """
    
    def __init__(self, builtin_dir: str = None, learned_dir: str = None):
        """
        Initialize the skills registry.
        
        Args:
            builtin_dir: Directory containing built-in skills
            learned_dir: Directory containing user-learned skills
        """
        self._skills: Dict[str, BaseSkill] = {}
        self._skill_classes: Dict[str, Type[BaseSkill]] = {}
        self._lock = threading.RLock()
        
        # Set default directories
        current_dir = Path(__file__).parent
        self.builtin_dir = Path(builtin_dir) if builtin_dir else current_dir / "builtin"
        self.learned_dir = Path(learned_dir) if learned_dir else current_dir / "learned"
        
        # Confidence threshold for skill selection
        self.confidence_threshold = 0.6
        
        # Track last discovery time for each directory
        self._last_discovery = {
            'builtin': None,
            'learned': None
        }
        
        # Fallback tools (for when no skill matches)
        self._fallback_tools: Dict[str, callable] = {}
    
    def discover_builtin_skills(self, force: bool = False) -> int:
        """
        Auto-discover all skills in the builtin directory.
        
        Args:
            force: Force re-discovery even if already discovered
            
        Returns:
            Number of skills discovered
        """
        return self._discover_skills(self.builtin_dir, 'builtin', force)
    
    def discover_learned_skills(self, force: bool = False) -> int:
        """
        Discover skills in the learned directory (can be called at runtime).
        
        Args:
            force: Force re-discovery
            
        Returns:
            Number of skills discovered
        """
        return self._discover_skills(self.learned_dir, 'learned', force)
    
    def _discover_skills(self, directory: Path, source: str, force: bool = False) -> int:
        """
        Discover skills from a directory.
        
        Args:
            directory: Directory to scan
            source: Source identifier ('builtin' or 'learned')
            force: Force re-discovery
            
        Returns:
            Number of skills discovered
        """
        with self._lock:
            # Check if we need to re-discover
            if not force and self._last_discovery.get(source):
                # Check if directory has been modified
                try:
                    latest_mtime = max(f.stat().st_mtime for f in directory.glob("*.py") if f.is_file())
                    if latest_mtime <= self._last_discovery[source].timestamp():
                        return len(self._skills)
                except (ValueError, FileNotFoundError):
                    pass
            
            count = 0
            
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                self._last_discovery[source] = datetime.now()
                return 0
            
            # Find all Python files in the directory
            for py_file in directory.glob("*.py"):
                if py_file.name.startswith('_'):
                    continue
                
                try:
                    module_name = f"jarvis.skills.{source}.{py_file.stem}"
                    
                    # Load the module dynamically
                    spec = importlib.util.spec_from_file_location(module_name, py_file)
                    if spec is None or spec.loader is None:
                        continue
                    
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    # Find skill classes in the module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        
                        # Check if it's a skill class (not imported)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseSkill) and 
                            attr != BaseSkill and
                            attr.__module__ == module_name):
                            
                            # Instantiate and register the skill
                            try:
                                skill_instance = attr()
                                self.register_skill(skill_instance)
                                count += 1
                            except Exception as e:
                                print(f"Warning: Could not instantiate {attr_name}: {e}")
                
                except Exception as e:
                    print(f"Warning: Error loading {py_file}: {e}")
            
            self._last_discovery[source] = datetime.now()
            return count
    
    def register_skill(self, skill: BaseSkill) -> None:
        """
        Register a skill instance.
        
        Args:
            skill: Skill instance to register
        """
        with self._lock:
            self._skills[skill.name] = skill
            self._skill_classes[skill.__class__.__name__] = skill.__class__
    
    def unregister_skill(self, name: str) -> bool:
        """
        Unregister a skill by name.
        
        Args:
            name: Name of the skill to unregister
            
        Returns:
            True if skill was unregistered, False if not found
        """
        with self._lock:
            if name in self._skills:
                del self._skills[name]
                skill_class = self._skill_classes.get(name)
                if skill_class:
                    del self._skill_classes[name]
                return True
            return False
    
    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """
        Get a skill by name.
        
        Args:
            name: Name of the skill
            
        Returns:
            Skill instance or None if not found
        """
        with self._lock:
            return self._skills.get(name)
    
    def get_all_skills(self) -> Dict[str, BaseSkill]:
        """
        Get all registered skills.
        
        Returns:
            Dictionary of skill name to skill instance
        """
        with self._lock:
            return self._skills.copy()
    
    def select_best_skill(self, task: str) -> tuple:
        """
        Select the best skill for a given task based on confidence scores.
        
        Args:
            task: User's task/request
            
        Returns:
            Tuple of (skill, confidence_score) or (None, 0.0) if no match
        """
        with self._lock:
            best_skill = None
            best_confidence = 0.0
            
            for name, skill in self._skills.items():
                try:
                    confidence = skill.can_handle(task)
                    
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_skill = skill
                        
                except Exception as e:
                    print(f"Warning: Error checking skill {name}: {e}")
            
            return (best_skill, best_confidence)
    
    def execute_task(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a task using the best matching skill, or fall back to tools.
        
        Args:
            task: User's task/request
            context: Additional context
            
        Returns:
            Execution result dictionary
        """
        # Select best skill
        skill, confidence = self.select_best_skill(task)
        
        # Check if confidence meets threshold
        if skill is None or confidence < self.confidence_threshold:
            # Fall back to direct tool execution
            return self._execute_fallback(task, context)
        
        # Execute the skill
        try:
            # Create plan
            plan = skill.plan(task)
            
            # Execute plan
            result = skill.execute(plan)
            
            return {
                'success': result.get('success', False),
                'output': result.get('output'),
                'error': result.get('error'),
                'skill_used': skill.name,
                'confidence': confidence,
                'used_fallback': False
            }
            
        except Exception as e:
            return {
                'success': False,
                'output': None,
                'error': str(e),
                'skill_used': skill.name,
                'confidence': confidence,
                'used_fallback': False
            }
    
    def _execute_fallback(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute task using fallback tools when no skill matches.
        
        Args:
            task: User's task/request
            context: Additional context
            
        Returns:
            Execution result dictionary
        """
        # Check registered fallback tools
        for tool_name, tool_func in self._fallback_tools.items():
            try:
                result = tool_func(task, context)
                if result:
                    return {
                        'success': True,
                        'output': result,
                        'error': None,
                        'skill_used': None,
                        'tool_used': tool_name,
                        'confidence': 0.0,
                        'used_fallback': True
                    }
            except Exception as e:
                continue
        
        # No fallback matched
        return {
            'success': False,
            'output': None,
            'error': f"No skill or tool could handle: {task}",
            'skill_used': None,
            'confidence': 0.0,
            'used_fallback': True
        }
    
    def register_fallback_tool(self, name: str, func: callable) -> None:
        """
        Register a fallback tool for when no skill matches.
        
        Args:
            name: Tool name
            func: Tool function that takes (task, context) and returns result
        """
        with self._lock:
            self._fallback_tools[name] = func
    
    def add_learned_skill(self, skill_path: str) -> bool:
        """
        Add a new skill to the learned directory at runtime.
        
        Args:
            skill_path: Path to the skill Python file
            
        Returns:
            True if skill was added successfully
        """
        path = Path(skill_path)
        
        if not path.exists():
            return False
        
        # Copy to learned directory
        dest_path = self.learned_dir / path.name
        
        try:
            import shutil
            shutil.copy2(path, dest_path)
            
            # Force re-discovery of learned skills
            self.discover_learned_skills(force=True)
            
            return True
            
        except Exception as e:
            print(f"Error adding learned skill: {e}")
            return False
    
    def reload_skill(self, name: str) -> bool:
        """
        Reload a skill from disk.
        
        Args:
            name: Name of the skill to reload
            
        Returns:
            True if skill was reloaded successfully
        """
        with self._lock:
            skill = self._skills.get(name)
            if not skill:
                return False
            
            # Find the skill's source file
            skill_class = self._skill_classes.get(name)
            if not skill_class:
                return False
            
            try:
                module = sys.modules.get(skill_class.__module__)
                if module:
                    importlib.reload(module)
                    
                    # Re-instantiate the skill
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseSkill) and 
                            attr != BaseSkill and
                            attr.__module__ == skill_class.__module__):
                            
                            new_skill = attr()
                            self._skills[name] = new_skill
                            return True
            except Exception as e:
                print(f"Error reloading skill {name}: {e}")
            
            return False
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """
        List all registered skills with their metadata.
        
        Returns:
            List of skill information dictionaries
        """
        with self._lock:
            skills_info = []
            
            for name, skill in self._skills.items():
                info = {
                    'name': skill.name,
                    'description': skill.description,
                    'class': skill.__class__.__name__,
                    'created_at': skill.created_at.isoformat() if skill.created_at else None,
                    'last_used': skill.last_used.isoformat() if skill.last_used else None,
                    'status': skill.get_status() if hasattr(skill, 'get_status') else {}
                }
                skills_info.append(info)
            
            return skills_info
    
    def get_skill_names(self) -> List[str]:
        """
        Get list of all registered skill names.
        
        Returns:
            List of skill names
        """
        with self._lock:
            return list(self._skills.keys())
    
    def initialize(self) -> int:
        """
        Initialize the registry by discovering all skills.
        
        Returns:
            Total number of skills discovered
        """
        builtin_count = self.discover_builtin_skills()
        learned_count = self.discover_learned_skills()
        return builtin_count + learned_count


# Global registry instance
_registry: Optional[SkillsRegistry] = None

def get_registry() -> SkillsRegistry:
    """Get or create the global skills registry."""
    global _registry
    if _registry is None:
        _registry = SkillsRegistry()
    return _registry

def initialize_registry() -> int:
    """Initialize the global registry and return skill count."""
    registry = get_registry()
    return registry.initialize()


__all__ = ['SkillsRegistry', 'get_registry', 'initialize_registry']
