"""
JARVIS Skills Module - Specialized capabilities with state management.
"""

from .base import BaseSkill, register_skill, get_registered_skills
from .registry import SkillsRegistry as SkillRegistry, get_registry as get_skill_registry
from .builtin.morning_briefing import MorningBriefing
from .builtin.focus_mode import FocusMode
from .builtin.task_executor import TaskExecutorSkill
from .builtin.system_optimizer import SystemOptimizerSkill as ResearchSkill
from .supervisor import SupervisorSkill

# Alias for consistency
MorningBriefingSkill = MorningBriefing
FocusModeSkill = FocusMode

__all__ = [
    'BaseSkill',
    'register_skill',
    'get_registered_skills',
    'SkillRegistry',
    'get_skill_registry',
    'MorningBriefingSkill',
    'MorningBriefing',
    'FocusModeSkill',
    'FocusMode',
    'TaskExecutorSkill',
    'ResearchSkill',
    'SupervisorSkill'
]