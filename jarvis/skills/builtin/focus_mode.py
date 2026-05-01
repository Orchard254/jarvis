"""
Focus Mode Skill - Helps user enter deep work sessions

Blocks distractions, sets timers, and maintains focus state.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import threading
import time

from ..base import BaseSkill


class FocusModeSkill(BaseSkill):
    """
    Skill for managing focus sessions with distraction blocking.
    
    Features:
    - Set focus duration
    - Block distracting websites/apps
    - Play focus music (optional)
    - Track focus streaks
    - Gentle reminders
    """
    
    def __init__(self):
        super().__init__(
            name="focus_mode",
            description="Enter a focused work session with distraction blocking",
            version="1.0.0"
        )
        
        self.focus_active = False
        self.focus_start: Optional[datetime] = None
        self.focus_duration: int = 25  # minutes (pomodoro default)
        self.focus_end: Optional[datetime] = None
        self.blocked_apps: List[str] = []
        self.blocked_sites: List[str] = []
        self.timer_thread: Optional[threading.Thread] = None
        self.stop_timer = threading.Event()
        
        # Default distractions to block
        self.default_blocked_sites = [
            "facebook.com", "twitter.com", "instagram.com", "tiktok.com",
            "reddit.com", "youtube.com", "netflix.com", "twitch.tv"
        ]
        self.default_blocked_apps = [
            "msedge", "chrome", "firefox"  # Can be selectively blocked
        ]
    
    def get_system_prompt(self) -> str:
        return """You are JARVIS in Focus Mode. Your role is to help the user maintain deep work.

CURRENT FOCUS SESSION STATUS:
- Active: {focus_active}
- Started: {focus_start}
- Duration: {duration} minutes
- Ends: {focus_end}
- Blocked Sites: {blocked_sites}
- Blocked Apps: {blocked_apps}

RULES FOR FOCUS MODE:
1. Keep responses brief and non-intrusive
2. Only interrupt for urgent matters (user-defined)
3. Track time remaining and give gentle warnings at 5 min intervals
4. If user asks to check distractions, politely remind them of focus goals
5. Help user extend or end session when requested
6. Log focus achievements for productivity tracking

