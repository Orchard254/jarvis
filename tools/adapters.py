"""
Tool adapters — maps clean schema tool names to Python implementations.
Each function accepts **kwargs (unpacked by safety executor), returns dict.
"""
import datetime
import os
import re
import subprocess
import glob as glob_mod
import shutil
import webbrowser
from pathlib import Path

from tools.system.execute_code import execute_code as _run_code

# DPI awareness for coordinate accuracy on Windows
_SCREEN_SCALE = 1.0
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        _SCREEN_SCALE = dpi / 96.0
    except Exception:
        pass


def open_app(**kwargs) -> dict:
    name = kwargs.get("name", "")
    # Try 1: os.startfile (works for PATH-resolvable names like 'notepad', 'calc')
    try:
        os.startfile(name) if os.name == "nt" else subprocess.Popen([name])
        return {"success": True, "status": f"launched {name}", "name": name}
    except Exception:
        pass
    # Try 2: shutil.which (finds system PATH executables)
    try:
        which_path = shutil.which(name) or shutil.which(f"{name}.exe")
        if which_path:
            os.startfile(which_path) if os.name == "nt" else subprocess.Popen([which_path])
            return {"success": True, "status": f"launched {name}", "name": name, "path": which_path}
    except Exception:
        pass
    # Try 3: search installed apps via PC index DB
    try:
        db_path = Path(__file__).parent.parent / "indexer" / "db" / "pc_index.db"
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            try:
                cur = conn.execute("SELECT name, exe_path FROM apps WHERE name LIKE ?", (f"%{name}%",))
                rows = cur.fetchall()
            finally:
                conn.close()
            for row_name, exe_path in rows:
                resolved = _resolve_exe(exe_path, row_name)
                if resolved:
                    try:
                        os.startfile(resolved) if os.name == "nt" else subprocess.Popen([resolved])
                        return {"success": True, "status": f"launched {name}", "name": name, "path": resolved}
                    except Exception:
                        pass
    except Exception:
        pass
    return {"success": False, "error": f"could not find '{name}' in PATH or app index. try list_installed_apps first."}


def _resolve_exe(exe_path: str | None, app_name: str) -> str | None:
    """Resolve a DB path to an executable. Returns best-effort path or None."""
    if exe_path:
        cleaned = exe_path.strip().strip('"')
        if cleaned:
            p = Path(cleaned)
            if p.suffix.lower() in (".exe", ".lnk"):
                return str(p)
            if p.is_dir():
                exe_candidate = p / f"{app_name}.exe"
                if exe_candidate.exists():
                    return str(exe_candidate)
                try:
                    for f in p.iterdir():
                        if f.suffix.lower() == ".exe":
                            return str(f)
                except PermissionError:
                    pass

    which = shutil.which(app_name)
    if which:
        return which
    which_alt = shutil.which(f"{app_name}.exe")
    if which_alt:
        return which_alt
    if app_name.endswith(".exe"):
        which_alt = shutil.which(app_name[:-4])
        if which_alt:
            return which_alt

    return exe_path if exe_path else None


