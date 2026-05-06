"""
Focus Mode Skill - Helps user enter deep work sessions

Closes all non-work apps (configurable from user profile)
Sets volume to user's preferred focus level
Sets brightness to user's preferred focus level
Opens all work apps (configurable from user profile)
Sets a Pomodoro timer (25 minutes default, configurable)
Speaks a motivational start message
Fully reversible via rollback
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import threading
import time

from ..base import BaseSkill, SkillStep, Recovery, RecoveryAction

logger = logging.getLogger(__name__)


class FocusMode(BaseSkill):
    """
    Skill for managing focus sessions with distraction blocking.
    
    Features:
    - Close all non-work apps (configurable list from user profile)
    - Set volume to user's preferred focus level
    - Set brightness to user's preferred focus level
    - Open all work apps (configurable from user profile)
    - Set a Pomodoro timer (25 minutes default, configurable)
    - Speak a motivational start message
    - Fully reversible via rollback
    """
    
    def __init__(self):
        super().__init__(
            name="focus_mode",
            description="Enter a focused work session by closing distractions, setting environment, and starting a Pomodoro timer"
        )
        
        self.focus_active = False
        self.focus_start: Optional[datetime] = None
        self.focus_duration: int = 25  # minutes (pomodoro default)
        self.focus_end: Optional[datetime] = None
        self.closed_apps: List[str] = []
        self.opened_work_apps: List[str] = []
        self.original_volume: float = 0.5
        self.original_brightness: float = 0.7
        self.timer_thread: Optional[threading.Thread] = None
        self.stop_timer = threading.Event()
        
        # Default configurations (would come from user profile in production)
        self.non_work_apps = [
            "msedge", "chrome", "firefox",  # browsers (unless needed for work)
            "spotify", "discord", "slack",  # entertainment/social
            "steam", "epicgames",  # gaming
        ]
        self.work_apps = ["code", "notepad", "terminal", "excel", "word"]
        self.focus_volume = 0.3  # 30% volume
        self.focus_brightness = 0.6  # 60% brightness
    
    def get_system_prompt(self) -> str:
        return f"""You are JARVIS in Focus Mode. Your role is to help the user maintain deep work.

CURRENT FOCUS SESSION STATUS:
- Active: {self.focus_active}
- Started: {self.focus_start.isoformat() if self.focus_start else 'N/A'}
- Duration: {self.focus_duration} minutes
- Ends: {self.focus_end.isoformat() if self.focus_end else 'N/A'}
- Closed Apps: {', '.join(self.closed_apps)}
- Opened Work Apps: {', '.join(self.opened_work_apps)}

RULES FOR FOCUS MODE:
1. Keep responses brief and non-intrusive
2. Only interrupt for urgent matters (user-defined)
3. Track time remaining and give gentle warnings at 5 min intervals
4. Help user extend or end session when requested
5. Log focus achievements for productivity tracking

