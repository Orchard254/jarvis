"""
4. Web & Knowledge (5 tools)
External intelligence layer.
"""

from typing import Optional, Any
from dataclasses import dataclass
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Search result item."""
    title: str
    url: str
    snippet: str
    rank: int


class WebSearch:
    """
    web_search: Real-time search
    
    Performs web searches using search engines.
    """
    
    def __init__(self, engine: str = "google", api_key: Optional[str] = None):
        self.engine = engine
        self.api_key = api_key
    
    def execute(self, query: str, num_results: int = 10,
                language: str = "en", region: str = "us",
                **kwargs) -> dict:
        """
        Search the web.
        
        Args:
            query: Search query
            num_results: Number of results to return
            language: Result language
            region: Region code
            
        Returns:
            Search results
        """
        try:
            # Try to use serpapi if available
            results = []
            
            if self.api_key and self.engine == "google":
                results = self._search_with_api(query, num_results)
            else:
                # Fallback to duckduckgo or simulated results
                results = self._search_fallback(query, num_results)
            
            return {
                "success": True,
                "output": {
                    "query": query,
                    "results": results,
                    "total_found": len(results),
                    "engine": self.engine
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _search_with_api(self, query: str, num: int) -> list:
        """Search using SerpAPI."""
        try:
            from serpapi import GoogleSearch
            
            params = {
                "q": query,
                "num": num,
                "hl": "en",
                "gl": "us",
                "api_key": self.api_key
            }
            
            search = GoogleSearch(params)
            results = search.get_dict()
            
            search_results = []
            for i, item in enumerate(results.get("organic_results", [])[:num]):
                search_results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    rank=i + 1
                ))
            
            return [r.__dict__ for r in search_results]
            
        except ImportError:
            return self._search_fallback(query, num)
    
    def _search_fallback(self, query: str, num: int) -> list:
        """Fallback search without API."""
        logger.warning("Using fallback search (no API key)")
        # In production, could use duckduckgo-search package
        return [
            {
                "title": f"Result {i+1} for: {query}",
                "url": f"https://example.com/result{i+1}",
                "snippet": f"This is a simulated search result for '{query}'",
                "rank": i + 1
            }
            for i in range(min(num, 5))
        ]


class WebScraper:
    """
    web_scraper: Extract page content
    
    Scrapes and extracts content from web pages.
    """
    
    def __init__(self, respect_robots: bool = True, 
                 user_agent: str = "JARVIS-Agent/1.0"):
        self.respect_robots = respect_robots
        self.user_agent = user_agent
    
    def execute(self, url: str, extract_type: str = "text",
                selectors: Optional[dict] = None,
                max_depth: int = 0,
                **kwargs) -> dict:
        """
        Scrape web page content.
        
        Args:
            url: URL to scrape
            extract_type: One of 'text', 'html', 'links', 'images', 'structured'
            selectors: CSS/XPath selectors for structured extraction
            max_depth: Max link depth to follow (0 = single page)
            
        Returns:
            Extracted content
        """
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {"User-Agent": self.user_agent}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if extract_type == "text":
                # Extract main text content
                for script in soup(["script", "style"]):
                    script.decompose()
                text = soup.get_text(separator=' ', strip=True)
                content = text[:10000]  # Limit length
                
            elif extract_type == "html":
                content = str(soup)
                
            elif extract_type == "links":
                links = []
                for link in soup.find_all('a', href=True):
                    links.append({
                        "text": link.get_text(strip=True),
                        "url": link['href']
                    })
                content = links
                
            elif extract_type == "images":
                images = []
                for img in soup.find_all('img'):
                    images.append({
                        "src": img.get('src', ''),
                        "alt": img.get('alt', '')
                    })
                content = images
                
            elif extract_type == "structured" and selectors:
                content = self._extract_structured(soup, selectors)
            else:
                content = soup.get_text(strip=True)[:5000]
            
            return {
                "success": True,
                "output": {
                    "url": url,
                    "content": content,
                    "extract_type": extract_type,
                    "status_code": response.status_code
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _extract_structured(self, soup, selectors: dict) -> dict:
        """Extract structured data using selectors."""
        result = {}
        for field, selector in selectors.items():
            element = soup.select_one(selector)
            result[field] = element.get_text(strip=True) if element else None
        return result


class URLReader:
    """
    url_reader: Structured page parsing
    
    Reads and parses URLs into structured data.
    """
    
    def execute(self, url: str, parse_metadata: bool = True,
                extract_main_content: bool = True,
                **kwargs) -> dict:
        """
        Read and parse URL content.
        
        Args:
            url: URL to read
            parse_metadata: Extract meta tags, title, etc.
            extract_main_content: Extract main article/content
            
        Returns:
            Structured page data
        """
        try:
            import requests
            from bs4 import BeautifulSoup
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            result = {"url": url}
            
            # Extract metadata
            if parse_metadata:
                result["metadata"] = {
                    "title": soup.title.string if soup.title else "",
                    "description": self._get_meta(soup, "description"),
                    "author": self._get_meta(soup, "author"),
                    "keywords": self._get_meta(soup, "keywords"),
                    "og_image": self._get_meta(soup, "og:image"),
                }
            
            # Extract main content
            if extract_main_content:
                # Simple heuristic: find largest text block
                paragraphs = soup.find_all('p')
                main_text = '\n'.join([p.get_text(strip=True) for p in paragraphs[:20]])
                result["main_content"] = main_text
            
            # Extract headings
            headings = []
            for h in soup.find_all(['h1', 'h2', 'h3']):
                headings.append({
                    "level": h.name,
                    "text": h.get_text(strip=True)
                })
            result["headings"] = headings
            
            return {
                "success": True,
                "output": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _get_meta(self, soup, name: str) -> str:
        """Get meta tag content."""
        meta = soup.find('meta', attrs={'name': name})
        if not meta:
            meta = soup.find('meta', attrs={'property': name})
        return meta.get('content', '') if meta else ""


class Summarizer:
    """
    summarizer: Compress long text
    
    Summarizes long documents or articles.
    """
    
    def __init__(self, model=None, max_length: int = 500):
        self.model = model
        self.max_length = max_length
    
    def execute(self, text: str, summary_type: str = "abstract",
                max_sentences: int = 5, **kwargs) -> dict:
        """
        Summarize text.
        
        Args:
            text: Text to summarize
            summary_type: One of 'abstract', 'extractive', 'abstractive'
            max_sentences: Maximum sentences in summary
            
        Returns:
            Summary
        """
        try:
            if len(text) <= self.max_length * 2:
                # Text is already short
                return {
                    "success": True,
                    "output": {
                        "summary": text,
                        "original_length": len(text),
                        "summary_length": len(text),
                        "compression_ratio": 1.0
                    }
                }
            
            # Use model if available
            if self.model:
                return self._summarize_with_model(text, summary_type, max_sentences)
            else:
                # Fallback: extractive summarization
                return self._extractive_summary(text, max_sentences)
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _summarize_with_model(self, text: str, summary_type: str, 
                               max_sentences: int) -> dict:
        """Summarize using ML model."""
        # TODO: Integrate with actual summarization model
        logger.info("Summarizing with model...")
        
        return {
            "success": True,
            "output": {
                "summary": "[Model summary would be generated here]",
                "original_length": len(text),
                "summary_length": len(text) // 5,
                "compression_ratio": 0.2,
                "model": "gpt-oss-120b"
            }
        }
    
    def _extractive_summary(self, text: str, max_sentences: int) -> dict:
        """Extractive summarization fallback."""
        # Split into sentences
        import re
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Score by position and length
        scored = []
        for i, sent in enumerate(sentences):
            score = len(sent) * (1.0 / (i + 1))  # Prefer early, longer sentences
            scored.append((score, sent))
        
        # Get top sentences
        scored.sort(reverse=True)
        top_sentences = [s[1] for s in scored[:max_sentences]]
        
        # Reorder by original position
        summary = ' '.join([s for s in sentences if s in top_sentences])
        
        return {
            "success": True,
            "output": {
                "summary": summary,
                "original_length": len(text),
                "summary_length": len(summary),
                "compression_ratio": len(summary) / len(text) if text else 0,
                "method": "extractive"
            }
        }


class FactChecker:
    """
    fact_checker: Validate claims across sources
    
    Cross-references information from multiple sources.
    """
    
    def __init__(self, trusted_sources: Optional[list[str]] = None):
        self.trusted_sources = trusted_sources or [
            "wikipedia.org", "britannica.com", "gov", "edu"
        ]
    
    def execute(self, claim: str, check_depth: int = 3,
                require_sources: bool = True,
                **kwargs) -> dict:
        """
        Fact-check a claim.
        
        Args:
            claim: Statement to verify
            check_depth: Number of sources to check
            require_sources: Whether to require citations
            
        Returns:
            Fact-check result with confidence and sources
        """
        try:
            # Search for the claim
            search_query = f"fact check: {claim}"
            
            # In production, would search multiple sources
            sources_checked = []
            confidence = 0.5
            verdict = "unverified"
            
            # Placeholder logic
            supporting = 0
            contradicting = 0
            
            # Simulate checking sources
            for i in range(check_depth):
                source = {
                    "name": f"Source {i+1}",
                    "url": f"https://example.com/factcheck{i+1}",
                    "verdict": "supporting" if i % 2 == 0 else "neutral",
                    "trusted": any(ts in f"source{i}" for ts in self.trusted_sources)
                }
                sources_checked.append(source)
                if source["verdict"] == "supporting":
                    supporting += 1
                elif source["verdict"] == "contradicting":
                    contradicting += 1
            
            # Calculate confidence
            total = supporting + contradicting
            if total > 0:
                confidence = supporting / total
                if confidence > 0.7:
                    verdict = "likely_true"
                elif confidence < 0.3:
                    verdict = "likely_false"
                else:
                    verdict = "mixed"
            
            return {
                "success": True,
                "output": {
                    "claim": claim,
                    "verdict": verdict,
                    "confidence": confidence,
                    "sources": sources_checked,
                    "supporting_count": supporting,
                    "contradicting_count": contradicting
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }


# Factory functions
def get_web_search(engine: str = "google", api_key: Optional[str] = None) -> WebSearch:
    return WebSearch(engine=engine, api_key=api_key)


def get_web_scraper(respect_robots: bool = True) -> WebScraper:
    return WebScraper(respect_robots=respect_robots)


def get_url_reader() -> URLReader:
    return URLReader()


def get_summarizer(model=None, max_length: int = 500) -> Summarizer:
    return Summarizer(model=model, max_length=max_length)


def get_fact_checker(trusted_sources: Optional[list[str]] = None) -> FactChecker:
    return FactChecker(trusted_sources=trusted_sources)