def close_app(**kwargs) -> dict:
    name = kwargs.get("name", "")
    force = kwargs.get("force", False)
    if not re.match(r"^[a-zA-Z0-9._\-, ]+$", name):
        return {"success": False, "error": f"Invalid process name: {name!r}"}
    try:
        args = ["taskkill", "/IM", f"{name}.exe"]
        if force:
            args.append("/F")
        subprocess.run(args, capture_output=True, timeout=5)
        return {"success": True, "status": f"closed {name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_active_window(**kwargs) -> dict:
    try:
        import pygetwindow as gw
        win = gw.getActiveWindow()
        if win:
            return {"success": True, "title": win.title, "process": "unknown"}
        return {"success": True, "title": "", "process": ""}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_window_bounds(**kwargs) -> dict:
    """Get the position and size of a window by title."""
    title = kwargs.get("title", "")
    try:
        import pygetwindow as gw
        for w in gw.getWindowsWithTitle(title):
            return {
                "success": True,
                "title": w.title,
                "left": w.left,
                "top": w.top,
                "width": w.width,
                "height": w.height,
                "right": w.right,
                "bottom": w.bottom,
            }
        return {"success": False, "error": "window not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def focus_window(**kwargs) -> dict:
    title = kwargs.get("title", "")
    process = kwargs.get("process", "") or kwargs.get("process_name", "")
    try:
        import pygetwindow as gw
        target = None
        if title:
            for w in gw.getWindowsWithTitle(title):
                target = w; break
        if not target and title and not process:
            if " - " in title:
                app_hint = title.rsplit(" - ", 1)[-1].strip()
                if app_hint:
                    for w in gw.getAllWindows():
                        if w.title.lower().endswith(f" - {app_hint.lower()}"):
                            target = w; break
                    if not target:
                        for w in gw.getAllWindows():
                            if app_hint.lower() in w.title.lower():
                                target = w; break
        if not target and process:
            for w in gw.getAllWindows():
                if process.lower() in w.title.lower():
                    target = w; break
        if target:
            if target.isMinimized:
                target.restore()
            target.activate()
            # Win32 fallback for reliable foreground switching
            try:
                import ctypes
                hwnd = target._hWnd
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            return {
                "success": True,
                "status": f"focused {target.title}",
                "title": target.title,
                "left": target.left,
                "top": target.top,
                "width": target.width,
                "height": target.height,
            }
        return {"success": False, "error": "window not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_running_apps(**kwargs) -> dict:
    try:
        import pygetwindow as gw
        windows = []
        for w in gw.getAllWindows():
            if w.title.strip():
                windows.append({"title": w.title, "visible": w.visible})
        return {"success": True, "windows": windows[:50]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_system_stats(**kwargs) -> dict:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/" if os.name != "nt" else "C:\\")
        battery = psutil.sensors_battery()
        return {
            "success": True,
            "cpu_percent": cpu,
            "ram_percent": ram.percent,
            "ram_free_gb": round(ram.available / 1e9, 1),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / 1e9, 1),
            "battery_percent": round(battery.percent, 1) if battery else None,
            "battery_plugged": battery.power_plugged if battery else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def screenshot(**kwargs) -> dict:
    try:
        import pyautogui
        region = kwargs.get("region")
        if region:
            img = pyautogui.screenshot(region=(region["left"], region["top"], region["width"], region["height"]))
        else:
            img = pyautogui.screenshot()
        import io, base64
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"success": True, "image_b64": b64, "width": img.width, "height": img.height}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_screen(**kwargs) -> dict:
    try:
        import pyautogui
        import pytesseract
        from PIL import Image
        region = kwargs.get("region")
        if region:
            img = pyautogui.screenshot(region=(region["left"], region["top"], region["width"], region["height"]))
        else:
            img = pyautogui.screenshot()
        text = pytesseract.image_to_string(img)
        return {"success": True, "text": text.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def click(**kwargs) -> dict:
    try:
        import pyautogui
        x, y = kwargs.get("x"), kwargs.get("y")
        button = kwargs.get("button", "left")
        failsafe_was = pyautogui.FAILSAFE
        pyautogui.FAILSAFE = False
        try:
            pyautogui.click(x, y, button=button)
        finally:
            pyautogui.FAILSAFE = failsafe_was
        return {"success": True, "status": f"clicked ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def type_text(**kwargs) -> dict:
    try:
        import pyautogui
        text = kwargs.get("text", "")
        interval = kwargs.get("interval", 0.02)
        pyautogui.write(text, interval=interval)
        if kwargs.get("enter"):
            pyautogui.press("enter")
        return {"success": True, "typed": len(text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def press_keys(**kwargs) -> dict:
    try:
        import pyautogui
        raw = kwargs.get("keys", "")
        keys = raw.lower().replace(" ", "").split("+")
        if len(keys) == 1 and len(keys[0]) == 1:
            pyautogui.write(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return {"success": True, "keys": raw}
    except Exception as e:
        return {"success": False, "error": str(e)}


def scroll(**kwargs) -> dict:
    try:
        import pyautogui
        clicks = kwargs.get("clicks", -3)
        pyautogui.scroll(clicks)
        return {"success": True, "clicks": clicks}
    except Exception as e:
        return {"success": False, "error": str(e)}


def wait(**kwargs) -> dict:
    import time
    ms = kwargs.get("ms", 1000)
    condition = kwargs.get("condition", "")
    target = kwargs.get("target", "")
    timeout_ms = kwargs.get("timeout_ms", ms * 2)

    if condition and target:
        deadline = time.time() + (timeout_ms / 1000.0)
        poll_interval = 0.2
        started = time.time()
        while time.time() < deadline:
            if _check_wait_condition(condition, target):
                elapsed = int((time.time() - started) * 1000)
                return {
                    "success": True,
                    "message": f"condition met: {condition} '{target}'",
                    "data": {"condition": condition, "target": target, "duration_ms": elapsed},
                }
            time.sleep(poll_interval)
        elapsed = int((time.time() - started) * 1000)
        return {
            "success": False,
            "message": f"Timeout waiting for {condition} '{target}' after {timeout_ms}ms",
            "data": {"condition": condition, "target": target, "timeout_ms": timeout_ms, "duration_ms": elapsed},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    time.sleep(ms / 1000.0)
    return {
        "success": True,
        "message": f"waited {ms}ms",
        "data": {"duration_ms": ms},
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def _check_wait_condition(condition: str, target: str) -> bool:
    """
    Check a named wait condition.

    Supported conditions:
      process_running  — target is a process name substring
      process_gone     — target is a process name substring
      cpu_idle         — target is a numeric threshold (e.g. "20" means CPU < 20%)
      window_visible   — target is a window title substring (checked via pygetwindow)
      window_exists    — alias for window_visible
      text_visible     — target is a text string; OCR-checks the screen for its presence
    """
    import psutil
    target_lower = target.lower()

    if condition == "process_running":
        return any(target_lower in (p.info.get("name") or "").lower()
                   for p in psutil.process_iter(["name"]))

    if condition == "process_gone":
        return not any(target_lower in (p.info.get("name") or "").lower()
                       for p in psutil.process_iter(["name"]))

    if condition == "cpu_idle":
        # FIX: target must be parsed as a float, not compared as a string
        try:
            threshold = float(target)
        except (ValueError, TypeError):
            threshold = 20.0
        return psutil.cpu_percent(interval=0.2) < threshold

    if condition in ("window_visible", "window_exists"):
        try:
            import pygetwindow as gw
            return any(
                target_lower in w.title.lower()
                for w in gw.getAllWindows()
                if w.title.strip()
            )
        except Exception:
            return False

    if condition == "text_visible":
        # FIX: Use OCR to actually check screen text, not window titles
        try:
            import pyautogui
            import pytesseract
            img = pyautogui.screenshot()
            screen_text = pytesseract.image_to_string(img).lower()
            return target_lower in screen_text
        except Exception:
            return False

    return False


def search_files(**kwargs) -> dict:
    try:
        pattern = kwargs.get("pattern", "")
        location = kwargs.get("location", str(Path.home() / "Desktop"))
        location_resolved = Path(location).resolve()
        home = Path.home().resolve()
        if not str(location_resolved).startswith(str(home)):
            return {"success": False, "error": f"Location must be under user home directory: {home}"}
        max_results = kwargs.get("max_results", 20)
        matches = []
        search_path = location_resolved / "**" / pattern
        for f in glob_mod.glob(str(search_path), recursive=True)[:max_results]:
            p = Path(f)
            try:
                size = p.stat().st_size if p.is_file() else 0
            except OSError:
                size = 0
            matches.append({"name": p.name, "path": str(p), "size": size})
        return {"success": True, "results": matches, "count": len(matches)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        os.startfile(path)
        return {"success": True, "status": f"opened {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        max_chars = kwargs.get("max_chars", 5000)
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        total_size = os.path.getsize(path)
        return {
            "success": True,
            "content": content,
            "truncated": len(content) >= max_chars,
            "total_bytes": total_size,
            "chars_read": len(content),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "status": f"wrote {len(content)} chars to {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        if os.path.isdir(path):
            try:
                os.rmdir(path)
            except OSError:
                return {"success": False, "error": f"Directory not empty: {path}. Use execute_code with caution for recursive deletes."}
        else:
            os.remove(path)
        return {"success": True, "status": f"deleted {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_file(**kwargs) -> dict:
    try:
        src = kwargs.get("source", "")
        dst = kwargs.get("destination", "")
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.move(src, dst)
        return {"success": True, "status": f"moved {src} to {dst}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_python(**kwargs) -> dict:
    return _run_code(
        code=kwargs.get("code", ""),
        language="python",
        timeout=kwargs.get("timeout", 30),
    )


def execute_code(**kwargs) -> dict:
    return _run_code(
        code=kwargs.get("code", ""),
        language=kwargs.get("language", "python"),
        background=kwargs.get("background", False),
        action=kwargs.get("action", "run"),
        pid=kwargs.get("pid", 0),
        timeout=kwargs.get("timeout", 60),
    )


# ---------------------------------------------------------------------------
# web_search — multi-tier fallback chain
#
# Tier 1: DuckDuckGo HTML scraping (no API key, works out of the box)
# Tier 2: Brave Search API  (requires BRAVE_API_KEY in .env)
# Tier 3: Google Custom Search (requires GOOGLE_API_KEY + GOOGLE_CX in .env)
#
# Each tier returns a list of {"title", "url", "snippet"} dicts.
# ---------------------------------------------------------------------------

def _ddg_search(query: str, n: int) -> list[dict]:
    """Scrape DuckDuckGo HTML results. No API key required."""
    import urllib.request
    import urllib.parse
    import html

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    q = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={q}"
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=12)
    body = resp.read().decode("utf-8", errors="replace")

    results = []
    # Extract result blocks: <a class="result__a" href="...">title</a>
    # and snippet: <a class="result__snippet">...</a>
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    links = link_pattern.findall(body)
    snippets = [m.group(1) for m in snippet_pattern.finditer(body)]

    for i, (href, title) in enumerate(links[:n]):
        # DDG may wrap real URL in a redirect — extract uddg param if present
        real_url = href
        uddg_match = re.search(r"uddg=([^&]+)", href)
        if uddg_match:
            real_url = urllib.parse.unquote(uddg_match.group(1))

        clean_title = re.sub(r"<[^>]+>", "", title).strip()
        clean_title = html.unescape(clean_title)
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            snippet = html.unescape(snippet)

        if real_url and clean_title:
            results.append({"title": clean_title, "url": real_url, "snippet": snippet})

    return results


def _brave_search(query: str, n: int, api_key: str) -> list[dict]:
    """Brave Search API — requires BRAVE_API_KEY."""
    import urllib.request
    import urllib.parse
    import json

    q = urllib.parse.quote_plus(query)
    url = f"https://api.search.brave.com/res/v1/web/search?q={q}&count={n}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    })
    resp = urllib.request.urlopen(req, timeout=12)
    data = json.loads(resp.read())
    results = []
    for item in data.get("web", {}).get("results", [])[:n]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })
    return results


def _google_search(query: str, n: int, api_key: str, cx: str) -> list[dict]:
    """Google Custom Search API — requires GOOGLE_API_KEY + GOOGLE_CX."""
    import urllib.request
    import urllib.parse
    import json

    params = urllib.parse.urlencode({"key": api_key, "cx": cx, "q": query, "num": min(n, 10)})
    url = f"https://www.googleapis.com/customsearch/v1?{params}"
    resp = urllib.request.urlopen(url, timeout=12)
    data = json.loads(resp.read())
    results = []
    for item in data.get("items", [])[:n]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })
    return results


def web_search(**kwargs) -> dict:
    """
    Search the web using the best available backend.

    Priority:
      1. Brave Search API  (BRAVE_API_KEY in env)
      2. Google Custom Search (GOOGLE_API_KEY + GOOGLE_CX in env)
      3. DuckDuckGo HTML scraping (always available, no key needed)
    """
    query = kwargs.get("query", "")
    n = int(kwargs.get("max_results", 5))

    if not query:
        return {"success": False, "error": "query is required"}

    errors = []

    # Tier 1 — Brave
    brave_key = os.environ.get("BRAVE_API_KEY", "")
    if brave_key:
        try:
            results = _brave_search(query, n, brave_key)
            if results:
                return {"success": True, "results": results, "count": len(results), "source": "brave"}
        except Exception as e:
            errors.append(f"brave: {e}")

    # Tier 2 — Google
    google_key = os.environ.get("GOOGLE_API_KEY", "")
    google_cx = os.environ.get("GOOGLE_CX", "")
    if google_key and google_cx:
        try:
            results = _google_search(query, n, google_key, google_cx)
            if results:
                return {"success": True, "results": results, "count": len(results), "source": "google"}
        except Exception as e:
            errors.append(f"google: {e}")

    # Tier 3 — DuckDuckGo HTML (always attempted)
    try:
        results = _ddg_search(query, n)
        if results:
            return {"success": True, "results": results, "count": len(results), "source": "duckduckgo"}
        return {
            "success": False,
            "error": "No results returned from DuckDuckGo",
            "prior_errors": errors,
        }
    except Exception as e:
        errors.append(f"duckduckgo: {e}")
        return {
            "success": False,
            "error": f"All search backends failed: {'; '.join(errors)}",
        }


def open_url(**kwargs) -> dict:
    try:
        url = kwargs.get("url", "")
        webbrowser.open(url)
        return {"success": True, "status": f"opened {url}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fetch_page(**kwargs) -> dict:
    """
    Fetch a webpage and return clean text content.

    Improvements over the old template-based version:
    - Proper User-Agent so sites don't block us
    - Strips script/style tags before extracting text
    - Returns structured metadata (url, title, char_count)
    - Respects max_chars without cutting mid-word
    """
    import urllib.request
    import urllib.error
    import html as html_lib
    import re as _re

    url = kwargs.get("url", "")
    max_chars = int(kwargs.get("max_chars", 12000))

    if not url:
        return {"success": False, "error": "url is required"}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}", "url": url}
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}

    # Extract title
    title_match = _re.search(r"<title[^>]*>(.*?)</title>", raw, _re.IGNORECASE | _re.DOTALL)
    title = html_lib.unescape(title_match.group(1).strip()) if title_match else ""

    # Remove script, style, nav, footer, header blocks — noise for LLM
    cleaned = _re.sub(r"<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>", "", raw,
                      flags=_re.DOTALL | _re.IGNORECASE)

    # Strip remaining HTML tags
    text = _re.sub(r"<[^>]+>", " ", cleaned)

    # Collapse whitespace
    text = _re.sub(r"[ \t]+", " ", text)
    text = _re.sub(r"\n{3,}", "\n\n", text)
    text = html_lib.unescape(text).strip()

    truncated = len(text) > max_chars
    if truncated:
        # Cut at last word boundary
        cut = text[:max_chars]
        last_space = cut.rfind(" ")
        text = cut[:last_space] if last_space > 0 else cut

    return {
        "success": True,
        "url": url,
        "title": title,
        "content": text,
        "char_count": len(text),
        "truncated": truncated,
    }


def detect_ui_elements(**kwargs) -> dict:
    """
    Detect UI elements on screen using pytesseract image_to_data.

    Returns structured elements with bounding boxes and center coordinates,
    so the LLM can call click(x=elem['center_x'], y=elem['center_y']) directly.

    element_type filter:
      'all'    — return everything with confidence >= min_confidence
      'button' — heuristic: short text (1-4 words), ALL CAPS, or surrounded by whitespace
      'text'   — any detected text
      'input'  — not reliably detectable via OCR; use vision_query instead
    """
    try:
        import pyautogui
        import pytesseract
        from PIL import Image

        region = kwargs.get("region")
        element_type = kwargs.get("element_type", "all")
        search_text = (kwargs.get("text") or "").lower().strip()
        min_confidence = float(kwargs.get("min_confidence", 50))

        # Capture screen (or region)
        offset_x, offset_y = 0, 0
        if region:
            img = pyautogui.screenshot(
                region=(region["left"], region["top"], region["width"], region["height"])
            )
            offset_x = region["left"]
            offset_y = region["top"]
        else:
            img = pyautogui.screenshot()

        # Use image_to_data for bounding boxes
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        elements = []
        n_boxes = len(data["text"])
        for i in range(n_boxes):
            word = (data["text"][i] or "").strip()
            conf = float(data["conf"][i])

            if not word or conf < min_confidence:
                continue

            x = data["left"][i] + offset_x
            y = data["top"][i] + offset_y
            w = data["width"][i]
            h = data["height"][i]
            center_x = int((x + w // 2) / _SCREEN_SCALE)
            center_y = int((y + h // 2) / _SCREEN_SCALE)

            elem = {
                "text": word,
                "confidence": round(conf, 1),
                "bbox": {"left": x, "top": y, "width": w, "height": h},
                "center_x": center_x,
                "center_y": center_y,
            }

            # Apply element_type filter
            if element_type == "button":
                # Heuristic: short, ALL CAPS or title-case, reasonably sized
                is_short = len(word.split()) <= 4
                is_caps = word.isupper() or word.istitle()
                if not (is_short and (is_caps or len(word) <= 10)):
                    continue
            elif element_type == "tab":
                # Heuristic: tab-like elements are near top of screen/region,
                # short text, small vertical extent (typically 20-40px tall)
                is_near_top = (y - offset_y) < 120
                is_short_text = len(word.split()) <= 8 and len(word) <= 60
                is_tab_height = h <= 80
                if not (is_near_top and is_short_text and is_tab_height):
                    continue
            elif element_type == "input":
                # OCR can't reliably detect input fields; pass everything through
                # and let the LLM figure it out from context
                pass

            # Apply text search filter
            if search_text and search_text not in word.lower():
                continue

            elements.append(elem)

        # Merge adjacent words into phrases (same line, close x positions)
        merged = _merge_adjacent_elements(elements)

        return {
            "success": True,
            "elements": merged,
            "count": len(merged),
            "note": (
                "Each element has center_x/center_y — pass directly to click(). "
                "For images or icons, use vision_query instead."
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _merge_adjacent_elements(elements: list[dict]) -> list[dict]:
    """
    Merge horizontally adjacent OCR words on the same line into phrases.
    This reduces 'OK Cancel Apply' (3 elements) into reasonable groups.
    """
    if not elements:
        return elements

    merged = []
    used = set()

    for i, elem in enumerate(elements):
        if i in used:
            continue
        group = [elem]
        used.add(i)

        for j, other in enumerate(elements):
            if j in used or j == i:
                continue
            # Same approximate line (top within ±8px) and close horizontally
            same_line = abs(other["bbox"]["top"] - elem["bbox"]["top"]) <= 8
            adjacent_x = (
                other["bbox"]["left"] <=
                elem["bbox"]["left"] + elem["bbox"]["width"] + 40
            )
            if same_line and adjacent_x:
                group.append(other)
                used.add(j)

        if len(group) == 1:
            merged.append(elem)
        else:
            # Build a merged phrase element
            all_text = " ".join(g["text"] for g in group)
            min_left = min(g["bbox"]["left"] for g in group)
            min_top = min(g["bbox"]["top"] for g in group)
            max_right = max(g["bbox"]["left"] + g["bbox"]["width"] for g in group)
            max_bottom = max(g["bbox"]["top"] + g["bbox"]["height"] for g in group)
            merged.append({
                "text": all_text,
                "confidence": round(sum(g["confidence"] for g in group) / len(group), 1),
                "bbox": {
                    "left": min_left,
                    "top": min_top,
                    "width": max_right - min_left,
                    "height": max_bottom - min_top,
                },
                "center_x": int((min_left + max_right) // 2 / _SCREEN_SCALE),
                "center_y": int((min_top + max_bottom) // 2 / _SCREEN_SCALE),
            })

    return merged


def store_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="store", key=kwargs.get("key"), value=kwargs.get("value"))


def retrieve_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="recall", key=kwargs.get("key"))


def forget_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="forget", key=kwargs.get("key"))


def search_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="search", query=kwargs.get("query"), limit=kwargs.get("limit", 10))


def send_message(**kwargs) -> dict:
    from tools.comm.send_message import send_message as _send
    return _send(
        to=kwargs.get("to", ""),
        subject=kwargs.get("subject", ""),
        body=kwargs.get("body", ""),
    )


def speak(**kwargs) -> dict:
    from tools.voice.speak import speak as _speak
    return _speak(text=kwargs.get("text", ""), blocking=True)


def minimize_window(**kwargs) -> dict:
    title = kwargs.get("title", "")
    process = kwargs.get("process", "") or kwargs.get("process_name", "")
    try:
        import pygetwindow as gw
        target = None
        if title:
            for w in gw.getWindowsWithTitle(title):
                target = w; break
        if not target and process:
            for w in gw.getAllWindows():
                if process.lower() in w.title.lower():
                    target = w; break
        if target:
            target.minimize()
            return {"success": True, "status": f"minimized {target.title}"}
        return {"success": False, "error": "window not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def maximize_window(**kwargs) -> dict:
    title = kwargs.get("title", "")
    process = kwargs.get("process", "") or kwargs.get("process_name", "")
    try:
        import pygetwindow as gw
        target = None
        if title:
            for w in gw.getWindowsWithTitle(title):
                target = w; break
        if not target and process:
            for w in gw.getAllWindows():
                if process.lower() in w.title.lower():
                    target = w; break
        if target:
            target.maximize()
            return {"success": True, "status": f"maximized {target.title}"}
        return {"success": False, "error": "window not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def double_click(**kwargs) -> dict:
    try:
        import pyautogui
        x, y = kwargs.get("x"), kwargs.get("y")
        pyautogui.doubleClick(x, y)
        return {"success": True, "status": f"double-clicked ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def right_click(**kwargs) -> dict:
    try:
        import pyautogui
        x, y = kwargs.get("x"), kwargs.get("y")
        pyautogui.rightClick(x, y)
        return {"success": True, "status": f"right-clicked ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_mouse(**kwargs) -> dict:
    try:
        import pyautogui
        x, y = kwargs.get("x"), kwargs.get("y")
        duration = kwargs.get("duration", 0.2)
        failsafe_was = pyautogui.FAILSAFE
        pyautogui.FAILSAFE = False
        try:
            pyautogui.moveTo(x, y, duration=duration)
        finally:
            pyautogui.FAILSAFE = failsafe_was
        return {"success": True, "status": f"moved to ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def drag(**kwargs) -> dict:
    try:
        import pyautogui
        sx, sy = kwargs.get("start_x"), kwargs.get("start_y")
        ex, ey = kwargs.get("end_x"), kwargs.get("end_y")
        duration = kwargs.get("duration", 0.3)
        pyautogui.moveTo(sx, sy)
        pyautogui.drag(ex - sx, ey - sy, duration=duration)
        return {"success": True, "status": f"dragged from ({sx},{sy}) to ({ex},{ey})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_volume(**kwargs) -> dict:
    level = kwargs.get("level", 0)
    try:
        from pycaw.pycaw import AudioUtilities
        devices = AudioUtilities.GetSpeakers()
        interface = devices.EndpointVolume
        interface.SetMasterVolumeLevelScalar(max(0, min(1, level / 100)), None)
        return {"success": True, "status": f"volume set to {level}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_process_info(**kwargs) -> dict:
    name = kwargs.get("name", "")
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "create_time"]):
            if name.lower() in p.info["name"].lower():
                procs.append(p.info)
        return {"success": True, "processes": procs[:10], "count": len(procs)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def kill_process(**kwargs) -> dict:
    name = kwargs.get("name", "")
    if not re.match(r"^[a-zA-Z0-9._\-, ]+$", name):
        return {"success": False, "error": f"Invalid process name: {name!r}"}
    try:
        subprocess.run(["taskkill", "/IM", f"{name}.exe", "/F"], capture_output=True, timeout=5)
        return {"success": True, "status": f"killed {name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def download_file(**kwargs) -> dict:
    url = kwargs.get("url", "")
    path = kwargs.get("path", "")
    try:
        import urllib.request
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        urllib.request.urlretrieve(url, path)
        size = os.path.getsize(path)
        return {"success": True, "status": f"downloaded to {path}", "size_bytes": size}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_battery(**kwargs) -> dict:
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery is None:
            return {"success": True, "battery_percent": None, "plugged_in": None,
                    "message": "No battery detected (desktop or VM)"}
        secs = battery.secsleft
        time_str = None
        if secs and secs > 0:
            h, m = divmod(int(secs) // 60, 60)
            time_str = f"{h}h {m}m remaining" if h else f"{m}m remaining"
        return {
            "success": True,
            "battery_percent": round(battery.percent, 1),
            "plugged_in": battery.power_plugged,
            "time_remaining": time_str,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_installed_apps(**kwargs) -> dict:
    query = kwargs.get("query", "").lower()
    try:
        db_path = Path(__file__).parent.parent / "indexer" / "db" / "pc_index.db"
        if not db_path.exists():
            return {"success": False, "error": "App index not built yet. Run the PC indexer first."}
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            if query:
                cur = conn.execute(
                    "SELECT name, exe_path FROM apps WHERE LOWER(name) LIKE ? LIMIT 30",
                    (f"%{query}%",),
                )
            else:
                cur = conn.execute("SELECT name, exe_path FROM apps LIMIT 50")
            rows = cur.fetchall()
        finally:
            conn.close()
        apps = [{"name": r[0], "exe_path": r[1]} for r in rows]
        return {"success": True, "apps": apps, "count": len(apps)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_brightness(**kwargs) -> dict:
    level = kwargs.get("level", 50)
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(max(0, min(100, level)))
        return {"success": True, "status": f"brightness set to {level}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def minimize_all_except(**kwargs) -> dict:
    exclude_titles = [t.lower() for t in kwargs.get("exclude_titles", [])]
    try:
        import pygetwindow as gw
        minimized = []
        for w in gw.getAllWindows():
            if not w.title.strip() or not w.visible:
                continue
            if any(ex in w.title.lower() for ex in exclude_titles):
                continue
            try:
                w.minimize()
                minimized.append(w.title)
            except Exception:
                pass
        return {"success": True, "minimized": minimized, "count": len(minimized)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def vision_query(**kwargs) -> dict:
    question = kwargs.get("question", "")
    region = kwargs.get("region")
    try:
        import pyautogui
        import io
        import base64
        if region:
            img = pyautogui.screenshot(
                region=(region["left"], region["top"], region["width"], region["height"])
            )
        else:
            img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        from brain import ollama_client
        from settings import LLM_VISION_MODEL, VISION_TIMEOUT
        result = ollama_client.chat(
            messages=[
                {
                    "role": "user",
                    "content": question,
                    "images": [b64],
                }
            ],
            model=LLM_VISION_MODEL,
            temperature=0.1,
            timeout=VISION_TIMEOUT,
            max_retries=1,
        )
        answer = result.get("content", "")
        return {"success": True, "answer": answer, "question": question}
    except Exception as e:
        # Fallback: OCR-based answer
        try:
            import pyautogui
            import pytesseract
            img = pyautogui.screenshot()
            text = pytesseract.image_to_string(img)
            return {
                "success": True,
                "answer": f"[Vision model unavailable, OCR fallback]\nScreen text:\n{text[:2000]}",
                "question": question,
                "fallback": True,
            }
        except Exception as ocr_err:
            return {"success": False, "error": f"vision_query failed: {e}; OCR fallback: {ocr_err}"}


def create_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        Path(path).touch()
        return {"success": True, "status": f"created {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def schedule(**kwargs) -> dict:
    from tools.comm.schedule_tool import schedule as _sched
    return _sched(**kwargs)


def listen(**kwargs) -> dict:
    from tools.voice.listen import listen as _listen
    return _listen(
        prompt=kwargs.get("prompt", ""),
        timeout_seconds=kwargs.get("timeout_seconds", 10),
        speak_prompt=kwargs.get("speak_prompt", True),
    )


def time_calendar(**kwargs) -> dict:
    from tools.comm.time_calendar import time_calendar as _tc
    return _tc(**kwargs)


def data_analysis(**kwargs) -> dict:
    data = kwargs.get("data", "")
    operations = kwargs.get("operations", "describe")
    code = f"""
import pandas as pd
import io
import json

data = {repr(data)}
ops = {repr(operations)}

try:
    df = pd.read_csv(io.StringIO(data))
except Exception:
    try:
        df = pd.DataFrame(eval(data))
    except Exception as e:
        print(json.dumps({{"error": f"Could not parse data: {{e}}"}}))
        raise SystemExit(1)

results = {{}}
if "describe" in ops or ops == "describe":
    results["describe"] = df.describe().to_dict()
if "head" in ops:
    results["head"] = df.head().to_dict()
if "correlation" in ops:
    results["correlation"] = df.corr(numeric_only=True).to_dict()
if "shape" in ops:
    results["shape"] = {{"rows": df.shape[0], "cols": df.shape[1], "columns": list(df.columns)}}

print(json.dumps(results, default=str))
"""
    return _run_code(code=code, language="python", timeout=30)


def update_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="store", key=kwargs.get("key"), value=kwargs.get("value"))


def summarize_session(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="search", query="", limit=kwargs.get("limit", 10))


# ---------------------------------------------------------------------------
# Clipboard tools
# ---------------------------------------------------------------------------

def read_clipboard(**kwargs) -> dict:
    """
    Read the current contents of the Windows clipboard.

    Tries pyperclip first (cross-platform), then falls back to
    a PowerShell one-liner so no extra package is required.
    """
    # Tier 1 — pyperclip (if installed)
    try:
        import pyperclip
        text = pyperclip.paste()
        return {"success": True, "text": text, "length": len(text)}
    except Exception:
        pass

    # Tier 2 — PowerShell (Windows, no extra deps)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5
        )
        text = result.stdout.rstrip("\n")
        return {"success": True, "text": text, "length": len(text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_clipboard(**kwargs) -> dict:
    """
    Write text to the Windows clipboard.

    Tries pyperclip first, then PowerShell fallback.
    """
    text = kwargs.get("text", "")

    # Tier 1 — pyperclip
    try:
        import pyperclip
        pyperclip.copy(text)
        return {"success": True, "status": f"copied {len(text)} chars to clipboard"}
    except Exception:
        pass

    # Tier 2 — PowerShell
    try:
        escaped = text.replace("'", "''")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{escaped}'"],
            capture_output=True, timeout=5
        )
        return {"success": True, "status": f"copied {len(text)} chars to clipboard"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Toast notification tool
# ---------------------------------------------------------------------------

def notify(**kwargs) -> dict:
    """
    Send a Windows desktop toast notification.

    FRIDAY uses this to proactively alert the user when a long task
    finishes, something critical is detected, or a scheduled reminder fires.

    Tries win10toast → PowerShell BalloonTip → msg command in that order.
    """
    title = kwargs.get("title", "F.R.I.D.A.Y.")
    message = kwargs.get("message", "")
    duration = int(kwargs.get("duration", 5))

    if not message:
        return {"success": False, "error": "message is required"}

    # Tier 1 — win10toast (pip install win10toast)
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=duration, threaded=True)
        return {"success": True, "status": f"toast sent: {title} — {message}"}
    except Exception:
        pass

    # Tier 2 — PowerShell BalloonTip (works on Win 10/11 without extra packages)
    try:
        ps_script = (
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Drawing') | Out-Null; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.Visible = $true; "
            f"$n.ShowBalloonTip({duration * 1000}, '{title.replace(chr(39), '')}', "
            f"'{message.replace(chr(39), '')}', "
            "[System.Windows.Forms.ToolTipIcon]::Info); "
            f"Start-Sleep -Seconds {duration}; "
            "$n.Visible = $false; $n.Dispose()"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return {"success": True, "status": f"balloon sent: {title} — {message}"}
    except Exception:
        pass

    # Tier 3 — msg command (shows a dialog, always available on Windows)
    try:
        subprocess.Popen(
            ["msg", "*", f"{title}: {message}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return {"success": True, "status": f"msg sent: {title} — {message}", "method": "msg"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delegate_to_subagent(**kwargs) -> dict:
    """
    Delegate a task to a specialized sub-agent and return its result.

    Jarvis calls this tool when a task is better handled by a focused worker:
      - ResearchAgent     → web searches, page fetching, fact-finding
      - FileAgent         → reading, writing, searching, organizing files
      - SystemAgent       → processes, hardware stats, app control
      - PerceptionAgent   → screen analysis, vision queries, UI detection, OCR
      - InteractionAgent  → mouse clicks, typing, scrolling, keyboard actions
      - MemoryAgent       → storing, retrieving, searching preferences and context

    The sub-agent runs its own tool loop and reports back a structured result
    with a human-readable summary that Jarvis uses in its reply to the user.
    """
    from agents.sub_agent_registry import registry
    from agents.base_agent import SubAgentTask

    agent_name = kwargs.get("agent", "")
    goal = kwargs.get("goal", "")
    context = kwargs.get("context", {})
    timeout = float(kwargs.get("timeout", 120))

    if not goal:
        return {"success": False, "error": "goal is required for delegate_to_subagent"}

    if agent_name:
        agent = registry.get(agent_name)
        if agent is None:
            available = [a["name"] for a in registry.list_agents()]
            return {
                "success": False,
                "error": f"Unknown sub-agent '{agent_name}'. Available: {available}",
            }
    else:
        agent = registry.route(goal)
        if agent is None:
            return {
                "success": False,
                "error": "Could not route task to any sub-agent. Specify 'agent' explicitly.",
            }

    task = SubAgentTask(goal=goal, context=context, timeout=timeout)
    try:
        result = agent.run(task)
    except Exception as e:
        return {
            "success": False,
            "error": f"Sub-agent '{agent.name}' raised an exception: {e}",
            "agent": agent.name,
        }

    return {
        "success": result.success,
        "agent": result.agent_name,
        "summary": result.summary,
        "data": result.data,
        "elapsed_s": result.elapsed_s,
        "tool_calls_count": len(result.tool_calls),
        "error": result.error or None,
    }


def lock_screen(**kwargs) -> dict:
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return {"success": True, "status": "screen locked"}
        else:
            subprocess.run(["loginctl", "lock-session"], timeout=5)
            return {"success": True, "status": "screen locked"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def shutdown(**kwargs) -> dict:
    confirmed = kwargs.get("_confirmed", False)
    if not confirmed:
        return {"success": False, "error": "Requires _confirmed=True after explicit user confirmation"}
    try:
        if os.name == "nt":
            subprocess.run(["shutdown", "/s", "/t", "10"], timeout=5)
        else:
            subprocess.run(["shutdown", "-h", "+1"], timeout=5)
        return {"success": True, "status": "shutdown scheduled in 10 seconds"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restart(**kwargs) -> dict:
    confirmed = kwargs.get("_confirmed", False)
    if not confirmed:
        return {"success": False, "error": "Requires _confirmed=True after explicit user confirmation"}
    try:
        if os.name == "nt":
            subprocess.run(["shutdown", "/r", "/t", "10"], timeout=5)
        else:
            subprocess.run(["shutdown", "-r", "+1"], timeout=5)
        return {"success": True, "status": "restart scheduled in 10 seconds"}
    except Exception as e:
        return {"success": False, "error": str(e)}
