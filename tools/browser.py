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


# ── Multi-browser support ────────────────────────────────────────────────────
# Browser executable paths on Windows (checked in order for "auto" preference)
_BROWSER_PATHS = {
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "opera": [
        r"C:\Users\{user}\AppData\Local\Programs\Opera\opera.exe",
        r"C:\Program Files\Opera\opera.exe",
        r"C:\Program Files (x86)\Opera\opera.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
}

# Browsers that support Chromium CDP (Playwright connect_over_cdp)
_CHROMIUM_BROWSERS = {"brave", "opera", "chrome"}

# Order for "auto" preference
_AUTO_ORDER = ["brave", "opera", "firefox", "chrome"]


def _find_browser_exe(browser_name: str) -> str | None:
    """Find the executable path for a browser on the system."""
    import os
    paths = _BROWSER_PATHS.get(browser_name, [])
    username = os.environ.get("USERNAME", os.environ.get("USER", ""))
    for path in paths:
        resolved = path.replace("{user}", username)
        if os.path.isfile(resolved):
            return resolved
    # Try shutil.which as fallback (works if browser is on PATH)
    import shutil
    exe_names = {
        "brave": ["brave", "brave-browser"],
        "opera": ["opera"],
        "firefox": ["firefox"],
        "chrome": ["chrome", "google-chrome", "google-chrome-stable"],
    }
    for name in exe_names.get(browser_name, [browser_name]):
        found = shutil.which(name)
        if found:
            return found
    return None


def _try_connect_cdp(port: int = None) -> bool:
    """Try connecting to a running browser via CDP.

    Works with any Chromium-based browser (Chrome, Brave, Opera, Edge)
    started with --remote-debugging-port=<port>.
    """
    global _playwright, _browser, _page
    if port is None:
        from settings import BROWSER_CDP_PORT
        port = BROWSER_CDP_PORT

    try:
        import requests as _req
        resp = _req.get(f"http://localhost:{port}/json/version", timeout=2)
        if resp.status_code != 200:
            return False

        if _playwright is None:
            _playwright = sync_playwright().__enter__()

        _browser = _playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
        contexts = _browser.contexts
        if contexts and contexts[0].pages:
            _page = contexts[0].pages[0]
        else:
            ctx = _browser.new_context() if not contexts else contexts[0]
            _page = ctx.new_page()

        browser_info = resp.json().get("Browser", "unknown")
        logger.info(f"browser: connected via CDP port {port} ({browser_info})")
        return True
    except Exception as e:
        logger.debug(f"CDP connection on port {port} failed: {e}")
        return False


def _launch_firefox(timeout: int = 30000) -> bool:
    """Launch Firefox with Playwright (uses its own protocol, not CDP)."""
    global _playwright, _browser, _page
    try:
        if _playwright is None:
            _playwright = sync_playwright().__enter__()
        _browser = _playwright.firefox.launch(headless=False)
        _page = _browser.new_page()
        _page.set_default_timeout(timeout)
        logger.info("browser: launched Firefox via Playwright")
        return True
    except Exception as e:
        logger.debug(f"Firefox launch failed: {e}")
        return False


def _launch_chromium_browser(browser_name: str, timeout: int = 30000) -> bool:
    """Launch a Chromium-based browser (Brave, Opera, Chrome) via Playwright."""
    global _playwright, _browser, _page

    # Playwright channel mapping
    channel_map = {
        "chrome": "chrome",
        "brave": None,  # no built-in channel — use executable_path
        "opera": None,
    }

    try:
        if _playwright is None:
            _playwright = sync_playwright().__enter__()

        channel = channel_map.get(browser_name)
        if channel:
            _browser = _playwright.chromium.launch(headless=False, channel=channel)
        else:
            exe = _find_browser_exe(browser_name)
            if not exe:
                return False
            _browser = _playwright.chromium.launch(
                headless=False, executable_path=exe,
            )
        _page = _browser.new_page()
        _page.set_default_timeout(timeout)
        logger.info(f"browser: launched {browser_name}")
        return True
    except Exception as e:
        logger.debug(f"{browser_name} launch failed: {e}")
        return False


def _do_launch(timeout: int = 30000):
    global _playwright, _browser, _page
    if _browser is not None:
        if _browser.is_connected():
            return  # alive — reuse existing session
        logger.warning("browser: existing session is dead — relaunching")
        _do_close()  # clean up stale globals before fresh launch

    from settings import BROWSER_PREFERRED

    # 1. Try CDP first (connects to user's existing browser)
    if _try_connect_cdp():
        if _page:
            _page.set_default_timeout(timeout)
        return

    # 2. Launch preferred or auto-detected browser
    pref = BROWSER_PREFERRED.lower().strip()
    if pref == "auto":
        order = _AUTO_ORDER
    else:
        # Put preferred first, then fall through others
        order = [pref] + [b for b in _AUTO_ORDER if b != pref]

    for name in order:
        if name == "firefox":
            if _launch_firefox(timeout):
                return
        elif _launch_chromium_browser(name, timeout):
            return

    # 3. Last resort: bundled Chromium
    if _playwright is None:
        _playwright = sync_playwright().__enter__()
    _browser = _playwright.chromium.launch(headless=False)
    _page = _browser.new_page()
    _page.set_default_timeout(timeout)
    logger.info("browser: launched bundled Chromium (no system browser found)")


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
