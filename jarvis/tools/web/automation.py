"""
jarvis/tools/web/automation.py — Advanced Web Automation
DOM-level control using Playwright for reliable, verifiable web interactions.
Replaces blind "open URL" with precise element interaction and state verification.
"""

import logging
import time
from typing import Any, Optional, List, Dict
from pathlib import Path

from ..base import BaseTool, ToolResult

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api._generated import Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None
    Browser = None
    BrowserContext = None
    logging.warning("Playwright not installed. Advanced web automation disabled.")

logger = logging.getLogger("web_automation")


class WebAutomationEngine:
    """
    Singleton engine managing Playwright browser instance.
    Provides persistent browser session for multi-step tasks.
    """
    
    _instance: Optional['WebAutomationEngine'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not available")
            
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._initialized = True
        logger.info("WebAutomationEngine initialized")
    
    def start(self, headless: bool = False):
        """Start browser instance."""
        if self.browser is not None:
            return
            
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.page = self.context.new_page()
        logger.info(f"Browser started (headless={headless})")
    
    def stop(self):
        """Close browser and cleanup."""
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        self.page = None
        self.context = None
        logger.info("Browser stopped")
    
    def ensure_browser(self, headless: bool = False):
        """Ensure browser is running, start if needed."""
        if self.browser is None:
            self.start(headless=headless)
        return self.page
    
    def get_page(self) -> Optional[Page]:
        return self.page
    
    def get_current_url(self) -> str:
        if self.page:
            return self.page.url
        return ""
    
    def get_page_content_summary(self, max_length: int = 1000) -> Dict:
        """Get text content of current page for LLM context."""
        if not self.page:
            return {"status": "error", "message": "No page loaded"}
        
        try:
            # Get visible text content
            text = self.page.content_text()[:max_length]
            title = self.page.title()
            
            return {
                "status": "success",
                "title": title,
                "url": self.page.url,
                "content_sample": text,
                "text_length": len(text)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Global engine instance
_engine: Optional[WebAutomationEngine] = None

def get_automation_engine() -> WebAutomationEngine:
    global _engine
    if _engine is None:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed")
        _engine = WebAutomationEngine()
    return _engine


class NavigateToUrlTool(BaseTool):
    """Navigate to URL with verification and wait for load."""
    
    name = "navigate_to_url"
    description = "Navigate to a URL and wait for page to fully load. Returns page title and status."
    parameters = {
        "url": {"type": "string", "description": "Full URL to navigate to"},
        "wait_for_selector": {
            "type": "string", 
            "description": "Optional CSS selector to wait for (e.g., '.search-results')",
            "default": None
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in milliseconds (default: 30000)",
            "default": 30000
        }
    }
    required_parameters = ["url"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        url = kwargs.get("url")
        if not url or not isinstance(url, str):
            return False, "url must be a non-empty string"
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "URL must start with http:// or https://"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        url = kwargs["url"]
        wait_for = kwargs.get("wait_for_selector")
        timeout = kwargs.get("timeout", 30000)
        
        try:
            engine = get_automation_engine()
            page = engine.ensure_browser(headless=False)
            
            logger.info(f"Navigating to: {url}")
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            
            # Wait for specific element if requested
            if wait_for:
                page.wait_for_selector(wait_for, timeout=timeout)
                logger.info(f"Waited for selector: {wait_for}")
            
            # Small delay for dynamic content
            time.sleep(1)
            
            title = page.title()
            return ToolResult.ok(f"Loaded: {title} ({url})")
            
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return ToolResult.fail(error=f"Navigation failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 3.0
    
    def risk_level(self) -> str:
        return "low"


class ClickElementTool(BaseTool):
    """Click an element identified by selector or text."""
    
    name = "click_element"
    description = "Click a button, link, or interactive element. Use CSS selector or visible text."
    parameters = {
        "selector": {
            "type": "string",
            "description": "CSS selector (e.g., 'button.search-btn') OR visible text (prefix with text:)"
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in ms to find element",
            "default": 10000
        }
    }
    required_parameters = ["selector"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        selector = kwargs.get("selector")
        if not selector or not isinstance(selector, str):
            return False, "selector must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        selector = kwargs["selector"]
        timeout = kwargs.get("timeout", 10000)
        
        try:
            engine = get_automation_engine()
            page = engine.get_page()
            
            if not page:
                return ToolResult.fail(error="No page loaded. Navigate first.")
            
            # Handle text-based selection
            if selector.startswith("text:"):
                text = selector[5:]
                locator = page.get_by_text(text, exact=False)
            else:
                locator = page.locator(selector).first
            
            # Wait for element and click
            locator.wait_for(state="visible", timeout=timeout)
            locator.click()
            
            logger.info(f"Clicked: {selector}")
            time.sleep(0.5)  # Allow UI to update
            
            return ToolResult.ok(f"Clicked: {selector}")
            
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return ToolResult.fail(error=f"Click failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.5
    
    def risk_level(self) -> str:
        return "low"


class FillInputTool(BaseTool):
    """Fill text into an input field."""
    
    name = "fill_input"
    description = "Type text into an input field. Use CSS selector or label text."
    parameters = {
        "selector": {
            "type": "string",
            "description": "CSS selector for input OR label text (prefix with label:)"
        },
        "value": {
            "type": "string",
            "description": "Text to type into the field"
        },
        "clear_first": {
            "type": "boolean",
            "description": "Clear existing value before typing",
            "default": True
        }
    }
    required_parameters = ["selector", "value"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        selector = kwargs.get("selector")
        value = kwargs.get("value")
        if not selector or not isinstance(selector, str):
            return False, "selector must be a string"
        if value is None or not isinstance(value, str):
            return False, "value must be a string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        selector = kwargs["selector"]
        value = kwargs["value"]
        clear = kwargs.get("clear_first", True)
        
        try:
            engine = get_automation_engine()
            page = engine.get_page()
            
            if not page:
                return ToolResult.fail(error="No page loaded")
            
            # Handle label-based selection
            if selector.startswith("label:"):
                label = selector[6:]
                locator = page.get_by_label(label)
            else:
                locator = page.locator(selector).first
            
            locator.wait_for(state="visible", timeout=10000)
            
            if clear:
                locator.fill("")
            locator.fill(value)
            
            logger.info(f"Filled '{selector}' with: {value[:50]}...")
            return ToolResult.ok(f"Entered text into {selector}")
            
        except Exception as e:
            logger.error(f"Fill failed: {e}")
            return ToolResult.fail(error=f"Fill failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class ExtractContentTool(BaseTool):
    """Extract structured data from current page."""
    
    name = "extract_content"
    description = "Extract text, links, or table data from current page. Specify what to extract."
    parameters = {
        "mode": {
            "type": "string",
            "description": "What to extract: 'text', 'links', 'tables', 'prices'",
            "enum": ["text", "links", "tables", "prices"]
        },
        "selector": {
            "type": "string",
            "description": "Optional CSS selector to limit extraction scope",
            "default": None
        },
        "limit": {
            "type": "integer",
            "description": "Max items to return (for links/tables/prices)",
            "default": 20
        }
    }
    required_parameters = ["mode"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        mode = kwargs.get("mode")
        valid_modes = ["text", "links", "tables", "prices"]
        if not mode or mode not in valid_modes:
            return False, f"mode must be one of: {valid_modes}"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        mode = kwargs["mode"]
        selector = kwargs.get("selector")
        limit = kwargs.get("limit", 20)
        
        try:
            engine = get_automation_engine()
            page = engine.get_page()
            
            if not page:
                return ToolResult.fail(error="No page loaded")
            
            base_locator = page.locator(selector) if selector else page
            
            if mode == "text":
                text = base_locator.text_content()[:2000]
                return ToolResult.ok(f"Page text:\n{text}")
            
            elif mode == "links":
                links = base_locator.locator("a").all()[:limit]
                results = [{"text": l.text_content(), "href": l.get_attribute("href")} for l in links]
                return ToolResult.ok({"links": results})
            
            elif mode == "prices":
                # Common price patterns
                price_selectors = [".price", "[class*='price']", "[data-price]", ".cost"]
                prices = []
                for sel in price_selectors:
                    elements = base_locator.locator(sel).all()[:limit]
                    for el in elements:
                        text = el.text_content().strip()
                        if text:
                            prices.append(text)
                return ToolResult.ok({"prices": list(set(prices))[:limit]})
            
            elif mode == "tables":
                tables = base_locator.locator("table").all()[:limit]
                results = []
                for table in tables:
                    rows = table.locator("tr").all()[:10]
                    table_data = []
                    for row in rows:
                        cells = row.locator("td, th").all()
                        row_data = [c.text_content().strip() for c in cells]
                        table_data.append(row_data)
                    results.append(table_data)
                return ToolResult.ok({"tables": results})
            
            return ToolResult.fail(error=f"Unknown mode: {mode}")
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ToolResult.fail(error=f"Extraction failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.0
    
    def risk_level(self) -> str:
        return "low"


class WaitForElementTool(BaseTool):
    """Wait for a specific element to appear on page."""
    
    name = "wait_for_element"
    description = "Wait for an element to become visible. Useful for dynamic pages."
    parameters = {
        "selector": {
            "type": "string",
            "description": "CSS selector to wait for"
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in milliseconds",
            "default": 15000
        },
        "state": {
            "type": "string",
            "description": "Expected state: visible, hidden, attached, detached",
            "enum": ["visible", "hidden", "attached", "detached"],
            "default": "visible"
        }
    }
    required_parameters = ["selector"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        selector = kwargs.get("selector")
        if not selector or not isinstance(selector, str):
            return False, "selector must be a string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        selector = kwargs["selector"]
        timeout = kwargs.get("timeout", 15000)
        state = kwargs.get("state", "visible")
        
        try:
            engine = get_automation_engine()
            page = engine.get_page()
            
            if not page:
                return ToolResult.fail(error="No page loaded")
            
            page.wait_for_selector(selector, state=state, timeout=timeout)
            logger.info(f"Waited for {selector} (state={state})")
            return ToolResult.ok(f"Element {selector} is now {state}")
            
        except Exception as e:
            logger.error(f"Wait failed: {e}")
            return ToolResult.fail(error=f"Wait failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 5.0
    
    def risk_level(self) -> str:
        return "low"


class ScreenshotTool(BaseTool):
    """Capture screenshot of current page or specific element."""
    
    name = "take_screenshot"
    description = "Take a screenshot of the current page or a specific element. Saved to jarvis_data/screenshots/"
    parameters = {
        "filename": {
            "type": "string",
            "description": "Filename (without extension). Default: auto-generated timestamp",
            "default": None
        },
        "selector": {
            "type": "string",
            "description": "Optional CSS selector to screenshot specific element",
            "default": None
        },
        "full_page": {
            "type": "boolean",
            "description": "Capture full scrollable page",
            "default": False
        }
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        filename = kwargs.get("filename")
        selector = kwargs.get("selector")
        full_page = kwargs.get("full_page", False)
        
        try:
            import time
            from pathlib import Path
            
            engine = get_automation_engine()
            page = engine.get_page()
            
            if not page:
                return ToolResult.fail(error="No page loaded")
            
            # Ensure output directory exists
            output_dir = Path("jarvis_data/screenshots")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename
            if not filename:
                filename = f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}"
            
            filepath = output_dir / f"{filename}.png"
            
            # Take screenshot
            if selector:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=5000)
                locator.screenshot(path=str(filepath))
            else:
                page.screenshot(path=str(filepath), full_page=full_page)
            
            logger.info(f"Screenshot saved: {filepath}")
            return ToolResult.ok(f"Screenshot saved: {filepath}")
            
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ToolResult.fail(error=f"Screenshot failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.5
    
    def risk_level(self) -> str:
        return "low"


class SearchAndNavigateTool(BaseTool):
    """
    Composite tool: Search web for a site, navigate to it, and optionally search within.
    This reduces multi-step web navigation to a single atomic operation.
    """
    
    name = "search_and_navigate"
    description = "Search for a website, navigate to it, and optionally perform an internal search. Combines search_web + navigate_to_url + fill_input + click into one tool."
    parameters = {
        "site_query": {
            "type": "string",
            "description": "Query to find the website (e.g., 'kilimall', 'amazon')"
        },
        "internal_search": {
            "type": "string",
            "description": "Optional: search term to use after navigating to the site (e.g., 'refurbished phones')",
            "default": None
        },
        "search_selector": {
            "type": "string",
            "description": "CSS selector for the search input field on the target site (default: common selectors)",
            "default": None
        },
        "submit_selector": {
            "type": "string",
            "description": "CSS selector for the search submit button (default: common selectors)",
            "default": None
        }
    }
    required_parameters = ["site_query"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        site_query = kwargs.get("site_query")
        if not site_query or not isinstance(site_query, str):
            return False, "site_query must be a non-empty string"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        site_query = kwargs["site_query"]
        internal_search = kwargs.get("internal_search")
        search_selector = kwargs.get("search_selector")
        submit_selector = kwargs.get("submit_selector")
        
        try:
            from jarvis.tools.registry import ToolRegistry
            
            # Step 1: Search for the site
            logger.info(f"Searching for site: {site_query}")
            registry = ToolRegistry.get_instance()
            
            # Use search_web to find the site
            search_result = registry.execute("search_web", query=site_query)
            if not search_result.success:
                return ToolResult.fail(error=f"Failed to search for site: {search_result.error}")
            
            # Extract URL from search result (assuming first result is the target)
            search_output = search_result.output if hasattr(search_result, 'output') else str(search_result)
            
            # Simple URL extraction - look for http(s) URLs in the response
            import re
            url_match = re.search(r'https?://[^\s\)]+', search_output)
            if not url_match:
                return ToolResult.fail(error=f"No URL found in search results: {search_output[:200]}")
            
            target_url = url_match.group(0)
            logger.info(f"Found URL: {target_url}")
            
            # Step 2: Navigate to the site
            nav_result = registry.execute("navigate_to_url", url=target_url)
            if not nav_result.success:
                return ToolResult.fail(error=f"Failed to navigate: {nav_result.error}")
            
            # Step 3: If internal search requested, perform it
            if internal_search:
                logger.info(f"Performing internal search for: {internal_search}")
                
                # Common search selectors
                search_selectors = search_selector.split(',') if search_selector else [
                    'input[name="q"]', 'input[name="search"]', 'input[type="search"]',
                    '.search-input', '#search', 'input[placeholder*="search" i]'
                ]
                
                submit_selectors = submit_selector.split(',') if submit_selector else [
                    'button[type="submit"]', 'input[type="submit"]', '.search-btn',
                    'button.search', '[aria-label*="search" i]'
                ]
                
                # Try to fill search field
                filled = False
                for sel in search_selectors:
                    try:
                        fill_result = registry.execute("fill_input", selector=sel, value=internal_search)
                        if fill_result.success:
                            filled = True
                            logger.info(f"Filled search field with selector: {sel}")
                            break
                    except Exception:
                        continue
                
                if not filled:
                    return ToolResult.fail(error="Could not find search input field on page")
                
                # Submit search
                submitted = False
                for sel in submit_selectors:
                    try:
                        click_result = registry.execute("click_element", selector=sel)
                        if click_result.success:
                            submitted = True
                            logger.info(f"Submitted search with selector: {sel}")
                            break
                    except Exception:
                        continue
                
                if not submitted:
                    # Try pressing Enter as fallback
                    try:
                        from playwright.sync_api import sync_playwright
                        engine = get_automation_engine()
                        page = engine.get_page()
                        if page:
                            page.keyboard.press("Enter")
                            submitted = True
                            logger.info("Submitted search by pressing Enter")
                    except Exception as e:
                        logger.warning(f"Failed to press Enter: {e}")
                
                if submitted:
                    import time
                    time.sleep(2)  # Wait for search results
                    
                    # Get page summary
                    engine = get_automation_engine()
                    summary = engine.get_page_content_summary(max_length=500)
                    return ToolResult.ok({
                        "url": target_url,
                        "search_performed": internal_search,
                        "page_summary": summary
                    })
            
            # No internal search - just return navigation success
            engine = get_automation_engine()
            summary = engine.get_page_content_summary(max_length=500)
            return ToolResult.ok({
                "url": target_url,
                "page_summary": summary
            })
            
        except Exception as e:
            logger.error(f"Search and navigate failed: {e}")
            return ToolResult.fail(error=f"Search and navigate failed: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        internal = kwargs.get("internal_search")
        return 8.0 if internal else 5.0
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
WEB_AUTOMATION_TOOLS = [
    NavigateToUrlTool,
    ClickElementTool,
    FillInputTool,
    ExtractContentTool,
    WaitForElementTool,
    ScreenshotTool,
    SearchAndNavigateTool,
]
