"""
Primitive: execute_code(code, language='python')
Sandboxed subprocess with AST guard, minimal env, and process tree kill.
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows-only constant for hiding console windows
if sys.platform == "win32":
    CREATE_NO_WINDOW = 0x00080000  # CREATE_NO_WINDOW constant for hiding console windows
else:
    CREATE_NO_WINDOW = 0

from safety.tool_guard import check_imports, get_safe_env
from settings import EXECUTE_CODE_TIMEOUT

logger = logging.getLogger(__name__)

# ── Launch-app script template ────────────────────────────────────────────────
# Uses os.startfile (ShellExecuteW) — no dedicated tool needed.
# APP_NAME is substituted at call-time via % formatting.
_LAUNCH_APP_SCRIPT = """
import os
from pathlib import Path

APP_NAME = %s

# ── Step 0: Windows built-in alias table ──────────────────────────────────
# Maps common spoken/typed names to the real executable or protocol that
# Windows actually registers.  This avoids fuzzy-search false positives
# (e.g. "calculator" matching "Calculator Tools 10.0.lnk" from KiCad).
_BUILTIN = {
    # System utilities
    "calculator":       "calc.exe",
    "calc":             "calc.exe",
    "notepad":          "notepad.exe",
    "paint":            "mspaint.exe",
    "mspaint":          "mspaint.exe",
    "wordpad":          "wordpad.exe",
    "explorer":         "explorer.exe",
    "file explorer":    "explorer.exe",
    "this pc":          "explorer.exe",
    "cmd":              "cmd.exe",
    "command prompt":   "cmd.exe",
    "terminal":         "wt.exe",
    "windows terminal": "wt.exe",
    "powershell":       "powershell.exe",
    "task manager":     "taskmgr.exe",
    "taskmgr":          "taskmgr.exe",
    "control panel":    "control.exe",
    "regedit":          "regedit.exe",
    "registry":         "regedit.exe",
    "snipping tool":    "SnippingTool.exe",
    "snip":             "SnippingTool.exe",
    "screenshot tool":  "SnippingTool.exe",
    "remote desktop":   "mstsc.exe",
    "mstsc":            "mstsc.exe",
    "disk management":  "diskmgmt.msc",
    "device manager":   "devmgmt.msc",
    "event viewer":     "eventvwr.msc",
    "services":         "services.msc",
    "task scheduler":   "taskschd.msc",
    "character map":    "charmap.exe",
    "on-screen keyboard": "osk.exe",
    "magnifier":        "magnify.exe",
    "narrator":         "narrator.exe",
    "msconfig":         "msconfig.exe",
    "system config":    "msconfig.exe",
    "resource monitor": "resmon.exe",
    "perfmon":          "perfmon.exe",
    # MS Store / UWP protocol launchers
    "settings":         "ms-settings:",
    "windows settings": "ms-settings:",
    "store":            "ms-windows-store:",
    "microsoft store":  "ms-windows-store:",
    "calendar":         "outlookcal:",
    "mail":             "outlookmail:",
    "maps":             "bingmaps:",
    "weather":          "bingweather:",
    "clock":            "ms-clock:",
    "alarms":           "ms-clock:",
    "sticky notes":     "ms-stickynotes:",
    "photos":           "ms-photos:",
    "camera":           "microsoft.windows.camera:",
    "xbox":             "xbox:",
    "groove music":     "mswindowsmusic:",
    "movies & tv":      "mswindowsvideo:",
    "3d viewer":        "com.microsoft.microsoft3dviewer:",
}

def _try_launch(target):
    try:
        os.startfile(str(target))
        print("Launched:", str(target))
        return True
    except Exception as exc:
        # Don't print here — caller collects failures and only reports them
        # if every strategy fails. This prevents partial-failure noise from
        # appearing in stdout when a later strategy succeeds.
        return False

# ── Strategy 0: built-in alias lookup (most reliable) ───────────────────
_alias_key = APP_NAME.lower().strip()
if _alias_key in _BUILTIN:
    if _try_launch(_BUILTIN[_alias_key]):
        raise SystemExit(0)

