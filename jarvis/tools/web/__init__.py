"""Web tools module."""

from .browser import WEB_TOOLS
from .automation import WEB_AUTOMATION_TOOLS

# Combine basic browser tools with advanced automation tools
__all__ = ["WEB_TOOLS", "WEB_AUTOMATION_TOOLS"]

# Export combined list for tool registry
ALL_WEB_TOOLS = WEB_TOOLS + WEB_AUTOMATION_TOOLS
