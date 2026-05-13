"""Fetch and extract text content from a URL."""

import logging
import re

logger = logging.getLogger(__name__)

_TEXT_CAP = 8000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def fetch_url(url: str, extract_text: bool = True) -> dict:
    """Fetch a URL and return its text content. Strips HTML tags when extract_text=True."""
    try:
        import requests

        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": _USER_AGENT},
            allow_redirects=True,
        )

        html_text = resp.text
        status_code = resp.status_code
        content_length = len(resp.content)
        title = ""

        if extract_text:
            # ── Primary: BeautifulSoup ──────────────────────────────────────
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html_text, "html.parser")

                # Extract title
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                else:
                    h1_tag = soup.find("h1")
                    if h1_tag:
                        title = h1_tag.get_text(strip=True)

                # Remove noise tags
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator=" ", strip=True)

            except ImportError:
                # ── Fallback: regex tag stripping ──────────────────────────
                logger.debug("fetch_url: bs4 not available, using regex fallback")

                # Best-effort title via regex
                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL
                )
                if title_match:
                    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

                text = re.sub(r"<[^>]+>", " ", html_text)
                text = re.sub(r"\s+", " ", text).strip()
        else:
            text = html_text

        return {
            "success": True,
            "url": resp.url,
            "title": title,
            "text": text[:_TEXT_CAP],
            "status_code": status_code,
            "content_length": content_length,
        }

    except Exception as e:
        logger.error(f"fetch_url: {e}")
        return {"success": False, "error": str(e)}