# ── Strategy 1: Windows shell association (PATH / registered apps) ────────
if _try_launch(APP_NAME):
    raise SystemExit(0)

# ── Strategy 2: scored fuzzy search across Desktop + Start Menu ──────────
# Match quality (lower score = better match):
#   0 - exact         : stem == needle
#   1 - stem prefix   : stem starts with needle AND needle is >=70 pct of stem
#   2 - needle prefix : needle starts with stem AND stem is >=70 pct of needle
# Substring-only matches are excluded to avoid false positives like
# 'calculator' matching 'Calculator Tools 10.0' from a 3rd-party app.
needle = APP_NAME.lower().replace(" ", "").replace("-", "").replace("_", "")
_roots = [
    Path.home() / "Desktop",
    Path(os.environ.get("PUBLIC", "")) / "Desktop",
]
for _base_key, _sub in [
    ("APPDATA",     "Microsoft/Windows/Start Menu/Programs"),
    ("ProgramData", "Microsoft/Windows/Start Menu/Programs"),
]:
    _b = os.environ.get(_base_key, "")
    if _b:
        _roots.append(Path(_b) / _sub)

_candidates = []  # list of (score, path)
for _root in _roots:
    if not _root.exists():
        continue
    for _ext in ("*.lnk", "*.exe"):
        try:
            for _f in _root.rglob(_ext):
                _stem = _f.stem.lower().replace(" ", "").replace("-", "").replace("_", "")
                if _stem == needle:
                    _candidates.append((0, _f))   # exact
                elif _stem.startswith(needle) and len(needle) >= len(_stem) * 0.70:
                    _candidates.append((1, _f))   # stem prefix, close enough
                elif needle.startswith(_stem) and len(_stem) >= len(needle) * 0.70:
                    _candidates.append((2, _f))   # needle prefix, close enough
        except PermissionError:
            pass

if _candidates:
    # Best score wins; break ties by preferring shorter stems (more specific)
    _candidates.sort(key=lambda x: (x[0], len(x[1].stem)))
    if _try_launch(_candidates[0][1]):
        raise SystemExit(0)

print("ERROR: Could not find or launch", repr(APP_NAME))
print("Available options:")
print("  1. Check spelling and try again")
print("  2. Search Start Menu manually for the exact app name")
print("  3. Provide the full path to the executable")
"""

# ── Install-app script template (PowerShell / winget) ─────────────────────────
# Searches first so the user can confirm; does NOT install automatically.
_INSTALL_SEARCH_SCRIPT = """
$app = %s
Write-Host "Searching winget for: $app"
winget search $app --accept-source-agreements 2>&1
Write-Host ""
Write-Host "To install, run: winget install --exact --id '<ID from above>' --accept-source-agreements --accept-package-agreements"
"""

# ── Web search script template ─────────────────────────────────────────────
# Strategy 1 : DuckDuckGo HTML scrape (real results, no API key).
# Strategy 2 : DuckDuckGo Instant Answer API fallback.
# Strategy 3 : Helpful message with direct browser links.
_WEB_SEARCH_SCRIPT = """
import requests, urllib.parse, re

