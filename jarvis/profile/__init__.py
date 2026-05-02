"""
JARVIS Profile Module - User profiles, learning, and routines.
"""

from .user_profile import (
    UserProfileManager, 
    get_profile_manager, 
    get_current_profile, 
    update_preferences, 
    update_context,
    UserProfile,
    UserPreferences,
    PersonalContext
)
from .learning import (
    LearningEngine,
    get_learning_engine,
    record_feedback,
    get_tool_preference,
    LearnedPattern,
    FeedbackRecord
)
from .routines import (
    RoutineManager,
    get_routine_manager,
    Routine,
    RoutineTrigger,
    RoutineStep,
    TriggerType
)

__all__ = [
    # User Profile
    'UserProfileManager',
    'get_profile_manager',
    'get_current_profile',
    'update_preferences',
    'update_context',
    'UserProfile',
    'UserPreferences',
    'PersonalContext',
    # Learning
    'LearningEngine',
    'get_learning_engine',
    'record_feedback',
    'get_tool_preference',
    'LearnedPattern',
    'FeedbackRecord',
    # Routines
    'RoutineManager',
    'get_routine_manager',
    'Routine',
    'RoutineTrigger',
    'RoutineStep',
    'TriggerType'
]
