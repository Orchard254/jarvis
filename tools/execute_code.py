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
    The LLM receives this as the ``code`` to execute, so it succeeds on
    iteration 1 without guessing or looping.
    """
    intent_lower = intent.lower()

    # ── Largest files ──────────────────────────────────────────────────
    if "largest files" in intent_lower or "top files" in intent_lower:
        return """import os, pathlib
from pathlib import Path

def find_large_files(root, top_n=5, min_size_mb=10):
    results = []
    min_bytes = min_size_mb * 1024 * 1024
    for f in Path(root).rglob("*"):
        try:
            if f.is_file() and f.stat().st_size >= min_bytes:
                results.append((f, f.stat().st_size))
        except (PermissionError, OSError):
            continue
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]

for path, size in find_large_files(Path.home()):
    print(f"{path}\t{size:,} bytes")
"""

    # ── Disk space ─────────────────────────────────────────────────────
    if "disk space" in intent_lower or "storage" in intent_lower:
        return """import shutil, psutil
disk = shutil.disk_usage("C:\\")
print(f"Total: {disk.total//1e9:.1f}GB")
print(f"Used: {disk.used//1e9:.1f}GB ({disk.used/disk.total*100:.1f}%)")
print(f"Free: {disk.free//1e9:.1f}GB")
"""

    # ── Open / launch app ──────────────────────────────────────────────
    # Match: "open X", "launch X", "start X", "run X"
    # Strip noise words a user might append ("found in desktop dir", etc.)
    _open_m = re.match(
        r"^(?:open|launch|start|run)\s+(.+)",
        intent_lower,
    )
    if _open_m:
        # Preserve original casing from the raw intent for the actual name
        raw_suffix = intent[_open_m.start(1) :].strip()
        # Drop trailing context hints the user typed (e.g. "found in desktop dir")
        raw_suffix = re.sub(
            r"\s+(found|located|in|at|on|from)\b.*$", "", raw_suffix, flags=re.I
        ).strip()
        # Drop generic suffixes
        raw_suffix = re.sub(
            r"\s+(?:app|application|program|software|exe)$", "", raw_suffix, flags=re.I
        ).strip()
        # Split multi-app commands: "notepad and calculator" → ["notepad", "calculator"]
        app_names = re.split(r"\s+and\s+|,\s*", raw_suffix)
        app_names = [a.strip() for a in app_names if a.strip()]
        if app_names:
            if len(app_names) == 1:
                return _LAUNCH_APP_SCRIPT % repr(app_names[0])
            # Multi-app: generate a script that launches each one
            lines = ["import os", "from pathlib import Path", ""]
            for an in app_names:
                lines.append(f"APP_NAME = {repr(an)}")
                lines.append(_LAUNCH_APP_SCRIPT.strip())
                lines.append("")
            return "\n".join(lines)

    # ── Install app (search first, never auto-install) ─────────────────
    _install_m = re.match(
        r"^(?:install|download|setup|add|get)\s+(.+)",
        intent_lower,
    )
    if _install_m:
        raw_app = intent[_install_m.start(1) :].strip()
        raw_app = re.sub(
            r"\s+(?:app|application|program|software)$", "", raw_app, flags=re.I
        ).strip()
        if raw_app:
            return _INSTALL_SEARCH_SCRIPT % repr(raw_app)

    # ── Web search ──────────────────────────────────────────────────
    _search_m = re.match(
        r"^(?:search(?:\s+for)?|google|look\s*up|what\s+is|what\s+are|who\s+is|find\s+out)\s+(.+)",
        intent_lower,
    )
    if _search_m:
        raw_query = intent[_search_m.start(1) :].strip()
        # ── Local system-state exclusion ──────────────────────────────
        # Phrases like "what is my cpu usage" or "what is the time" are
        # LOCAL system queries answered by psutil / datetime — NOT web
        # searches.  Skip the web-search script for these so the LLM
        # (or a psutil fast-path) handles them instead.
        _SYSTEM_QUERY_WORDS = {
            # Hardware / OS state
            "cpu",
            "ram",
            "memory",
            "disk",
            "battery",
            "storage",
            "time",
            "date",
            "clock",
            "temperature",
            "uptime",
            "network",
            "wifi",
            "ip",
            "processes",
            "performance",
            "usage",
            "speed",
            "free space",
            "my pc",
            "my computer",
            # Personal identity — answered from memory, not the web
            "my name",
            "my age",
            "my birthday",
            "who am i",
            "my real name",
            "my username",
        }
        # Also exclude if raw_query starts with "my " (possessive personal query)
        if raw_query.lower().startswith("my "):
            return None
        query_words = set(raw_query.lower().split())
        if query_words & _SYSTEM_QUERY_WORDS:
            return None  # let the LLM handle it with psutil/datetime tools
        if raw_query:
            return _WEB_SEARCH_SCRIPT % repr(raw_query)

    return None


def execute_code(code: str, language: str = "python") -> dict:
    safe, reason = check_imports(code)
    if not safe:
        return {"success": False, "blocked": True, "stderr": reason}

    try:
        if sys.platform == "win32":
            return _execute_with_job_object(code, language)
        else:
            return _execute_with_subprocess(code, language)
    except Exception as e:
        logger.error(f"execute_code error: {e}")
        return {"success": False, "stderr": str(e)}


def _execute_with_subprocess(code: str, language: str = "python") -> dict:
    import psutil

    stdout = b""
    stderr = b""
    returncode = -1
    
    try:
        if language == "python":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                tmp_path = f.name
            try:
                proc = subprocess.Popen(
                    [sys.executable, tmp_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(Path.home()),
                    env=get_safe_env(),
                    creationflags=CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                )
                _kill_tree_on_timeout(proc, EXECUTE_CODE_TIMEOUT)
                stdout, stderr = proc.communicate()
                returncode = proc.returncode
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        elif language == "powershell":
            proc = subprocess.Popen(
                ["powershell", "-NonInteractive", "-Command", code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            _kill_tree_on_timeout(proc, EXECUTE_CODE_TIMEOUT)
            stdout, stderr = proc.communicate()
            returncode = proc.returncode
        else:
            return {"success": False, "stderr": f"Unsupported language: {language}"}
    except Exception as e:
        logger.error(f"Subprocess execution failed: {e}")
        stderr = str(e).encode("utf-8", errors="replace")

    # Add actionable error context when execution fails
    result = {
        "stdout": stdout.decode("utf-8", errors="replace")[:4096],
        "stderr": stderr.decode("utf-8", errors="replace")[:2048],
        "returncode": returncode,
        "success": returncode == 0,
    }
    
    # If failed, provide structured guidance without biasing toward specific tools
    if not result["success"]:
        error_lower = result["stderr"].lower()
        suggestions = [
            "Check if the code has syntax errors",
            "Verify file paths exist before accessing them", 
            "Ensure required permissions are available",
            "Try a simpler approach or break into smaller steps"
        ]
        
        # Add context-specific hints based on error type
        if "file not found" in error_lower or "no such file" in error_lower:
            suggestions.insert(0, "Use query_pc_index to locate files/apps if path is unknown")
        elif "permission" in error_lower or "access is denied" in error_lower:
            suggestions.insert(0, "Run as administrator or choose a different location")
        elif "module" in error_lower and ("not found" in error_lower or "import" in error_lower):
            suggestions.insert(0, "Install missing module via pip or use alternative approach")
        
        result["error_context"] = {
            "type": "execution_failure",
            "suggestions": suggestions
        }
    
    return result


def _execute_with_job_object(code: str, language: str = "python") -> dict:
    return _execute_with_subprocess(code, language)


def _kill_tree_on_timeout(proc: subprocess.Popen, timeout: int):
    """Wait up to *timeout* seconds, then kill the entire process tree.

    Kill order: parent first (stops it spawning new children), then all
    descendants.  Uses psutil.wait_procs() to confirm death.

    Note: processes launched with DETACH_PROCESS / CREATE_NEW_PROCESS_GROUP
    may survive — a Windows Job Object would be required to prevent that,
    but implementing one portably via ctypes is out of scope here.
    """
    import psutil

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            parent = psutil.Process(proc.pid)
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            return  # already gone

        # Kill parent first so it cannot spawn additional children
        try:
            parent.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Kill all (grand)children
        for child in children:
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Give the OS a moment to reap them
        psutil.wait_procs([parent] + children, timeout=3)
