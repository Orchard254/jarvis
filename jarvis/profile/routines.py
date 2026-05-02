"""
JARVIS Routines - Manages user routines and automated workflows.

Handles:
- Routine definition and scheduling
- Trigger-based execution
- Routine templates
- Execution tracking
"""

import json
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from datetime import datetime, time
from dataclasses import dataclass, field
from enum import Enum
import threading


class TriggerType(Enum):
    """Types of routine triggers."""
    TIME = 'time'  # Specific time of day
    INTERVAL = 'interval'  # Every N minutes/hours
    EVENT = 'event'  # On specific event
    MANUAL = 'manual'  # User-initiated only


@dataclass
class RoutineTrigger:
    """Trigger configuration for a routine."""
    trigger_type: TriggerType
    value: Any  # time object for TIME, minutes for INTERVAL, event name for EVENT
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'trigger_type': self.trigger_type.value,
            'value': self.value.isoformat() if isinstance(self.value, time) else self.value,
            'enabled': self.enabled
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RoutineTrigger':
        trigger_type = TriggerType(data['trigger_type'])
        value = data['value']
        
        if trigger_type == TriggerType.TIME and isinstance(value, str):
            value = time.fromisoformat(value)
        
        return cls(
            trigger_type=trigger_type,
            value=value,
            enabled=data.get('enabled', True)
        )


@dataclass
class RoutineStep:
    """A single step in a routine."""
    step_id: str
    tool_name: str
    parameters: Dict[str, Any]
    description: str = ''
    on_error: str = 'stop'  # 'stop', 'continue', 'retry'
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'step_id': self.step_id,
            'tool_name': self.tool_name,
            'parameters': self.parameters,
            'description': self.description,
            'on_error': self.on_error,
            'retry_count': self.retry_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RoutineStep':
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class Routine:
    """A user-defined routine."""
    routine_id: str
    name: str
    description: str
    triggers: List[RoutineTrigger]
    steps: List[RoutineStep]
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    run_count: int = 0
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'routine_id': self.routine_id,
            'name': self.name,
            'description': self.description,
            'triggers': [t.to_dict() for t in self.triggers],
            'steps': [s.to_dict() for s in self.steps],
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat(),
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'run_count': self.run_count,
            'tags': self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Routine':
        triggers = [RoutineTrigger.from_dict(t) for t in data.get('triggers', [])]
        steps = [RoutineStep.from_dict(s) for s in data.get('steps', [])]
        
        created_at = datetime.now()
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        last_run = None
        if data.get('last_run'):
            last_run = datetime.fromisoformat(data['last_run'])
        
        return cls(
            routine_id=data['routine_id'],
            name=data['name'],
            description=data['description'],
            triggers=triggers,
            steps=steps,
            enabled=data.get('enabled', True),
            created_at=created_at,
            last_run=last_run,
            run_count=data.get('run_count', 0),
            tags=data.get('tags', [])
        )


