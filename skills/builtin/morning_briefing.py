"""
Morning Briefing Skill - Provides a comprehensive morning briefing.
Includes weather, calendar, news, system status, and daily tasks.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from ..base import BaseSkill


class MorningBriefing(BaseSkill):
    """
    Skill for providing morning briefings.
    
    Features:
    - Greeting based on time of day
    - System health status
    - Calendar/events overview
    - Weather summary (if available)
    - Todo list priorities
    - Recent notifications
    """
    
    def __init__(self):
        super().__init__(
            name='MorningBriefing',
            description='Provides a comprehensive morning briefing with system status, schedule, and priorities'
        )
        self.briefing_data = {}
    
    def get_system_prompt(self) -> str:
        return """You are JARVIS, providing a morning briefing to the user.
Be concise but informative. Structure your response clearly.
Include relevant system information and help the user prepare for their day."""
    
    def can_handle(self, user_input: str, context: Dict[str, Any] = None) -> bool:
        """Check if this is a morning briefing request."""
        input_lower = user_input.lower()
        
        briefing_triggers = [
            'morning briefing', 'daily briefing', 'brief me',
            'good morning', 'start my day', "what's on my calendar",
            'what\'s on today', 'day ahead', 'today\'s schedule',
            'morning report', 'daily report'
        ]
        
        return any(trigger in input_lower for trigger in briefing_triggers)
    
    def execute(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute the morning briefing skill."""
        try:
            self.initialize(context)
            
            # Gather briefing data
            briefing = self._gather_briefing()
            
            # Format the briefing
            formatted = self._format_briefing(briefing)
            
            self.save_state('briefing', briefing)
            
            return {
                'success': True,
                'output': formatted,
                'error': None,
                'data': briefing
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': None
            }
        finally:
            self.cleanup()
    
    def _gather_briefing(self) -> Dict[str, Any]:
        """Gather all briefing data."""
        now = datetime.now()
        
        briefing = {
            'timestamp': now.isoformat(),
            'greeting': self._get_greeting(now),
            'date': now.strftime('%A, %B %d, %Y'),
            'time': now.strftime('%I:%M %p'),
            'system_status': self._get_system_status(),
            'schedule': self._get_schedule(),
            'todos': self._get_todos(),
            'weather': self._get_weather(),
            'notifications': self._get_notifications()
        }
        
        return briefing
    
    def _get_greeting(self, now: datetime) -> str:
        """Get appropriate greeting based on time."""
        hour = now.hour
        
        if 5 <= hour < 12:
            return "Good morning"
        elif 12 <= hour < 17:
            return "Good afternoon"
        elif 17 <= hour < 21:
            return "Good evening"
        else:
            return "Hello"
    
    def _get_system_status(self) -> Dict[str, Any]:
        """Get current system status."""
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('C:\\')
            battery = psutil.sensors_battery()
            
            status = {
                'cpu': f'{cpu_percent}%',
                'memory': f'{memory.percent}%',
                'disk': f'{disk.percent}%',
                'battery': None
            }
            
            if battery:
                status['battery'] = {
                    'percent': battery.percent,
                    'plugged_in': battery.power_plugged,
                    'time_left': f'{battery.secsleft // 60} min' if battery.secsleft != psutil.POWER_TIME_UNLIMITED else 'Charging'
                }
            
            # Add alerts for high usage
            alerts = []
            if cpu_percent > 80:
                alerts.append('High CPU usage')
            if memory.percent > 80:
                alerts.append('High memory usage')
            if disk.percent > 90:
                alerts.append('Low disk space')
            if battery and battery.percent < 20 and not battery.power_plugged:
                alerts.append('Low battery')
            
            status['alerts'] = alerts
            
            return status
            
        except Exception as e:
            return {'error': str(e)}
    
    def _get_schedule(self) -> Dict[str, Any]:
        """Get today's schedule."""
        # This would integrate with calendar APIs
        # For now, return placeholder structure
        return {
            'events_today': [],
            'next_event': None,
            'message': 'Calendar integration not configured'
        }
    
    def _get_todos(self) -> Dict[str, Any]:
        """Get todo list priorities."""
        # This would integrate with todo manager
        return {
            'priority_tasks': [],
            'pending_count': 0,
            'message': 'Todo integration available via tools'
        }
    
    def _get_weather(self) -> Dict[str, Any]:
        """Get weather information."""
        # This would integrate with weather APIs
        return {
            'available': False,
            'message': 'Weather integration not configured'
        }
    
    def _get_notifications(self) -> list:
        """Get recent notifications."""
        # This would check system notifications
        return []
    
    def _format_briefing(self, briefing: Dict[str, Any]) -> str:
        """Format the briefing for display."""
        lines = []
        
        # Header
        lines.append(f"{briefing['greeting']}! Here's your briefing for {briefing['date']}")
        lines.append("")
        
        # Time
        lines.append(f"📅 Current time: {briefing['time']}")
        lines.append("")
        
        # System Status
        sys_status = briefing.get('system_status', {})
        if 'error' not in sys_status:
            lines.append("💻 System Status:")
            lines.append(f"   CPU: {sys_status.get('cpu', 'N/A')}")
            lines.append(f"   Memory: {sys_status.get('memory', 'N/A')}")
            lines.append(f"   Disk: {sys_status.get('disk', 'N/A')}")
            
            if sys_status.get('battery'):
                bat = sys_status['battery']
                plug_status = "🔌 Plugged in" if bat.get('plugged_in') else "🔋 On battery"
                lines.append(f"   Battery: {bat.get('percent', 'N/A')}% {plug_status}")
            
            if sys_status.get('alerts'):
                lines.append(f"   ⚠️ Alerts: {', '.join(sys_status['alerts'])}")
            else:
                lines.append("   ✅ All systems normal")
        lines.append("")
        
        # Schedule
        schedule = briefing.get('schedule', {})
        lines.append("📆 Today's Schedule:")
        if schedule.get('events_today'):
            for event in schedule['events_today']:
                lines.append(f"   • {event}")
        else:
            lines.append(f"   {schedule.get('message', 'No events')}")
        lines.append("")
        
        # Todos
        todos = briefing.get('todos', {})
        lines.append("✓ Priority Tasks:")
        if todos.get('priority_tasks'):
            for task in todos['priority_tasks']:
                lines.append(f"   • {task}")
        else:
            lines.append(f"   {todos.get('message', 'No priority tasks')}")
        lines.append("")
        
        # Weather
        weather = briefing.get('weather', {})
        lines.append("🌤️ Weather:")
        lines.append(f"   {weather.get('message', 'Not available')}")
        lines.append("")
        
        # Footer
        lines.append("How can I help you today?")
        
        return '\n'.join(lines)


# Export the class
__all__ = ['MorningBriefing']
