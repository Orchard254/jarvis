"""Web tools module."""

from .browser import WEB_TOOLS
from .automation import WEB_AUTOMATION_TOOLS

# Visual automation tools are optional (require opencv-python)
try:
    from .visual_automation import VISUAL_AUTOMATION_TOOLS
except ImportError:
    VISUAL_AUTOMATION_TOOLS = []

# Combine basic browser tools with advanced automation tools and visual automation
__all__ = ["WEB_TOOLS", "WEB_AUTOMATION_TOOLS"]
if VISUAL_AUTOMATION_TOOLS:
    __all__.append("VISUAL_AUTOMATION_TOOLS")

# Export combined list for tool registry
ALL_WEB_TOOLS = WEB_TOOLS + WEB_AUTOMATION_TOOLS + VISUAL_AUTOMATION_TOOLS
