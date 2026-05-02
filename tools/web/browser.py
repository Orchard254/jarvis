"""
tools/web/browser.py — Web browser tools

Tools for: search web, open URL
Uses subprocess and webbrowser module.
"""

import logging
import subprocess
import urllib.parse
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("web_tools")


class SearchWebTool(BaseTool):
    """Search the web using default search engine."""
    
    name = "search_web"
    description = "Search the web using Google. Opens search results in the default browser."
    parameters = {
        "query": {
            "type": "string",
            "description": "Search query string",
        },
    }
    required_parameters = ["query"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        query = kwargs.get("query")
        if not query or not isinstance(query, str):
            return False, "query must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        query = kwargs["query"]
        
        try:
            # URL encode the query
            encoded_query = urllib.parse.quote_plus(query)
            search_url = f"https://www.google.com/search?q={encoded_query}"
            
            # Open in default browser
            import webbrowser
            webbrowser.open(search_url)
            
            return ToolResult.ok(f"Searching for: {query}")
            
        except Exception as e:
            log.error(f"Web search failed: {e}")
            return ToolResult.fail(error=f"Web search failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class OpenUrlTool(BaseTool):
    """Open a specific URL in the browser."""
    
    name = "open_url"
    description = "Open a specific URL in the default web browser."
    parameters = {
        "url": {
            "type": "string",
            "description": "Full URL to open (including http:// or https://)",
        },
    }
    required_parameters = ["url"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        url = kwargs.get("url")
        if not url or not isinstance(url, str):
            return False, "url must be a non-empty string"
        
        # Basic URL validation
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "URL must start with http:// or https://"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        url = kwargs["url"]
        
        try:
            import webbrowser
            webbrowser.open(url)
            
            return ToolResult.ok(f"Opening: {url}")
            
        except Exception as e:
            log.error(f"Failed to open URL: {e}")
            return ToolResult.fail(error=f"Failed to open URL: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
WEB_TOOLS = [
    SearchWebTool,
    OpenUrlTool,
]