class RoutineManager:
    """
    Routine management and execution system.
    
    Features:
    - Routine CRUD operations
    - Trigger evaluation
    - Sequential step execution
    - Error handling per step
    - Execution history
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path(__file__).parent.parent / 'data' / 'routines.json'
        self._routines: Dict[str, Routine] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._running = False
        self._check_thread: Optional[threading.Thread] = None
        self._execute_callback: Optional[Callable] = None
        
        self._load()
    
    def _load(self):
        """Load routines from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for rid, rdata in data.get('routines', {}).items():
                        self._routines[rid] = Routine.from_dict(rdata)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load routines: {e}")
    
    def _save(self):
        """Save routines to storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'routines': {rid: r.to_dict() for rid, r in self._routines.items()}
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save routines: {e}")
    
    def set_execute_callback(self, callback: Callable):
        """Set callback for executing routine steps."""
        self._execute_callback = callback
    
    def create_routine(
        self,
        name: str,
        description: str,
        triggers: List[RoutineTrigger],
        steps: List[RoutineStep],
        tags: Optional[List[str]] = None
    ) -> Routine:
        """Create a new routine."""
        import uuid
        routine_id = str(uuid.uuid4())[:8]
        
        routine = Routine(
            routine_id=routine_id,
            name=name,
            description=description,
            triggers=triggers,
            steps=steps,
            tags=tags or []
        )
        
        self._routines[routine_id] = routine
        self._save()
        return routine
    
    def update_routine(self, routine_id: str, **kwargs) -> bool:
        """Update an existing routine."""
        if routine_id not in self._routines:
            return False
        
        routine = self._routines[routine_id]
        for key, value in kwargs.items():
            if hasattr(routine, key):
                setattr(routine, key, value)
        
        self._save()
        return True
    
    def delete_routine(self, routine_id: str) -> bool:
        """Delete a routine."""
        if routine_id in self._routines:
            del self._routines[routine_id]
            self._save()
            return True
        return False
    
    def get_routine(self, routine_id: str) -> Optional[Routine]:
        """Get a routine by ID."""
        return self._routines.get(routine_id)
    
    def list_routines(self, enabled_only: bool = False) -> List[Routine]:
        """List all routines."""
        routines = list(self._routines.values())
        if enabled_only:
            routines = [r for r in routines if r.enabled]
        return routines
    
    def enable_routine(self, routine_id: str) -> bool:
        """Enable a routine."""
        return self.update_routine(routine_id, enabled=True)
    
    def disable_routine(self, routine_id: str) -> bool:
        """Disable a routine."""
        return self.update_routine(routine_id, enabled=False)
    
    def run_routine_manually(self, routine_id: str) -> Dict[str, Any]:
        """Manually trigger a routine execution."""
        routine = self._routines.get(routine_id)
        if not routine:
            return {'success': False, 'error': 'Routine not found'}
        
        if not routine.enabled:
            return {'success': False, 'error': 'Routine is disabled'}
        
        return self._execute_routine(routine)
    
    def _execute_routine(self, routine: Routine) -> Dict[str, Any]:
        """Execute a routine's steps."""
        results = {
            'routine_id': routine.routine_id,
            'name': routine.name,
            'started_at': datetime.now().isoformat(),
            'steps': [],
            'success': True
        }
        
        for i, step in enumerate(routine.steps):
            step_result = {
                'step_id': step.step_id,
                'tool_name': step.tool_name,
                'attempt': 1,
                'success': False,
                'error': None
            }
            
            try:
                if self._execute_callback:
                    # Execute the tool
                    result = self._execute_callback(
                        step.tool_name,
                        step.parameters
                    )
                    step_result['success'] = result.get('success', False)
                    step_result['output'] = result.get('output', '')
                else:
                    step_result['error'] = 'No execute callback configured'
                
            except Exception as e:
                step_result['error'] = str(e)
                
                # Handle retries
                attempts = 0
                while attempts < step.retry_count and not step_result['success']:
                    attempts += 1
                    step_result['attempt'] = attempts + 1
                    try:
                        if self._execute_callback:
                            result = self._execute_callback(
                                step.tool_name,
                                step.parameters
                            )
                            step_result['success'] = result.get('success', False)
                    except Exception as retry_e:
                        step_result['error'] = str(retry_e)
            
            results['steps'].append(step_result)
            
            # Check if we should stop on error
            if not step_result['success'] and step.on_error == 'stop':
                results['success'] = False
                break
            
            if not step_result['success'] and step.on_error == 'continue':
                results['success'] = False
                continue
        
        # Update routine stats
        routine.last_run = datetime.now()
        routine.run_count += 1
        self._save()
        
        # Record execution
        self._execution_history.append(results)
        if len(self._execution_history) > 100:
            self._execution_history = self._execution_history[-50:]
        
        results['completed_at'] = datetime.now().isoformat()
        return results
    
    def check_triggers(self):
        """Check all routines for triggered execution."""
        now = datetime.now()
        current_time = now.time()
        
        for routine in self._routines.values():
            if not routine.enabled:
                continue
            
            for trigger in routine.triggers:
                if not trigger.enabled:
                    continue
                
                should_run = False
                
                if trigger.trigger_type == TriggerType.TIME:
                    # Check if current time matches trigger time
                    trigger_time = trigger.value
                    if isinstance(trigger_time, time):
                        # Allow 1-minute window
                        diff = abs((current_time.hour - trigger_time.hour) * 60 + 
                                  (current_time.minute - trigger_time.minute))
                        if diff <= 1:
                            should_run = True
                
                elif trigger.trigger_type == TriggerType.INTERVAL:
                    # Check if enough time has passed since last run
                    if routine.last_run:
                        elapsed = (now - routine.last_run).total_seconds() / 60
                        if elapsed >= trigger.value:  # value is in minutes
                            should_run = True
                    else:
                        should_run = True
                
                if should_run:
                    self._execute_routine(routine)
    
    def start_scheduler(self, check_interval: float = 60.0):
        """Start the routine scheduler."""
        self._running = True
        
        def scheduler_loop():
            while self._running:
                self.check_triggers()
                # Sleep in small increments to allow quick shutdown
                for _ in range(int(check_interval)):
                    if not self._running:
                        break
                    import time
                    time.sleep(1)
        
        self._check_thread = threading.Thread(target=scheduler_loop, daemon=True)
        self._check_thread.start()
    
    def stop_scheduler(self):
        """Stop the routine scheduler."""
        self._running = False
        if self._check_thread:
            self._check_thread.join(timeout=5.0)
            self._check_thread = None
    
    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent execution history."""
        return self._execution_history[-limit:]
    
    def get_routine_templates(self) -> Dict[str, Dict[str, Any]]:
        """Get predefined routine templates."""
        return {
            'morning_briefing': {
                'name': 'Morning Briefing',
                'description': 'Start your day with weather, news, and calendar',
                'default_triggers': [{'trigger_type': 'time', 'value': '08:00'}],
                'suggested_steps': [
                    {'tool_name': 'get_time', 'parameters': {}},
                    {'tool_name': 'get_date', 'parameters': {}},
                    {'tool_name': 'search_web', 'parameters': {'query': 'news headlines'}},
                ]
            },
            'focus_mode': {
                'name': 'Focus Mode',
                'description': 'Minimize distractions and set Do Not Disturb',
                'default_triggers': [],
                'suggested_steps': [
                    {'tool_name': 'mute_volume', 'parameters': {}},
                    {'tool_name': 'minimize_windows', 'parameters': {}},
                ]
            },
            'shutdown_sequence': {
                'name': 'Shutdown Sequence',
                'description': 'Safely close apps and shutdown PC',
                'default_triggers': [],
                'suggested_steps': [
                    {'tool_name': 'close_app', 'parameters': {'app_name': 'chrome'}},
                    {'tool_name': 'close_app', 'parameters': {'app_name': 'spotify'}},
                    {'tool_name': 'shutdown_pc', 'parameters': {}},
                ]
            }
        }


# Singleton instance
_routine_manager: Optional[RoutineManager] = None


def get_routine_manager(storage_path: Optional[Path] = None) -> RoutineManager:
    """Get the singleton routine manager instance."""
    global _routine_manager
    if _routine_manager is None:
        _routine_manager = RoutineManager(storage_path)
    return _routine_manager


def reset_routine_manager():
    """Reset the singleton instance (for testing)."""
    global _routine_manager
    if _routine_manager:
        _routine_manager.stop_scheduler()
    _routine_manager = None