When focus mode ends, celebrate the achievement and offer to start another session.""".format(
            focus_active=self.focus_active,
            focus_start=self.focus_start.isoformat() if self.focus_start else "N/A",
            duration=self.focus_duration,
            focus_end=self.focus_end.isoformat() if self.focus_end else "N/A",
            blocked_sites=", ".join(self.blocked_sites),
            blocked_apps=", ".join(self.blocked_apps)
        )
    
    def on_enter(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Activate focus mode."""
        try:
            duration = context.get("duration", self.focus_duration)
            
            self.focus_active = True
            self.focus_start = datetime.now()
            self.focus_duration = int(duration)
            self.focus_end = self.focus_start + timedelta(minutes=duration)
            self.blocked_sites = self.default_blocked_sites.copy()
            self.blocked_apps = []  # Don't block browsers by default, just sites
            
            # Start timer thread
            self.stop_timer.clear()
            self.timer_thread = threading.Thread(target=self._focus_timer, daemon=True)
            self.timer_thread.start()
            
            return {
                "success": True,
                "output": f"Focus mode activated for {duration} minutes. Ending at {self.focus_end.strftime('%H:%M')}. I'll keep you on track!",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Focus session started successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to start focus mode: {e}"
            }
    
    def on_exit(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Deactivate focus mode."""
        try:
            self.stop_timer.set()
            
            if self.timer_thread and self.timer_thread.is_alive():
                self.timer_thread.join(timeout=2)
            
            session_duration = 0
            if self.focus_start:
                session_duration = int((datetime.now() - self.focus_start).total_seconds() / 60)
            
            self.focus_active = False
            completed = self.focus_end is not None and datetime.now() >= self.focus_end
            
            result = {
                "success": True,
                "output": f"Focus session {'completed' if completed else 'ended early'}. "
                         f"You focused for {session_duration} minutes. Great work!",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Focus session ended"
            }
            
            # Reset state
            self.focus_start = None
            self.focus_end = None
            self.blocked_sites = []
            self.blocked_apps = []
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Error ending focus mode: {e}"
            }
    
    def _focus_timer(self):
        """Background timer for focus session."""
        while not self.stop_timer.is_set():
            if not self.focus_active or not self.focus_end:
                break
                
            now = datetime.now()
            if now >= self.focus_end:
                # Session complete
                self.stop_timer.set()
                break
                
            remaining = (self.focus_end - now).total_seconds() / 60
            
            # Give warnings at 5 minute intervals
            if remaining <= 5 and remaining > 4:
                # Would trigger TTS here in full implementation
                pass
                
            time.sleep(30)  # Check every 30 seconds
    
    def execute(self, action: str, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute focus mode actions."""
        
        actions = {
            "start": self._start_focus,
            "end": self._end_focus,
            "extend": self._extend_focus,
            "status": self._get_status,
            "block_app": self._block_app,
            "block_site": self._block_site,
            "unblock_all": self._unblock_all
        }
        
        if action not in actions:
            return {
                "success": False,
                "output": None,
                "error": f"Unknown focus action: {action}",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Invalid action"
            }
        
        return actions[action](params, context)
    
    def _start_focus(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Start focus session."""
        if self.focus_active:
            return {
                "success": False,
                "output": None,
                "error": "Focus mode is already active",
                "exit_code": 1,
                "verified": True,
                "verify_msg": "Focus already active"
            }
        
        return self.on_enter(params)
    
    def _end_focus(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """End focus session."""
        if not self.focus_active:
            return {
                "success": False,
                "output": None,
                "error": "Focus mode is not active",
                "exit_code": 1,
                "verified": True,
                "verify_msg": "Focus not active"
            }
        
        return self.on_exit(params)
    
    def _extend_focus(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Extend current focus session."""
        if not self.focus_active:
            return {
                "success": False,
                "output": None,
                "error": "Cannot extend: focus mode is not active",
                "exit_code": 1,
                "verified": True,
                "verify_msg": "Focus not active"
            }
        
        try:
            extra_minutes = int(params.get("minutes", 5))
            old_end = self.focus_end
            self.focus_end = self.focus_end + timedelta(minutes=extra_minutes)
            self.focus_duration += extra_minutes
            
            return {
                "success": True,
                "output": f"Extended focus session by {extra_minutes} minutes. New end time: {self.focus_end.strftime('%H:%M')}",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Extended from {old_end.strftime('%H:%M')} to {self.focus_end.strftime('%H:%M')}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Failed to extend"
            }
    
    def _get_status(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Get current focus status."""
        if not self.focus_active:
            return {
                "success": True,
                "output": "Focus mode is not currently active. Say 'start focus mode' to begin.",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Focus inactive"
            }
        
        now = datetime.now()
        elapsed = int((now - self.focus_start).total_seconds() / 60) if self.focus_start else 0
        remaining = max(0, int((self.focus_end - now).total_seconds() / 60)) if self.focus_end else 0
        
        return {
            "success": True,
            "output": f"Focus session in progress. Elapsed: {elapsed} min, Remaining: {remaining} min. Ends at {self.focus_end.strftime('%H:%M') if self.focus_end else 'N/A'}. Stay focused!",
            "error": None,
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"{elapsed}min elapsed, {remaining}min remaining"
        }
    
    def _block_app(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Block an application during focus."""
        app = params.get("app", "").lower()
        if not app:
            return {
                "success": False,
                "output": None,
                "error": "No app specified",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Missing app name"
            }
        
        if app not in self.blocked_apps:
            self.blocked_apps.append(app)
        
        return {
            "success": True,
            "output": f"Added {app} to blocked apps during focus",
            "error": None,
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Blocked {app}"
        }
    
    def _block_site(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Block a website during focus."""
        site = params.get("site", "").lower()
        if not site:
            return {
                "success": False,
                "output": None,
                "error": "No site specified",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Missing site name"
            }
        
        if site not in self.blocked_sites:
            self.blocked_sites.append(site)
        
        return {
            "success": True,
            "output": f"Added {site} to blocked sites during focus",
            "error": None,
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Blocked {site}"
        }
    
    def _unblock_all(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Unblock all apps and sites."""
        self.blocked_apps = []
        self.blocked_sites = []
        
        return {
            "success": True,
            "output": "All blocks removed. Use caution - distractions are now accessible.",
            "error": None,
            "exit_code": 0,
            "verified": True,
            "verify_msg": "All blocks cleared"
        }
    
    def get_state(self) -> Dict[str, Any]:
        """Get current skill state for persistence."""
        return {
            "focus_active": self.focus_active,
            "focus_start": self.focus_start.isoformat() if self.focus_start else None,
            "focus_duration": self.focus_duration,
            "focus_end": self.focus_end.isoformat() if self.focus_end else None,
            "blocked_apps": self.blocked_apps,
            "blocked_sites": self.blocked_sites
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore skill state from persistence."""
        self.focus_active = state.get("focus_active", False)
        focus_start_str = state.get("focus_start")
        self.focus_start = datetime.fromisoformat(focus_start_str) if focus_start_str else None
        self.focus_duration = state.get("focus_duration", 25)
        focus_end_str = state.get("focus_end")
        self.focus_end = datetime.fromisoformat(focus_end_str) if focus_end_str else None
        self.blocked_apps = state.get("blocked_apps", [])
        self.blocked_sites = state.get("blocked_sites", [])
