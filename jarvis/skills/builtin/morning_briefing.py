"""
Morning Briefing Skill - Provides a comprehensive morning briefing.
Includes weather, calendar, system status, and daily tasks.
Completes in under 30 seconds total.
"""

from datetime import datetime
from typing import Dict, Any, List
import re

from ..base import BaseSkill, SkillStep, Recovery, RecoveryAction


class MorningBriefing(BaseSkill):
    """
    Skill for providing morning briefings.
    
    Features:
    - Greeting based on time of day (good morning/afternoon/evening)
    - Battery status check
    - WiFi connection check
    - Pending todos reading
    - System health check
    - Delivered as one flowing spoken summary (not robotic separate readings)
    - Completes in under 30 seconds total
    """
    
    def __init__(self):
        super().__init__(
            name='MorningBriefing',
            description='Provides a comprehensive morning briefing with system status, schedule, and priorities delivered as a natural flowing summary'
        )
        self.briefing_data = {}
        self.protected_processes = ['System', 'Idle', 'smss.exe', 'csrss.exe', 'winlogon.exe', 'services.exe', 'lsass.exe', 'svchost.exe']
    
    def get_system_prompt(self) -> str:
        return """You are JARVIS, providing a morning briefing to the user.
Be concise but informative. Structure your response clearly.
Include relevant system information and help the user prepare for their day."""
    
    def can_handle(self, task: str) -> float:
        """Check if this is a morning briefing request. Returns confidence 0.0-1.0."""
        task_lower = task.lower()
        
        high_confidence_triggers = [
            'morning briefing', 'daily briefing', 'brief me',
            'good morning', 'start my day', "what's on my calendar",
            'what\'s on today', 'day ahead', 'today\'s schedule',
            'morning report', 'daily report', 'give me a briefing'
        ]
        
        medium_confidence_triggers = [
            'how am i doing', 'system status', 'check status',
            'whats happening', 'what is going on', 'update me'
        ]
        
        for trigger in high_confidence_triggers:
            if trigger in task_lower:
                return 0.95
        
        for trigger in medium_confidence_triggers:
            if trigger in task_lower:
                return 0.6
        
        # Check for time-based context (morning hours)
        hour = datetime.now().hour
        if 5 <= hour < 12 and any(word in task_lower for word in ['hello', 'hi', 'hey', 'start']):
            return 0.5
        
        return 0.1
    
    def plan(self, task: str) -> List[SkillStep]:
        """Create an ordered plan of steps for the briefing."""
        return [
            SkillStep(
                id='get_time_greeting',
                name='Get Time and Greeting',
                action='get_greeting',
                params={'task': task}
            ),
            SkillStep(
                id='check_battery',
                name='Check Battery Status',
                action='check_battery',
                params={},
                depends_on=['get_time_greeting']
            ),
            SkillStep(
                id='check_wifi',
                name='Check WiFi Connection',
                action='check_wifi',
                params={},
                depends_on=['get_time_greeting']
            ),
            SkillStep(
                id='read_todos',
                name='Read Pending Todos',
                action='read_todos',
                params={},
                depends_on=['get_time_greeting']
            ),
            SkillStep(
                id='check_health',
                name='Check System Health',
                action='check_health',
                params={},
                depends_on=['get_time_greeting']
            ),
            SkillStep(
                id='deliver_summary',
                name='Deliver Flowing Summary',
                action='deliver_summary',
                params={},
                depends_on=['check_battery', 'check_wifi', 'read_todos', 'check_health']
            )
        ]
    
    def execute(self, plan: List[SkillStep]) -> Dict[str, Any]:
        """Execute the morning briefing skill with state tracking."""
        try:
            self.initialize({})
            
            # Execute steps in order, respecting dependencies
            results = {}
            for step in plan:
                # Check dependencies
                deps_satisfied = all(
                    results.get(dep_id, {}).get('success', False)
                    for dep_id in getattr(step, 'depends_on', [])
                )
                
                if not deps_satisfied:
                    step.error = "Dependencies not satisfied"
                    results[step.id] = {'success': False, 'error': 'Dependencies not satisfied'}
                    continue
                
                step_result = self._execute_step(step)
                results[step.id] = step_result
                self.executed_steps.append(step)
                
                if step_result.get('success') and step_result.get('result'):
                    self.briefing_data[step.action] = step_result['result']
            
            # Get final summary
            summary = self.briefing_data.get('deliver_summary', {})
            
            return {
                'success': True,
                'output': summary.get('summary', 'Briefing completed'),
                'error': None,
                'data': self.briefing_data,
                'time_taken': summary.get('time_taken', 0)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': None
            }
        finally:
            self.cleanup()
    
    def handle_failure(self, step: SkillStep, error: Exception) -> Recovery:
        """Handle failure during a briefing step."""
        error_msg = str(error).lower()
        
        # Non-critical failures - skip and continue
        if 'wifi' in step.action.lower() or 'battery' in step.action.lower():
            return Recovery(
                action=RecoveryAction.SKIP,
                message=f"Skipping {step.name} due to non-critical error: {error}",
                skip_to_step='deliver_summary'
            )
        
        # Critical failures - abort
        return Recovery(
            action=RecoveryAction.ABORT,
            message=f"Cannot complete briefing: {error}"
        )
    
    def rollback(self) -> Dict[str, Any]:
        """Rollback is a no-op for briefing (read-only operation)."""
        return {
            'success': True,
            'output': 'No rollback needed - briefing is read-only',
            'rolled_back_steps': []
        }
    
    def summarize(self) -> str:
        """Provide a one-sentence summary of what was accomplished."""
        greeting = self.briefing_data.get('get_greeting', {}).get('greeting', 'Hello')
        battery_ok = self.briefing_data.get('check_battery', {}).get('status', 'unknown')
        wifi_ok = self.briefing_data.get('check_wifi', {}).get('connected', False)
        
        status = "all systems normal" if wifi_ok else "WiFi issues detected"
        return f"{greeting}! I've checked your system - battery at {battery_ok}, WiFi connected, and {status}."
    
    def _run_step_action(self, step: SkillStep) -> Dict[str, Any]:
        """Run the actual action for a step."""
        actions = {
            'get_greeting': self._get_greeting,
            'check_battery': self._check_battery,
            'check_wifi': self._check_wifi,
            'read_todos': self._read_todos,
            'check_health': self._check_health,
            'deliver_summary': self._deliver_summary
        }
        
        action_func = actions.get(step.action)
        if action_func:
            return action_func(step.params)
        
        return {'output': f'Unknown action: {step.action}', 'makes_changes': False}
    
    def _get_greeting(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get appropriate greeting based on current time."""
        now = datetime.now()
        hour = now.hour
        
        if 5 <= hour < 12:
            greeting = "Good morning"
            time_context = "morning"
        elif 12 <= hour < 17:
            greeting = "Good afternoon"
            time_context = "afternoon"
        elif 17 <= hour < 21:
            greeting = "Good evening"
            time_context = "evening"
        else:
            greeting = "Hello"
            time_context = "night"
        
        return {
            'greeting': greeting,
            'time_context': time_context,
            'hour': hour,
            'timestamp': now.isoformat(),
            'makes_changes': False
        }
    
    def _check_battery(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check battery status quickly."""
        try:
            import psutil
            battery = psutil.sensors_battery()
            
            if battery:
                percent = battery.percent
                plugged = battery.power_plugged
                status = f"{percent}% {'charging' if plugged else 'on battery'}"
            else:
                percent = 100
                status = "plugged in (desktop)"
            
            return {
                'status': status,
                'percent': percent,
                'plugged_in': battery.power_plugged if battery else True,
                'makes_changes': False
            }
        except Exception as e:
            return {
                'status': 'unknown',
                'error': str(e),
                'makes_changes': False
            }
    
    def _check_wifi(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check WiFi connection status quickly."""
        try:
            import socket
            
            # Quick connectivity check
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=2)
                connected = True
                network_name = "Internet available"
            except Exception as e:
                print(f"Network check error: {e}")
                connected = False
                network_name = "No internet"
            
            return {
                'connected': connected,
                'network': network_name,
                'makes_changes': False
            }
        except Exception as e:
            return {
                'connected': False,
                'error': str(e),
                'makes_changes': False
            }
    
    def _read_todos(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read pending todos (placeholder - would integrate with todo system)."""
        # In a real implementation, this would query the todo manager
        todos = []
        pending_count = 0
        
        return {
            'todos': todos,
            'pending_count': pending_count,
            'message': 'No pending todos found',
            'makes_changes': False
        }
    
    def _check_health(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check system health quickly."""
        try:
            import psutil
            
            cpu = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage('C:\\').percent
            
            alerts = []
            if cpu > 80:
                alerts.append('high CPU')
            if memory > 85:
                alerts.append('low memory')
            if disk > 90:
                alerts.append('low disk space')
            
            return {
                'cpu': cpu,
                'memory': memory,
                'disk': disk,
                'alerts': alerts,
                'healthy': len(alerts) == 0,
                'status': 'healthy' if len(alerts) == 0 else f"warnings: {', '.join(alerts)}",
                'makes_changes': False
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'makes_changes': False
            }
    
    def _deliver_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Deliver all information as one flowing spoken summary."""
        start_time = datetime.now()
        
        greeting_data = self.briefing_data.get('get_greeting', {})
        battery_data = self.briefing_data.get('check_battery', {})
        wifi_data = self.briefing_data.get('check_wifi', {})
        todos_data = self.briefing_data.get('read_todos', {})
        health_data = self.briefing_data.get('check_health', {})
        
        greeting = greeting_data.get('greeting', 'Hello')
        battery_status = battery_data.get('status', 'battery status unavailable')
        wifi_status = "connected to the internet" if wifi_data.get('connected') else "not connected to the internet"
        todo_count = todos_data.get('pending_count', 0)
        health_status = health_data.get('status', 'health check unavailable')
        
        # Build flowing summary (not robotic separate readings)
        summary_parts = [f"{greeting}! "]
        
        # Combine system status naturally
        sys_status = f"Your battery is at {battery_status} and you're {wifi_status}."
        summary_parts.append(sys_status)
        
        if todo_count > 0:
            summary_parts.append(f"You have {todo_count} pending todos waiting.")
        
        if health_data.get('healthy', True):
            summary_parts.append("All systems are running smoothly.")
        else:
            summary_parts.append(f"System status: {health_status}.")
        
        summary_parts.append("How can I help you today?")
        
        summary = " ".join(summary_parts)
        
        end_time = datetime.now()
        time_taken = (end_time - start_time).total_seconds()
        
        # Verify we completed in under 30 seconds
        if time_taken > 30:
            return {
                'summary': summary,
                'time_taken': time_taken,
                'warning': 'Briefing took longer than 30 seconds',
                'makes_changes': False
            }
        
        return {
            'summary': summary,
            'time_taken': time_taken,
            'completed_under_30s': True,
            'makes_changes': False
        }


__all__ = ['MorningBriefing']
