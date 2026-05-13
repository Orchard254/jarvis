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
    wait_for: str = None,
) -> dict:
    """
    Control a web browser using Playwright.
    Actions: launch, navigate, click, type, read_page, screenshot,
             close, close_tab, get_tabs, switch_tab, new_tab, back,
             forward, get_url, scroll, wait_for
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
        # ── launch ──────────────────────────────────────────────────────────
        if action == "launch":
            _do_launch(timeout)
            return {"success": True, "action": "launch"}

        # ── navigate (auto-launches if needed) ──────────────────────────────
        elif action == "navigate":
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

        elif action == "new_tab":
            _require_page()
            new_page = _browser.contexts[0].new_page()
            _page = new_page
            if url:
                _page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return {"success": True, "action": "new_tab", "url": _page.url}

        elif action == "get_tabs":
            _require_page()
            pages = _browser.contexts[0].pages if _browser.contexts else []
            tabs = [{"title": p.title(), "url": p.url, "index": i} for i, p in enumerate(pages)]
            return {"success": True, "action": "get_tabs", "tabs": tabs}

        elif action == "switch_tab":
            _require_page()
            if selector is None:
                return {"success": False, "error": "switch_tab requires selector (tab index)"}
            try:
                tab_index = int(selector)
                pages = _browser.contexts[0].pages if _browser.contexts else []
                if 0 <= tab_index < len(pages):
                    pages[tab_index].bring_to_front()
                    _page = pages[tab_index]
                    return {"success": True, "action": "switch_tab", "tab_index": tab_index}
                else:
                    return {"success": False, "error": f"Invalid tab index: {tab_index}"}
            except ValueError:
                return {"success": False, "error": f"Invalid tab index format: '{selector}'"}

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
            # Infer dimensions via PIL if available, otherwise omit
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

        elif action == "close":
            _do_close()
            return {"success": True, "action": "close"}

        elif action == "close_tab":
            _require_page()
            _page.keyboard.press("Control+w")
            return {"success": True, "action": "close_tab"}

        elif action == "back":
            _require_page()
            _page.go_back()
            return {"success": True, "url": _page.url, "action": "back"}

        elif action == "forward":
            _require_page()
            _page.go_forward()
            return {"success": True, "url": _page.url, "action": "forward"}

        elif action == "get_url":
            _require_page()
            return {
                "success": True,
                "url": _page.url,
                "title": _page.title(),
                "action": "get_url",
            }

        elif action == "scroll":
            _require_page()
            if selector and "," in selector:
                # Interpret selector as "x,y" delta
                parts = selector.split(",", 1)
                dx = int(parts[0].strip())
                dy = int(parts[1].strip())
                _page.evaluate(f"window.scrollBy({dx}, {dy})")
            else:
                _page.evaluate("window.scrollBy(0, 500)")
            return {"success": True, "action": "scroll"}

        elif action == "wait_for":
            _require_page()
            _page.wait_for_selector(selector, timeout=timeout)
            return {"success": True, "action": "wait_for", "selector": selector}

        elif action == "refresh":
            _require_page()
            _page.reload()
            return {
                "success": True,
                "url": _page.url,
                "title": _page.title(),
                "action": "refresh",
            }

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
