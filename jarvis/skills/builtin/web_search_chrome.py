"""
Skill: Web Search using Existing Chrome.

Opens search in user's existing Chrome browser instead of launching new instance.
Uses Windows 'start chrome' command which opens new tab in existing Chrome.
"""

import logging
import subprocess
import time
import urllib.parse
from typing import Any, Dict, Optional

from ..base import BaseSkill, SkillResult
from ...tools.registry import execute_tool

logger = logging.getLogger(__name__)


class WebSearchChromeSkill(BaseSkill):
    """
    Perform web search using the user's existing Chrome browser.
    
    Opens a new tab in existing Chrome (if running) or launches Chrome with user's profile.
    Avoids creating new Chrome instances with clean profiles.
    """
    
    name = "web_search_chrome"
    description = "Search the web using your existing Chrome browser (opens new tab)."
    
    TRIGGERS = [
        "search for",
        "search the web",
        "google",
        "look up",
        "find information about",
    ]
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for this skill."""
        return "You are a web search assistant that opens searches in the user's existing Chrome browser."
    
    def can_handle(self, task: str) -> float:
        """Check if this skill can handle the given request."""
        cmd_lower = task.lower()
        if any(trigger in cmd_lower for trigger in self.TRIGGERS):
            return 0.9
        return 0.0
    
    def plan(self, task: str) -> list:
        """Create a plan of steps to accomplish the task."""
        query = self._extract_query(task)
        return [{
            'id': 'search',
            'name': 'Execute web search',
            'action': 'search',
            'params': {'query': query},
            'completed': False
        }]
    
    def execute(self, plan: list) -> Dict[str, Any]:
        """Execute the skill with state tracking."""
        try:
            # Extract query from the first step
            query = plan[0]['params'].get('query', '') if plan else ''
            if not query:
                return {'success': False, 'error': 'No search query provided'}
            
            success, message = self._open_in_existing_chrome(query)
            
            if success:
                return {
                    'success': True,
                    'output': f"Opened search for '{query}' in Chrome",
                    'metadata': {'query': query, 'method': 'existing_chrome'}
                }
            
            # Fallback to automation
            return self._search_via_automation_dict(query)
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _search_via_automation_dict(self, query: str) -> Dict[str, Any]:
        """Fallback: use automation engine for search (dict version)."""
        try:
            # Use the existing automation tools
            result1 = execute_tool("navigate_to_url", url="https://www.google.com")
            
            if not result1.get('success', False):
                return {'success': False, 'error': f"Navigation failed: {result1.get('error', 'Unknown error')}"}
            
            time.sleep(1)
            
            result2 = execute_tool("fill_input", selector="input[name='q']", value=query)
            
            if not result2.get('success', False):
                return {'success': False, 'error': f"Fill input failed: {result2.get('error', 'Unknown error')}"}
            
            time.sleep(0.5)
            
            result3 = execute_tool("press_key", keys="Enter")
            
            return {
                'success': True,
                'output': f"Search executed via automation: {query}",
                'metadata': {"query": query, "method": "automation"}
            }
            
        except Exception as e:
            logger.error(f"Automation search failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def handle_failure(self, step: Any, error: Exception) -> Any:
        """Handle a failure during step execution."""
        logger.error(f"Step failed: {error}")
        return None
    
    def rollback(self) -> Dict[str, Any]:
        """Undo completed steps in reverse order."""
        return {'success': True, 'message': 'No actions to rollback for web search'}
    
    def summarize(self) -> str:
        """Provide a one-sentence summary of what was accomplished."""
        return "Web search completed."
    
    def execute_search(self, command: str, context: Optional[Dict] = None) -> SkillResult:
        """
        Execute web search in existing Chrome.
        
        Args:
            command: User's search command
            context: Optional context dict
            
        Returns:
            SkillResult with success/failure
        """
        # Extract search query from command
        query = self._extract_query(command)
        if not query:
            return SkillResult.fail(error="Could not extract search query")
        
        logger.info(f"Searching for: {query}")
        
        # Try to use existing Chrome
        success, message = self._open_in_existing_chrome(query)
        
        if success:
            return SkillResult.ok(
                output=f"Opened search for '{query}' in Chrome",
                metadata={"query": query, "method": "existing_chrome"}
            )
        
        # Fallback: use automation engine
        logger.info("Fallback to automation engine for search")
        return self._search_via_automation(query)
    
    def _extract_query(self, command: str) -> str:
        """Extract search query from command."""
        cmd_lower = command.lower()
        
        # Remove common prefixes
        prefixes = ["search for", "search the web for", "google", "look up", "find information about"]
        query = command
        for prefix in prefixes:
            if prefix in cmd_lower:
                idx = cmd_lower.index(prefix) + len(prefix)
                query = command[idx:].strip()
                break
        
        return query
    
    def _open_in_existing_chrome(self, query: str) -> tuple[bool, str]:
        """
        Open search in existing Chrome browser.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            import psutil
            
            # Check if Chrome is running
            chrome_running = False
            for proc in psutil.process_iter(['name']):
                try:
                    if 'chrome' in proc.info['name'].lower():
                        chrome_running = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            
            if chrome_running:
                # Chrome is running - open new tab with search URL
                # On Windows, 'start chrome URL' opens new tab in existing Chrome
                result = subprocess.run(
                    ["cmd", "/c", f"start chrome \"{search_url}\""],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    logger.info(f"Opened new tab in existing Chrome: {search_url}")
                    return True, f"Opened search in existing Chrome"
                else:
                    logger.warning(f"Failed to open in Chrome: {result.stderr}")
                    return False, result.stderr
            else:
                # Launch Chrome (Windows will use default profile)
                result = subprocess.run(
                    ["cmd", "/c", f"start chrome \"{search_url}\""],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    return True, "Launched Chrome with search"
                return False, result.stderr
            
        except Exception as e:
            logger.error(f"Error opening in Chrome: {e}")
            return False, str(e)
    
    def _search_via_automation(self, query: str) -> SkillResult:
        """Fallback: use automation engine for search."""
        try:
            # Use the existing automation tools
            result1 = execute_tool("navigate_to_url", url="https://www.google.com")
            
            if not result1.success:
                return SkillResult.fail(error=f"Navigation failed: {result1.error}")
            
            time.sleep(1)
            
            result2 = execute_tool("fill_input", selector="input[name='q']", value=query)
            
            if not result2.success:
                return SkillResult.fail(error=f"Fill input failed: {result2.error}")
            
            time.sleep(0.5)
            
            result3 = execute_tool("press_key", keys="Enter")
            
            return SkillResult.ok(
                output=f"Search executed via automation: {query}",
                metadata={"query": query, "method": "automation"}
            )
            
        except Exception as e:
            logger.error(f"Automation search failed: {e}")
            return SkillResult.fail(error=str(e))
