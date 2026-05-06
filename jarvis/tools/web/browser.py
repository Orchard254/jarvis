"""
tools/web/browser.py — Web browser tools

Tools for: search web, open URL, close browser, search within site
Uses subprocess, webbrowser module, and selenium for advanced control.
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

            # Use automation engine to open in Chrome with debug port (so extract_content works)
            try:
                from jarvis.tools.web.automation import get_automation_engine
                engine = get_automation_engine()
                page = engine.ensure_browser(headless=False, use_existing=True)
                page.goto(search_url, timeout=15000)
                return ToolResult.ok(f"Searching for: {query}")
            except Exception as automation_err:
                log.warning(f"Automation engine failed, falling back to default browser: {automation_err}")
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


class CloseBrowserTool(BaseTool):
    """Close the web browser or all browser windows.
    
    IMPORTANT: This tool closes ENTIRE browser windows/processes.
    - To close a single tab, use close_tab instead
    - To close an application window (Notepad, etc.), use close_window instead
    
    Use this when you want to completely exit Chrome, Firefox, Edge, etc.
    """
    
    name = "close_browser"
    description = "Close entire browser windows/processes (Chrome, Firefox, Edge). Use ONLY to completely exit browsers. For closing individual tabs use close_tab. For closing app windows use close_window."
    parameters = {
        "browser": {
            "type": "string",
            "description": "Browser name to close (chrome, firefox, edge, or 'all' for all browsers). Default: 'all'",
            "default": "all",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        browser = kwargs.get("browser", "all")
        if not isinstance(browser, str):
            return False, "browser must be a string"
        
        valid_browsers = ["chrome", "firefox", "edge", "all"]
        if browser.lower() not in valid_browsers:
            return False, f"browser must be one of: {', '.join(valid_browsers)}"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        browser = kwargs.get("browser", "all").lower()
        
        try:
            import subprocess
            
            if browser == "chrome":
                process_names = ["chrome", "chromium"]
            elif browser == "firefox":
                process_names = ["firefox"]
            elif browser == "edge":
                process_names = ["msedge"]
            else:  # all
                process_names = ["chrome", "chromium", "firefox", "msedge"]
            
            closed_count = 0
            for proc_name in process_names:
                try:
                    # Windows: use taskkill
                    import platform
                    if platform.system() == "Windows":
                        result = subprocess.run(
                            ["taskkill", "/F", "/IM", f"{proc_name}.exe"],
                            capture_output=True,
                            text=True
                        )
                        if result.returncode == 0:
                            closed_count += 1
                    else:
                        # Linux/Mac: use pkill
                        result = subprocess.run(
                            ["pkill", "-f", proc_name],
                            capture_output=True,
                            text=True
                        )
                        if result.returncode == 0:
                            closed_count += 1
                except Exception:
                    pass  # Continue trying other browsers
            
            if closed_count > 0:
                return ToolResult.ok(f"Closed {closed_count} browser process(es)")
            else:
                return ToolResult.ok("No browser processes found running")
            
        except Exception as e:
            log.error(f"Failed to close browser: {e}")
            return ToolResult.fail(error=f"Failed to close browser: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "medium"


class SearchInSiteTool(BaseTool):
    """Search within a specific website using site-specific search."""
    
    name = "search_in_site"
    description = "Search within a specific website. Opens the site's search results page in the browser."
    parameters = {
        "query": {
            "type": "string",
            "description": "Search query string",
        },
        "site": {
            "type": "string",
            "description": "Website domain (e.g., 'jiji.co.ke', 'amazon.com')",
        },
    }
    required_parameters = ["query", "site"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        query = kwargs.get("query")
        site = kwargs.get("site")
        
        if not query or not isinstance(query, str):
            return False, "query must be a non-empty string"
        if not site or not isinstance(site, str):
            return False, "site must be a non-empty string"
        
        # Basic site validation
        if "." not in site:
            return False, "site must be a valid domain (e.g., 'example.com')"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        query = kwargs["query"]
        site = kwargs["site"]
        
        try:
            import webbrowser
            
            # Clean site URL (remove http/https prefix if present)
            site_clean = site.replace("http://", "").replace("https://", "").split("/")[0]
            
            # Try common search URL patterns
            search_url = None
            
            # Pattern 1: site.com/search?query=...
            # Pattern 2: site.com?s=...
            # Pattern 3: Use Google site: operator as fallback
            
            # For known sites, use specific patterns
            if "jiji" in site_clean:
                search_url = f"https://www.{site_clean}/search?query={urllib.parse.quote(query)}"
            elif "amazon" in site_clean:
                search_url = f"https://www.{site_clean}/s?k={urllib.parse.quote(query)}"
            elif "ebay" in site_clean:
                search_url = f"https://www.{site_clean}/sch/i.html?_nkw={urllib.parse.quote(query)}"
            else:
                # Fallback: Use Google site-specific search
                search_url = f"https://www.google.com/search?q=site:{site_clean}+{urllib.parse.quote_plus(query)}"
            
            webbrowser.open(search_url)
            
            return ToolResult.ok(f"Searching for '{query}' on {site_clean}")
            
        except Exception as e:
            log.error(f"Site search failed: {e}")
            return ToolResult.fail(error=f"Site search failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
WEB_TOOLS = [
    SearchWebTool,
    OpenUrlTool,
    CloseBrowserTool,
    SearchInSiteTool,
]
