"""Web search tool using DuckDuckGo."""

import logging
import urllib.parse

logger = logging.getLogger(__name__)


def search_web(query: str, limit: int = 5) -> dict:
    """Search the web using DuckDuckGo. Returns list of results with title, url, snippet."""

    # ── Primary: duckduckgo_search package ──────────────────────────────────
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=limit):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")[:200],
                    }
                )
        return {
            "success": True,
            "results": results,
            "count": len(results),
            "query": query,
        }
    except ImportError:
        pass  # fall through to HTML scrape fallback
    except Exception as e:
        logger.warning(f"search_web DDGS error: {e}")
        # Don't give up yet — try the HTML fallback below

    # ── Fallback: scrape DuckDuckGo HTML endpoint ────────────────────────────
    try:
        import requests
        from bs4 import BeautifulSoup

        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        raw_results = soup.find_all("div", class_="result__body")

        results = []
        for item in raw_results[:limit]:
            a_tag = item.find("a", class_="result__a")
            snip = item.find("a", class_="result__snippet")
            title = a_tag.get_text(strip=True) if a_tag else ""
            href = a_tag.get("href", "") if a_tag else ""
            snippet = snip.get_text(strip=True) if snip else ""
            results.append(
                {
                    "title": title,
                    "url": href,
                    "snippet": snippet[:200],
                }
            )

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "query": query,
        }
    except ImportError:
        pass  # bs4 not installed — fall through to plain-requests attempt
    except Exception as e:
        logger.warning(f"search_web HTML fallback error: {e}")

    # ── Second fallback: requests only (no bs4) ──────────────────────────────
    try:
        import re

        import requests

        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        # Very rough regex extraction — good enough for a fallback
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', resp.text)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text)

        results = []
        for i, title in enumerate(titles[:limit]):
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            clean_snippet = re.sub(
                r"<[^>]+>", "", snippets[i] if i < len(snippets) else ""
            ).strip()
            results.append(
                {
                    "title": clean_title,
                    "url": "",
                    "snippet": clean_snippet[:200],
                }
            )

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "query": query,
        }
    except Exception as e:
        logger.error(f"search_web all fallbacks failed: {e}")

    return {
        "success": False,
        "error": (
            "duckduckgo_search not installed and HTML fallback failed. "
            "Run: pip install duckduckgo-search"
        ),
    }
