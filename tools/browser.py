"""Playwright-based browser automation tool."""

import base64
import logging

logger = logging.getLogger(__name__)

# ── Optional Playwright import ───────────────────────────────────────────────
try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    PlaywrightError = Exception  # type: ignore[misc,assignment]

# ── Module-level persistent browser state ───────────────────────────────────
_playwright = None
_browser = None
_page = None


def browser(
    action: str,
    url: str = None,
    selector: str = None,
    text: str = None,
    timeout: int = 30000,
) -> dict:
    """
    Control a web browser using Playwright.
    Actions: navigate, click, type, read_page, screenshot, scroll
    """
    global _playwright, _browser, _page

    if not _PLAYWRIGHT_AVAILABLE:
        return {
            "success": False,
            "error": (
                "playwright not installed. "
                "Run: pip install playwright && playwright install chromium"
            ),
        }

    try:
        # ── navigate (auto-launches if needed) ──────────────────────────────
        if action == "navigate":
            if not url:
                return {"success": False, "error": "URL required for navigate"}
            _ensure_alive(timeout)
            if _page is None:
                _do_launch(timeout)
            _page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return {
                "success": True,
                "url": _page.url,
                "title": _page.title(),
                "action": "navigate",
            }

        # ── actions that require an open page ────────────────────────────────
        elif action == "click":
            _require_page()
            _page.click(selector, timeout=timeout)
            return {"success": True, "action": "click", "selector": selector}

        elif action == "type":
            _require_page()
            if selector:
                _page.fill(selector, text or "")
            else:
                _page.keyboard.type(text or "")
            return {"success": True, "action": "type"}

        elif action == "read_page":
            _require_page()
            return {
                "success": True,
                "url": _page.url,
                "title": _page.title(),
                "text": _page.inner_text("body")[:5000],
                "action": "read_page",
            }

        elif action == "screenshot":
            _require_page()
            png_bytes = _page.screenshot()
            b64 = base64.b64encode(png_bytes).decode("utf-8")
            try:
                import io

                from PIL import Image

                img = Image.open(io.BytesIO(png_bytes))
                width, height = img.size
            except Exception:
                width, height = 0, 0
            return {
                "success": True,
                "image_b64": b64,
                "width": width,
                "height": height,
                "action": "screenshot",
            }

        elif action == "scroll":
            _require_page()
            if selector and "," in selector:
                parts = selector.split(",", 1)
                dx = int(parts[0].strip())
                dy = int(parts[1].strip())
                _page.evaluate(f"window.scrollBy({dx}, {dy})")
            else:
                _page.evaluate("window.scrollBy(0, 500)")
            return {"success": True, "action": "scroll"}

        else:
            return {"success": False, "error": f"Unknown browser action: '{action}'"}

    except _NoBrowserError as e:
        return {"success": False, "error": str(e)}
    except PlaywrightError as e:
        logger.error(f"browser({action}): Playwright error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"browser({action}): {e}")
        return {"success": False, "error": str(e)}


# ── Internal helpers ─────────────────────────────────────────────────────────


class _NoBrowserError(RuntimeError):
    pass


def _require_page():
    _ensure_alive()
    if _page is None or _browser is None:
        raise _NoBrowserError(
            "Browser not launched. Use action='launch' first or action='navigate' to auto-launch."
        )


def _ensure_alive():
    """Re-launch if browser or page is dead. Call before every action."""
    global _playwright, _browser, _page
    if _browser is not None:
        try:
            if _browser.is_connected():
                if _page is not None:
                    try:
                        _page.title()
                        return
                    except Exception:
                        logger.warning("browser: page is dead — creating new page")
                        _page = _browser.new_page()
                        return
                _page = _browser.new_page()
                return
        except Exception:
            logger.warning("browser: existing session is dead — relaunching")
            _do_close()
    _do_launch(30000)


def _do_launch(timeout: int = 30000):
    global _playwright, _browser, _page
    if _browser is not None:
        if _browser.is_connected():
            return  # alive — reuse existing session
        logger.warning("browser: existing session is dead — relaunching")
        _do_close()  # clean up stale globals before fresh launch
    _playwright = sync_playwright().__enter__()
    # Use system Chrome instead of bundled Chromium
    # channel="chrome" launches the user's installed Chrome browser
    _browser = _playwright.chromium.launch(headless=False, channel="chrome")
    _page = _browser.new_page()
    _page.set_default_timeout(timeout)


def _do_close():
    global _playwright, _browser, _page
    try:
        if _browser is not None:
            _browser.close()
    except Exception:
        pass
    try:
        if _playwright is not None:
            _playwright.__exit__(None, None, None)
    except Exception:
        pass
    _browser = None
    _page = None
    _playwright = None
