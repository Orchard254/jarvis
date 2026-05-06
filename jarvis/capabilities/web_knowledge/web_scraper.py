"""
Web Scraper Capability
Extract structured content from web pages
"""

import requests
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
from ..base import Capability


class WebScraper(Capability):
    """Extract structured content from web pages"""
    
    def __init__(self, timeout: int = 10):
        """
        Initialize web scraper
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (JARVIS Agent)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        })
    
    def execute(self, url: str, extract_type: str = "content", 
                selectors: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        Scrape and extract content from a web page
        
        Args:
            url: Target URL to scrape
            extract_type: Type of extraction (content, links, images, tables, custom)
            selectors: CSS selectors for custom extraction
            
        Returns:
            Dictionary with success status and extracted data
        """
        try:
            if not url or not url.startswith(('http://', 'https://')):
                return {"success": False, "error": "Invalid URL format"}
            
            # Fetch the page
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if extract_type == "content":
                data = self._extract_content(soup, url)
            elif extract_type == "links":
                data = self._extract_links(soup, url)
            elif extract_type == "images":
                data = self._extract_images(soup, url)
            elif extract_type == "tables":
                data = self._extract_tables(soup)
            elif extract_type == "custom" and selectors:
                data = self._extract_custom(soup, selectors)
            else:
                data = self._extract_content(soup, url)
            
            return {
                "success": True,
                "output": {
                    "url": url,
                    "extract_type": extract_type,
                    "data": data
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Scraping failed: {str(e)}"}
    
    def _extract_content(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract main text content"""
        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()
        
        # Get title
        title = soup.title.string if soup.title else ""
        
        # Extract main content (try common containers first)
        main_content = ""
        for tag in ['article', 'main', 'div.content', 'div.post']:
            element = soup.select_one(tag)
            if element:
                main_content = element.get_text(separator='\n', strip=True)
                break
        
        # Fallback to body
        if not main_content:
            main_content = soup.body.get_text(separator='\n', strip=True) if soup.body else ""
        
        # Clean up whitespace
        lines = [line.strip() for line in main_content.splitlines() if line.strip()]
        cleaned_text = '\n'.join(lines)
        
        # Limit size
        max_length = 10000
        if len(cleaned_text) > max_length:
            cleaned_text = cleaned_text[:max_length] + "... [truncated]"
        
        return {
            "title": title,
            "content": cleaned_text,
            "word_count": len(cleaned_text.split())
        }
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract all links from page"""
        links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            text = a_tag.get_text(strip=True)
            
            # Convert relative URLs to absolute
            if href.startswith('/'):
                from urllib.parse import urljoin
                href = urljoin(base_url, href)
            elif not href.startswith(('http://', 'https://')):
                continue
            
            links.append({
                "url": href,
                "text": text,
                "title": a_tag.get('title', '')
            })
        
        return links[:50]  # Limit to 50 links
    
    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract all images from page"""
        images = []
        for img_tag in soup.find_all('img', src=True):
            src = img_tag['src'].strip()
            
            # Convert relative URLs to absolute
            if src.startswith('/'):
                from urllib.parse import urljoin
                src = urljoin(base_url, src)
            elif not src.startswith(('http://', 'https://')):
                continue
            
            images.append({
                "url": src,
                "alt": img_tag.get('alt', ''),
                "width": img_tag.get('width', ''),
                "height": img_tag.get('height', '')
            })
        
        return images[:30]  # Limit to 30 images
    
    def _extract_tables(self, soup: BeautifulSoup) -> List[List[List[str]]]:
        """Extract all tables from page"""
        tables = []
        for table in soup.find_all('table'):
            table_data = []
            rows = table.find_all(['tr', 'thead', 'tbody'])
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    table_data.append(row_data)
            if table_data:
                tables.append(table_data)
        
        return tables[:10]  # Limit to 10 tables
    
    def _extract_custom(self, soup: BeautifulSoup, selectors: Dict[str, str]) -> Dict:
        """Extract content using custom CSS selectors"""
        results = {}
        for name, selector in selectors.items():
            elements = soup.select(selector)
            if elements:
                if len(elements) == 1:
                    results[name] = elements[0].get_text(strip=True)
                else:
                    results[name] = [el.get_text(strip=True) for el in elements]
            else:
                results[name] = None
        
        return results


# Factory function
def create_capability(**kwargs) -> Capability:
    return WebScraper(**kwargs)
