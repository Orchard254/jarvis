"""
Sub-agent implementations for JARVIS.

Each module in this package defines one specialized sub-agent and registers
it with the global registry on import.

Import this package once at startup to activate all sub-agents:

    import agents.sub_agents  # noqa: F401  (triggers all registrations)

Or import individual agents:

    from agents.sub_agents.research_agent import ResearchAgent
"""

from agents.sub_agents import research_agent     # noqa: F401
from agents.sub_agents import file_agent         # noqa: F401
from agents.sub_agents import system_agent       # noqa: F401
from agents.sub_agents import perception_agent   # noqa: F401
from agents.sub_agents import interaction_agent  # noqa: F401
from agents.sub_agents import memory_agent       # noqa: F401
from agents.sub_agents import proactive_agent    # noqa: F401

__all__ = [
    "research_agent",
    "file_agent",
    "system_agent",
    "perception_agent",
    "interaction_agent",
    "memory_agent",
    "proactive_agent",
]
