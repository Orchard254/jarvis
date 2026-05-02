"""
JARVIS User Profile - Manages user preferences, settings, and learned behaviors.

Stores and manages:
- User preferences (voice, display, behavior)
- Personal context (name, location, schedule patterns)
- Learned behaviors and routines
- Custom tool configurations
"""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict


@dataclass
class UserPreferences:
    """User preference settings."""
    # Voice settings
    voice_enabled: bool = True
    voice_name: str = 'default'
    speech_rate: float = 1.0
    wake_word_enabled: bool = True
    
    # Display settings
    dark_mode: bool = True
    notifications_enabled: bool = True
    
    # Behavior settings
    auto_execute_safe_tools: bool = True
    require_confirmation_for: List[str] = field(default_factory=list)
    default_model: str = 'llama3.1'
    
    # Privacy settings
    log_commands: bool = True
    share_analytics: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPreferences':
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class PersonalContext:
    """Personal context about the user."""
    name: Optional[str] = None
    timezone: str = 'UTC'
    location: Optional[str] = None
    occupation: Optional[str] = None
    
    # Schedule patterns
    work_hours_start: int = 9  # 9 AM
    work_hours_end: int = 17   # 5 PM
    quiet_hours_start: int = 22  # 10 PM
    quiet_hours_end: int = 7     # 7 AM
    
    # App preferences
    preferred_browser: str = 'chrome'
    preferred_terminal: str = 'powershell'
    favorite_apps: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PersonalContext':
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class UserProfile:
    """Complete user profile."""
    user_id: str = 'default'
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    preferences: UserPreferences = field(default_factory=UserPreferences)
    context: PersonalContext = field(default_factory=PersonalContext)
    
    # Custom tool configurations
    tool_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Tags/notes
    tags: List[str] = field(default_factory=list)
    notes: str = ''
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'preferences': self.preferences.to_dict(),
            'context': self.context.to_dict(),
            'tool_configs': self.tool_configs,
            'tags': self.tags,
            'notes': self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserProfile':
        prefs = UserPreferences.from_dict(data.get('preferences', {}))
        ctx = PersonalContext.from_dict(data.get('context', {}))
        
        created_at = datetime.now()
        updated_at = datetime.now()
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        
        return cls(
            user_id=data.get('user_id', 'default'),
            created_at=created_at,
            updated_at=updated_at,
            preferences=prefs,
            context=ctx,
            tool_configs=data.get('tool_configs', {}),
            tags=data.get('tags', []),
            notes=data.get('notes', '')
        )


class UserProfileManager:
    """
    User profile management system.
    
    Features:
    - Persistent profile storage
    - Preference management
    - Context learning
    - Multi-user support (future)
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path(__file__).parent.parent / 'data' / 'profile.json'
        self._profiles: Dict[str, UserProfile] = {}
        self._current_user: str = 'default'
        self._load()
    
    def _load(self):
        """Load profiles from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for user_id, profile_data in data.items():
                        self._profiles[user_id] = UserProfile.from_dict(profile_data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load user profiles: {e}")
        
        # Ensure default user exists
        if 'default' not in self._profiles:
            self._profiles['default'] = UserProfile()
    
    def _save(self):
        """Save profiles to storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {uid: profile.to_dict() for uid, profile in self._profiles.items()}
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save user profiles: {e}")
    
    @property
    def current_profile(self) -> UserProfile:
        """Get current user's profile."""
        return self._profiles.get(self._current_user, self._profiles['default'])
    
    def switch_user(self, user_id: str) -> UserProfile:
        """Switch to a different user profile."""
        if user_id not in self._profiles:
            self._profiles[user_id] = UserProfile(user_id=user_id)
        self._current_user = user_id
        return self.current_profile
    
    def update_preferences(self, **kwargs):
        """Update user preferences."""
        profile = self.current_profile
        for key, value in kwargs.items():
            if hasattr(profile.preferences, key):
                setattr(profile.preferences, key, value)
        profile.updated_at = datetime.now()
        self._save()
    
    def update_context(self, **kwargs):
        """Update personal context."""
        profile = self.current_profile
        for key, value in kwargs.items():
            if hasattr(profile.context, key):
                setattr(profile.context, key, value)
        profile.updated_at = datetime.now()
        self._save()
    
    def set_tool_config(self, tool_name: str, config: Dict[str, Any]):
        """Set configuration for a specific tool."""
        profile = self.current_profile
        profile.tool_configs[tool_name] = config
        profile.updated_at = datetime.now()
        self._save()
    
    def get_tool_config(self, tool_name: str) -> Dict[str, Any]:
        """Get configuration for a specific tool."""
        return self.current_profile.tool_configs.get(tool_name, {})
    
    def add_tag(self, tag: str):
        """Add a tag to the user profile."""
        profile = self.current_profile
        if tag not in profile.tags:
            profile.tags.append(tag)
            profile.updated_at = datetime.now()
            self._save()
    
    def remove_tag(self, tag: str):
        """Remove a tag from the user profile."""
        profile = self.current_profile
        if tag in profile.tags:
            profile.tags.remove(tag)
            profile.updated_at = datetime.now()
            self._save()
    
    def add_note(self, note: str):
        """Add/update profile notes."""
        profile = self.current_profile
        profile.notes = note
        profile.updated_at = datetime.now()
        self._save()
    
    def is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours."""
        profile = self.current_profile
        now = datetime.now().hour
        
        if profile.context.quiet_hours_start > profile.context.quiet_hours_end:
            # Quiet hours span midnight (e.g., 22:00 to 07:00)
            return now >= profile.context.quiet_hours_start or now < profile.context.quiet_hours_end
        else:
            # Quiet hours within same day
            return profile.context.quiet_hours_start <= now < profile.context.quiet_hours_end
    
    def is_work_hours(self) -> bool:
        """Check if current time is within work hours."""
        profile = self.current_profile
        now = datetime.now().hour
        return profile.context.work_hours_start <= now < profile.context.work_hours_end
    
    def requires_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires explicit confirmation."""
        profile = self.current_profile
        return tool_name in profile.preferences.require_confirmation_for
    
    def export_profile(self) -> str:
        """Export profile as JSON string."""
        return json.dumps(self.current_profile.to_dict(), indent=2)
    
    def import_profile(self, json_str: str, merge: bool = False):
        """Import profile from JSON string."""
        data = json.loads(json_str)
        new_profile = UserProfile.from_dict(data)
        
        if merge:
            # Merge with existing profile
            existing = self.current_profile
            existing.preferences = new_profile.preferences
            existing.context = new_profile.context
            existing.tool_configs.update(new_profile.tool_configs)
            existing.tags.extend(t for t in new_profile.tags if t not in existing.tags)
            existing.updated_at = datetime.now()
        else:
            # Replace profile
            self._profiles[self._current_user] = new_profile
        
        self._save()


# Singleton instance
_profile_manager: Optional[UserProfileManager] = None


def get_profile_manager(storage_path: Optional[Path] = None) -> UserProfileManager:
    """Get the singleton profile manager instance."""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = UserProfileManager(storage_path)
    return _profile_manager


def reset_profile_manager():
    """Reset the singleton instance (for testing)."""
    global _profile_manager
    _profile_manager = None


def get_current_profile() -> UserProfile:
    """Get current user profile."""
    return get_profile_manager().current_profile


def update_preferences(**kwargs):
    """Convenience function to update preferences."""
    get_profile_manager().update_preferences(**kwargs)


def update_context(**kwargs):
    """Convenience function to update context."""
    get_profile_manager().update_context(**kwargs)