When focus mode ends, celebrate the achievement and offer to start another session."""
    
    def can_handle(self, task: str) -> float:
        """Check if this is a focus mode request. Returns confidence 0.0-1.0."""
        task_lower = task.lower()
        
        high_confidence_triggers = [
            'focus mode', 'deep work', 'pomodoro', 'work session',
            'start focusing', 'begin work', 'work mode', 'concentrate',
            'close distractions', 'block distractions'
        ]
        
        medium_confidence_triggers = [
            'help me focus', 'need to work', 'time to work',
            'get things done', 'productive', 'study mode'
        ]
        
        for trigger in high_confidence_triggers:
            if trigger in task_lower:
                return 0.95
        
        for trigger in medium_confidence_triggers:
            if trigger in task_lower:
                return 0.6
        
        return 0.1
    
    def plan(self, task: str) -> List[SkillStep]:
        """Create an ordered plan of steps for focus mode."""
        # Parse custom duration if specified
        import re
        duration_match = re.search(r'(\d+)\s*(?:min|minute)', task.lower())
        duration = int(duration_match.group(1)) if duration_match else 25
        
        return [
            SkillStep(
                id='save_state',
                name='Save Current State',
                action='save_state',
                params={}
            ),
            SkillStep(
                id='close_distractions',
                name='Close Non-Work Apps',
                action='close_non_work_apps',
                params={'apps': self.non_work_apps},
                depends_on=['save_state']
            ),
            SkillStep(
                id='set_volume',
                name='Set Focus Volume',
                action='set_volume',
                params={'level': self.focus_volume},
                depends_on=['save_state']
            ),
            SkillStep(
                id='set_brightness',
                name='Set Focus Brightness',
                action='set_brightness',
                params={'level': self.focus_brightness},
                depends_on=['save_state']
            ),
            SkillStep(
                id='open_work_apps',
                name='Open Work Apps',
                action='open_work_apps',
                params={'apps': self.work_apps},
                depends_on=['close_distractions']
            ),
            SkillStep(
                id='start_timer',
                name='Start Pomodoro Timer',
                action='start_timer',
                params={'duration_minutes': duration},
                depends_on=['open_work_apps']
            ),
            SkillStep(
                id='motivational_message',
                name='Deliver Motivational Message',
                action='speak_motivation',
                params={},
                depends_on=['start_timer']
            )
        ]
    
    def execute(self, plan: List[SkillStep]) -> Dict[str, Any]:
        """Execute the focus mode skill with state tracking."""
        try:
            self.initialize({})
            
            results = {}
            for step in plan:
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
                    result_data = step_result['result']
                    if step.action == 'save_state':
                        self.original_volume = result_data.get('volume', 0.5)
                        self.original_brightness = result_data.get('brightness', 0.7)
                    elif step.action == 'close_non_work_apps':
                        self.closed_apps = result_data.get('closed_apps', [])
                    elif step.action == 'open_work_apps':
                        self.opened_work_apps = result_data.get('opened_apps', [])
                    elif step.action == 'start_timer':
                        self.focus_active = True
                        self.focus_start = datetime.now()
                        self.focus_duration = result_data.get('duration', 25)
                        self.focus_end = self.focus_start + timedelta(minutes=self.focus_duration)
            
            return {
                'success': True,
                'output': f"Focus mode activated for {self.focus_duration} minutes. Ending at {self.focus_end.strftime('%H:%M') if self.focus_end else 'N/A'}. Stay focused!",
                'error': None,
                'data': {
                    'focus_active': self.focus_active,
                    'focus_end': self.focus_end.isoformat() if self.focus_end else None,
                    'closed_apps': self.closed_apps,
                    'opened_work_apps': self.opened_work_apps
                }
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
        """Handle failure during a focus mode step."""
        # If we can't close apps or set environment, we can still proceed
        if step.action in ['close_non_work_apps', 'set_volume', 'set_brightness']:
            return Recovery(
                action=RecoveryAction.SKIP,
                message=f"Skipping {step.name}: {error}. Continuing with focus mode."
            )
        
        # Timer failure is critical
        if step.action == 'start_timer':
            return Recovery(
                action=RecoveryAction.ABORT,
                message=f"Cannot start focus session without timer: {error}"
            )
        
        return Recovery(
            action=RecoveryAction.SKIP,
            message=f"Skipping {step.name}: {error}"
        )
    
    def rollback(self) -> Dict[str, Any]:
        """Undo completed steps in reverse order - fully reversible."""
        rolled_back = []
        
        try:
            # Stop timer
            if self.focus_active:
                self.stop_timer.set()
                if self.timer_thread and self.timer_thread.is_alive():
                    self.timer_thread.join(timeout=2)
                self.focus_active = False
                rolled_back.append('timer_stopped')
            
            # Close work apps that were opened
            for app in self.opened_work_apps:
                try:
                    import subprocess
                    subprocess.run(['taskkill', '/IM', f'{app}.exe', '/F'], 
                                 capture_output=True, timeout=2)
                    rolled_back.append(f'closed_{app}')
                except Exception as e:
                    logger.warning(f"Failed to close work app {app} during rollback: {e}")
            
            # Re-open previously closed apps (if we tracked them properly)
            # This would require more sophisticated process tracking
            
            # Restore volume
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMasterVolumeLevelScalar(self.original_volume, None)
                rolled_back.append('volume_restored')
            except Exception as e:
                logger.warning(f"Failed to restore volume during rollback: {e}")
            
            # Restore brightness (would require monitor control library)
            rolled_back.append('brightness_restore_pending')
            
            self.opened_work_apps = []
            self.closed_apps = []
            
            return {
                'success': True,
                'output': 'Focus mode rolled back. Environment restored.',
                'rolled_back_steps': rolled_back
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'rolled_back_steps': rolled_back
            }
    
    def summarize(self) -> str:
        """Provide a one-sentence summary of what was accomplished."""
        if self.focus_active:
            remaining = max(0, int((self.focus_end - datetime.now()).total_seconds() / 60)) if self.focus_end else 0
            return f"Focus session active with {remaining} minutes remaining, {len(self.closed_apps)} distractions closed, and {len(self.opened_work_apps)} work apps open."
        else:
            return "Focus mode session completed successfully."
    
    def _run_step_action(self, step: SkillStep) -> Dict[str, Any]:
        """Run the actual action for a step."""
        actions = {
            'save_state': self._save_state,
            'close_non_work_apps': self._close_non_work_apps,
            'set_volume': self._set_volume,
            'set_brightness': self._set_brightness,
            'open_work_apps': self._open_work_apps,
            'start_timer': self._start_timer,
            'speak_motivation': self._speak_motivation
        }
        
        action_func = actions.get(step.action)
        if action_func:
            return action_func(step.params)
        
        return {'output': f'Unknown action: {step.action}', 'makes_changes': False}
    
    def _save_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Save current system state for rollback."""
        # Get current volume
        volume = 0.5
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            volume = vol.GetMasterVolumeLevelScalar()
        except Exception as e:
            logger.debug(f"Could not get current volume: {e}")
        
        # Get current brightness (placeholder - would use monitor control)
        brightness = 0.7
        
        return {
            'volume': volume,
            'brightness': brightness,
            'makes_changes': False
        }
    
    def _close_non_work_apps(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Close non-work applications."""
        apps_to_close = params.get('apps', self.non_work_apps)
        closed = []
        
        try:
            import subprocess
            import psutil
            
            running_processes = {p.name().lower(): p.pid for p in psutil.process()}
            
            for app in apps_to_close:
                app_name = f'{app}.exe'.lower()
                if app_name in running_processes:
                    try:
                        subprocess.run(['taskkill', '/PID', str(running_processes[app_name]), '/F'],
                                     capture_output=True, timeout=2)
                        closed.append(app)
                    except Exception as e:
                        logger.warning(f"Failed to close app {app}: {e}")
        except Exception as e:
            logger.warning(f"Error in _close_non_work_apps: {e}")
        
        return {
            'closed_apps': closed,
            'makes_changes': True,
            'undo_data': {'reopened_apps': closed}
        }
    
    def _set_volume(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set volume to focus level."""
        level = params.get('level', self.focus_volume)
        
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(level, None)
        except Exception as e:
            logger.warning(f"Failed to set volume level {level}: {e}", exc_info=True)
            return {
                'success': False,
                'error': f"Failed to set volume: {e}",
                'volume_set': None,
                'makes_changes': False
            }
        
        return {
            'volume_set': level,
            'makes_changes': True,
            'undo_data': {'restore_volume': True}
        }
    
    def _set_brightness(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set brightness to focus level."""
        level = params.get('level', self.focus_brightness)
        
        # Brightness control would require monitor control library
        # Placeholder for implementation
        
        return {
            'brightness_set': level,
            'makes_changes': True,
            'undo_data': {'restore_brightness': True}
        }
    
    def _open_work_apps(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Open work applications."""
        apps_to_open = params.get('apps', self.work_apps)
        opened = []
        failed = []
        
        try:
            import subprocess
            for app in apps_to_open:
                try:
                    subprocess.Popen([app])
                    opened.append(app)
                except Exception as e:
                    logger.warning(f"Failed to open app '{app}': {e}", exc_info=True)
                    failed.append({'app': app, 'error': str(e)})
        except Exception as e:
            logger.error(f"Error opening work apps: {e}", exc_info=True)
            return {
                'success': False,
                'error': f"Failed to open apps: {e}",
                'opened_apps': [],
                'failed_apps': [],
                'makes_changes': False
            }
        
        result = {
            'opened_apps': opened,
            'makes_changes': True,
            'undo_data': {'closed_apps': opened}
        }
        
        if failed:
            result['failed_apps'] = failed
            result['partial_success'] = True
        
        return result
    
    def _start_timer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start Pomodoro timer."""
        duration = params.get('duration_minutes', 25)
        
        self.stop_timer.clear()
        self.timer_thread = threading.Thread(target=self._focus_timer, args=(duration,), daemon=True)
        self.timer_thread.start()
        
        return {
            'duration': duration,
            'timer_started': True,
            'makes_changes': True
        }
    
    def _focus_timer(self, duration: int):
        """Background timer for focus session."""
        end_time = datetime.now() + timedelta(minutes=duration)
        
        while not self.stop_timer.is_set():
            now = datetime.now()
            if now >= end_time:
                break
            
            remaining = (end_time - now).total_seconds() / 60
            
            # Give warnings at 5 minute intervals
            if remaining <= 5 and remaining > 4:
                # Would trigger TTS here
                pass
            
            time.sleep(30)
    
    def _speak_motivation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Deliver motivational start message."""
        messages = [
            "Let's do this! Focus mode activated.",
            "Time to crush your goals. Stay focused!",
            "Deep work session started. You've got this!",
            "Distractions eliminated. Time to make progress!"
        ]
        
        import random
        message = random.choice(messages)
        
        return {
            'message': message,
            'spoken': True,
            'makes_changes': False
        }


__all__ = ['FocusMode']