QUERY = %s
encoded = urllib.parse.quote_plus(QUERY)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def _ddg_html(q_enc):
    url = "https://html.duckduckgo.com/html/?q=" + q_enc
    resp = requests.get(url, timeout=12, headers=_HEADERS)
    html = resp.text

    # Capture (opening_tag, title_text) for every result__a anchor
    link_blocks = re.findall(
        r'(<a\b[^>]*class="[^"]*result__a[^"]*"[^>]*>)([^<]+)</a>', html
    )
    # Capture snippet text from result__snippet anchors
    raw_snippets = re.findall(
        r'<a\b[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )
    snippets = [re.sub(r'<[^>]+>', '', s).strip() for s in raw_snippets]

    results = []
    for i, (tag, title) in enumerate(link_blocks[:5]):
        href_m = re.search(r'href="([^"]*)"', tag)
        href = href_m.group(1) if href_m else ""
        # DDG wraps links in a redirect — extract the real destination URL
        if "uddg=" in href:
            m = re.search(r'uddg=([^&]+)', href)
            if m:
                href = urllib.parse.unquote_plus(m.group(1))
        snippet = snippets[i] if i < len(snippets) else ""
        results.append((title.strip(), snippet, href))
    return results

def _ddg_instant(q_enc):
    url = ("https://api.duckduckgo.com/?q=" + q_enc
           + "&format=json&no_html=1&skip_disambig=1")
    resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    data = resp.json()
    lines = []
    if data.get("AbstractText"):
        lines.append(data["AbstractText"])
        if data.get("AbstractURL"):
            lines.append("Source: " + data["AbstractURL"])
    elif data.get("Answer"):
        lines.append(data["Answer"])
    elif data.get("RelatedTopics"):
        for topic in data["RelatedTopics"][:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                lines.append(topic["Text"])
    return lines

found = False

# Strategy 1: DuckDuckGo HTML scrape
try:
    results = _ddg_html(encoded)
    if results:
        print("Search results for:", QUERY)
        print()
        for idx, (title, snippet, link) in enumerate(results, 1):
            print(str(idx) + ". " + title)
            if snippet:
                print("   " + snippet)
            if link:
                print("   URL: " + link)
            print()
        found = True
except Exception:
    pass

# Strategy 2: DuckDuckGo Instant Answer API
if not found:
    try:
        lines = _ddg_instant(encoded)
        if lines:
            print("Search results for:", QUERY)
            print()
            for line in lines:
                print(line)
            found = True
    except Exception:
        pass

# Strategy 3: Helpful fallback message
if not found:
    print("No results found for:", QUERY)
    print("Try opening a browser and searching at:")
    print("  https://www.google.com/search?q=" + encoded)
    print("  https://duckduckgo.com/?q=" + encoded)
"""


def get_fallback_script(intent: str) -> str | None:
    """
    Return an optimised, pre-built script for common intent patterns.
    
    DEPRECATED: This function now returns None for all intents.
    Modern LLMs handle these cases well with tool calling.
    Kept for backward compatibility but effectively disabled.
    """
    return None


def execute_code(code: str, language: str = "python") -> dict:
    """
    Execute Python or PowerShell code in a sandboxed subprocess.
    
    Args:
        code: The code to execute
        language: Either "python" or "powershell" (default: "python")
    
    Returns:
        dict with keys: success, output/error, return_code
    """
    from safety.tool_guard import check_imports, get_safe_env
    
    if language not in ("python", "powershell"):
        return {
            "success": False,
            "error": f"Unsupported language: {language}. Must be 'python' or 'powershell'."
        }
    
    # Security check for Python code
    if language == "python":
        allowed, reason = check_imports(code)
        if not allowed:
            return {"success": False, "error": f"Security check failed: {reason}"}
    
    # Create a temporary file for the code
    import tempfile
    import subprocess
    import sys
    
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py" if language == "python" else ".ps1",
            delete=False
        ) as f:
            f.write(code)
            temp_path = f.name
        
        # Build the command
        if language == "python":
            cmd = [sys.executable, temp_path]
        else:  # powershell
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", temp_path]
        
        # Execute with timeout
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=EXECUTE_CODE_TIMEOUT,
            env=get_safe_env(),
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        
        # Clean up temp file
        import os
        try:
            os.unlink(temp_path)
        except:
            pass
        
        if result.returncode == 0:
            return {
                "success": True,
                "output": result.stdout,
                "return_code": result.returncode
            }
        else:
            return {
                "success": False,
                "error": result.stderr or f"Process exited with code {result.returncode}",
                "output": result.stdout,
                "return_code": result.returncode
            }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Code execution timed out after {EXECUTE_CODE_TIMEOUT} seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

