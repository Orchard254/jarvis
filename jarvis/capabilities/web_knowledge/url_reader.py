"""
URL Reader Capability
Structured page parsing and metadata extraction
"""

import requests
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from ..base import Capability


class URLReader(Capability):
    """Structured URL reading with metadata extraction"""
    
    def __init__(self, timeout: int = 10):
        """
        Initialize URL reader
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (JARVIS Agent)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        })
    
    def execute(self, url: str, include_content: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Read and parse URL structure
        
        Args:
            url: Target URL to read
            include_content: Whether to include full page content
            
        Returns:
            Dictionary with success status and structured page data
        """
        try:
            if not url or not url.startswith(('http://', 'https://')):
                return {"success": False, "error": "Invalid URL format"}
            
            # Fetch the page
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            parsed_url = urlparse(url)
            
            # Extract metadata
            metadata = {
                "url": url,
                "domain": parsed_url.netloc,
                "path": parsed_url.path,
                "title": self._get_title(soup),
                "description": self._get_meta_tag(soup, 'description'),
                "author": self._get_meta_tag(soup, 'author'),
                "keywords": self._get_meta_tag(soup, 'keywords'),
                "og_data": self._get_open_graph_data(soup),
                "language": self._get_language(soup),
                "content_type": response.headers.get('Content-Type', ''),
                "status_code": response.status_code,
                "final_url": response.url,
                "links_count": len(soup.find_all('a', href=True)),
                "images_count": len(soup.find_all('img')),
                "headings": self._get_headings(soup)
            }
            
            if include_content:
                metadata["content"] = self._extract_main_content(soup)
            
            return {
                "success": True,
                "output": metadata
            }
        except Exception as e:
            return {"success": False, "error": f"URL reading failed: {str(e)}"}
    
    def _get_title(self, soup: BeautifulSoup) -> str:
        """Extract page title"""
        if soup.title:
            return soup.title.string.strip()
        
        # Fallback to h1
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        return ""
    
    def _get_meta_tag(self, soup: BeautifulSoup, name: str) -> str:
        """Extract meta tag content"""
        # Try name attribute
        meta = soup.find('meta', attrs={'name': name})
        if meta and meta.get('content'):
            return meta['content'].strip()
        
        # Try property attribute (for Open Graph)
        meta = soup.find('meta', attrs={'property': f'og:{name}'})
        if meta and meta.get('content'):
            return meta['content'].strip()
        
        return ""
    
    def _get_open_graph_data(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Open Graph metadata"""
        og_data = {}
        for meta in soup.find_all('meta', attrs={'property': True}):
            prop = meta.get('property', '')
            if prop.startswith('og:'):
                key = prop[3:]  # Remove 'og:' prefix
                if meta.get('content'):
                    og_data[key] = meta['content'].strip()
        
        return og_data
    
    def _get_language(self, soup: BeautifulSoup) -> str:
        """Detect page language"""
        # Check html lang attribute
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            return html_tag['lang']
        
        # Check meta http-equiv
        meta = soup.find('meta', attrs={'http-equiv': 'content-language'})
        if meta and meta.get('content'):
            return meta['content']
        
        return ""
    
    def _get_headings(self, soup: BeautifulSoup) -> Dict[str, list]:
        """Extract heading structure"""
        headings = {}
        for level in range(1, 7):
            tags = soup.find_all(f'h{level}')
            if tags:
                headings[f'h{level}'] = [tag.get_text(strip=True) for tag in tags[:10]]
        
        return headings
    
    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main text content"""
        # Remove non-content elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            element.decompose()
        
        # Try to find main content area
        main = soup.find('main') or soup.find('article') or soup.find('div', class_=lambda x: x and ('content' in x.lower() or 'post' in x.lower()))
        
        if main:
            text = main.get_text(separator='\n', strip=True)
        else:
            text = soup.body.get_text(separator='\n', strip=True) if soup.body else ""
        
        # Clean and limit
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned = '\n'.join(lines)
        
        max_length = 15000
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length] + "... [truncated]"
        
        return cleaned


# Factory function
def create_capability(**kwargs) -> Capability:
    return URLReader(**kwargs)
