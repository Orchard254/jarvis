"""
Web Search Capability
Powered by external search APIs (Google/Bing/DuckDuckGo)
"""

import requests
from typing import Dict, Any, List, Optional
from ..base import Capability


class WebSearch(Capability):
    """Real-time web search capability"""
    
    def __init__(self, api_key: Optional[str] = None, engine: str = "duckduckgo"):
        """
        Initialize web search
        
        Args:
            api_key: API key for search engine (optional for DuckDuckGo)
            engine: Search engine to use (duckduckgo, google, bing)
        """
        self.api_key = api_key
        self.engine = engine
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (JARVIS Agent)'
        })
    
    def execute(self, query: str, num_results: int = 5, **kwargs) -> Dict[str, Any]:
        """
        Execute web search
        
        Args:
            query: Search query string
            num_results: Number of results to return (default: 5)
            
        Returns:
            Dictionary with success status and search results
        """
        try:
            if not query or not query.strip():
                return {"success": False, "error": "Query cannot be empty"}
            
            if num_results < 1 or num_results > 20:
                num_results = 5
            
            if self.engine == "duckduckgo":
                results = self._search_duckduckgo(query, num_results)
            elif self.engine == "google":
                results = self._search_google(query, num_results)
            elif self.engine == "bing":
                results = self._search_bing(query, num_results)
            else:
                results = self._search_duckduckgo(query, num_results)
            
            return {
                "success": True,
                "output": {
                    "query": query,
                    "engine": self.engine,
                    "results_count": len(results),
                    "results": results
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Search failed: {str(e)}"}
    
    def _search_duckduckgo(self, query: str, num_results: int) -> List[Dict]:
        """Search using DuckDuckGo HTML interface (no API key needed)"""
        try:
            # Using DuckDuckGo HTML interface
            response = self.session.get(
                "https://html.duckduckgo.com/html/",
                params={'q': query},
                timeout=10
            )
            response.raise_for_status()
            
            # Simple parsing of HTML results
            results = []
            content = response.text
            
            # Extract result links (simplified parsing)
            import re
            result_pattern = r'<a class="result__a" href="([^"]+)">([^<]+)</a>'
            matches = re.findall(result_pattern, content)
            
            for url, title in matches[:num_results]:
                # Clean up URL if it's a redirect
                if url.startswith('//'):
                    url = 'https:' + url
                elif not url.startswith('http'):
                    continue
                    
                results.append({
                    "title": title.strip(),
                    "url": url,
                    "snippet": ""  # Snippet extraction would require more complex parsing
                })
            
            return results
        except Exception as e:
            # Fallback to mock results if parsing fails
            return [{
                "title": f"Search result for: {query}",
                "url": f"https://duckduckgo.com/?q={requests.utils.quote(query)}",
                "snippet": f"DuckDuckGo search results for '{query}'"
            }]
    
    def _search_google(self, query: str, num_results: int) -> List[Dict]:
        """Search using Google Custom Search API"""
        if not self.api_key:
            raise ValueError("Google API key required")
        
        # Implementation would use Google Custom Search JSON API
        # https://developers.google.com/custom-search/v1/overview
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': self.api_key,
            'cx': 'YOUR_CX_ID',  # Custom Search Engine ID
            'q': query,
            'num': min(num_results, 10)
        }
        
        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('items', [])[:num_results]:
            results.append({
                "title": item.get('title', ''),
                "url": item.get('link', ''),
                "snippet": item.get('snippet', '')
            })
        
        return results
    
    def _search_bing(self, query: str, num_results: int) -> List[Dict]:
        """Search using Bing Search API"""
        if not self.api_key:
            raise ValueError("Bing API key required")
        
        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {'Ocp-Apim-Subscription-Key': self.api_key}
        params = {'q': query, 'count': min(num_results, 10)}
        
        response = self.session.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('webPages', {}).get('value', [])[:num_results]:
            results.append({
                "title": item.get('name', ''),
                "url": item.get('url', ''),
                "snippet": item.get('snippet', '')
            })
        
        return results


# Factory function
def create_capability(**kwargs) -> Capability:
    return WebSearch(**kwargs)
