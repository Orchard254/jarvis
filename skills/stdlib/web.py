"""skills.stdlib.web — web search and URL fetching.

The LLM should use browser(navigate) for web tasks. For programmatic
URL fetching, the LLM can write requests.get() via exec(run).
This module is kept for backward compatibility but the LLM should
prefer browser() or writing its own code.
"""

__all__: list[str] = []
