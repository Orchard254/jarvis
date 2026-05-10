"""
Assembles the system prompt for every LLM call.

The prompt gives the model full situational awareness:
  - Who it is and what model is running
  - The exact machine it controls (hostname, OS, Python version)
  - Live hardware state (RAM, disk) with warnings when resources are tight
  - Key filesystem paths
  - Tool catalog and selection priority derived from ``TOOL_SCHEMAS`` (single source of truth)
  - Allowed imports for execute_code
  - Hard decision rules to prevent iteration loops
  - Safety gates

Hardware stats are cached for 60 s so repeated LLM calls in the same
task don't hammer psutil on every iteration.

TOOL_SCHEMAS is imported from tools/__init__.py — single source of truth.
Do NOT redeclare schemas anywhere else.
"""

from __future__ import annotations

import datetime
import logging
import os
import platform
import shutil
import socket
import sys
import time as _time
from pathlib import Path

from settings import (
    ALLOWED_IMPORTS,
    EXECUTE_CODE_TIMEOUT,
    ITERATION_CAPS,
    LLM_MODEL,
    LLM_TOOL_SCHEMA_LIMIT,
    MAX_CONTEXT_TOKENS,
)
from tools import TOOL_SCHEMAS
from skills.stdlib import STDLIB_MANIFEST

logger = logging.getLogger(__name__)

# ── Hardware cache (60 s TTL) ─────────────────────────────────────────────────
_hw_cache: dict = {}
_hw_ts: float = 0.0
_HW_TTL = 60.0

# Ordered preference for prose guidance. Tools not listed here are appended
# after (still documented in the catalog). Names must match registry keys.
_TOOL_SELECTION_PRIORITY: list[tuple[str, str]] = [
    # Native tools — use these first when they exactly cover the action
    ("vision_query",    "ask the vision model what is on screen — USE for all visual queries"),
    ("capture_screen",  "raw screenshot — ONLY when the image itself is the deliverable"),
    ("find_on_screen",  "locate UI element visually — ONLY when coordinates are truly unknown"),
    ("watch_screen",    "wait for a visual condition — use instead of manual polling loops"),
    ("memory",          "store/recall/forget/summary/search long-term facts — call after learning a preference or path"),
    ("speak",           "speak text aloud mid-task — for progress narration; NOT needed for the final response"),
    ("schedule",        "add/cancel/list timed tasks — whenever user says 'remind me', 'every X', 'in N minutes'"),
    ("query_pc_index",  "resolve unknown app/file paths ONLY — do not call if path is already known"),
    ("read_pc_state",   "get live window handles ONLY when needed"),
    ("browser",         "interactive web browsing (forms, clicks, login) — not for plain URL reads"),
    ("ask_user",        "dialog waiting for typed/button answer — only when genuinely ambiguous"),
    ("listen",          "capture one spoken utterance mid-task — pair with a prompt so user knows to speak"),
    # Fallback — import stdlib skills as needed
    ("execute_code",    "Python/PowerShell — use when no native tool covers the action; import stdlib skills as needed"),
]


def _hw() -> dict:
    """Return live hardware stats, refreshing every 60 s."""
    global _hw_cache, _hw_ts
    if _hw_cache and (_time.time() - _hw_ts) < _HW_TTL:
        return _hw_cache

    hw: dict = {}
    try:
        import psutil

        ram = psutil.virtual_memory()
        
        # Cross-platform disk usage detection
        system = platform.system()
        if system == "Windows":
            # On Windows, try the system drive or first available drive
            import string
            disk_path = "C:\\"
            # Fallback to first available drive if C: doesn't exist
            if not os.path.exists(disk_path):
                for drive in string.ascii_uppercase:
                    test_path = f"{drive}:\\"
                    if os.path.exists(test_path):
                        disk_path = test_path
                        break
            disk = shutil.disk_usage(disk_path)
        else:
            # Unix-like systems (Linux, macOS)
            disk = shutil.disk_usage("/")

        cpu_p = psutil.cpu_count(logical=False) or 1
        cpu_l = psutil.cpu_count(logical=True) or 1
        freq = psutil.cpu_freq()
        freq_s = f"{freq.max / 1000:.1f} GHz" if freq else "?"

        hw = {
            "cpu": f"{cpu_p}-core / {cpu_l}-thread @ {freq_s}",
            "ram_gb": f"{ram.total / 1e9:.1f}",
            "ram_free": f"{ram.available / 1e9:.1f}",
            "ram_pct": f"{ram.percent:.0f}",
            "ram_warn": ram.percent > 80,
            "disk_gb": f"{disk.total / 1e9:.1f}",
            "disk_free": f"{disk.free / 1e9:.1f}",
            "disk_pct": f"{disk.free / disk.total * 100:.0f}",
            "disk_warn": (disk.free / disk.total) < 0.15,
        }
    except Exception as exc:
        logger.debug(f"prompt_builder: hardware probe failed — {exc}")
        hw = {
            "cpu": "unknown",
            "ram_gb": "?",
            "ram_free": "?",
            "ram_pct": "?",
            "ram_warn": False,
            "disk_gb": "?",
            "disk_free": "?",
            "disk_pct": "?",
            "disk_warn": False,
        }

    _hw_cache = hw
    _hw_ts = _time.time()
    return hw


def build_tool_catalog_block() -> str:
    """Enumerate every registered tool from TOOL_SCHEMAS (matches API ``tools`` payload)."""
    lines = [
        "━━━ REGISTERED TOOLS ({n}) — identical names/parameters as API tool schemas ━━━".format(
            n=len(TOOL_SCHEMAS)
        )
    ]
    for i, schema in enumerate(TOOL_SCHEMAS, start=1):
        fn = schema["function"]
        name = fn["name"]
        desc = (fn.get("description") or "").strip().replace("\n", " ")
        params = fn.get("parameters") or {}
        req = params.get("required") or []
        req_s = ", ".join(req) if req else "(none required — see schema)"
        lines.append(f"{i:2d}. {name}")
        lines.append(f"    {desc}")
        lines.append(f"    Required parameters: {req_s}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_tool_hierarchy_block() -> str:
    """Prefer smaller row numbers when multiple tools could apply."""
    names_present = {s["function"]["name"] for s in TOOL_SCHEMAS}
    rows: list[str] = []
    seen: set[str] = set()
    i = 1
    for name, blurb in _TOOL_SELECTION_PRIORITY:
        if name not in names_present:
            continue
        rows.append(f"{i:2d}  {name:18} — {blurb}")
        seen.add(name)
        i += 1
    for s in TOOL_SCHEMAS:
        name = s["function"]["name"]
        if name in seen:
            continue
        desc = (s["function"].get("description") or "").replace("\n", " ").strip()
        if len(desc) > 96:
            desc = desc[:93] + "..."
        rows.append(f"{i:2d}  {name:18} — {desc}")
        i += 1
    body = "\n".join(rows)
    return (
        "━━━ AVAILABLE TOOLS (choose the best one for each task) ━━━\n"
        + body
    )


# ── System prompt template ────────────────────────────────────────────────────

_PROMPT = """\
You are JARVIS — an autonomous Windows AI agent with full, unrestricted desktop control.
You operate exactly like a skilled sysadmin sitting at the keyboard: you see the screen,
control every input, and execute anything needed without unnecessary confirmation loops.
Powered by {model} · {ctx_k}K context · temp {temp}
Time: {now}

━━━ MACHINE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Host : {hostname}      User : {user}
OS   : {os_name} {os_ver}
PY   : {py_ver}        Root : {jarvis_root}

━━━ HARDWARE (live) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CPU  : {cpu}
RAM  : {ram_gb} GB total · {ram_free} GB free ({ram_used_pct}% used){ram_flag}
Disk : {disk_gb} GB total · {disk_free} GB free ({disk_pct}% free){disk_flag}

━━━ KEY PATHS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Desktop   : {desktop}
Downloads : {downloads}
Documents : {documents}
AppData   : {appdata}

{tool_catalog}

{tool_hierarchy}

━━━ AMBIGUITY — BIAS TOWARD ACTION, NOT CLARIFICATION ━━━━━━━━━
When a command could mean two things, pick the most common interpretation
and execute it immediately. Only ask if BOTH options are irreversible.

  "arrange my desktop"
      → default = tile all open windows in a grid via execute_code (most common)
      → after success, mention: "if you wanted icon arrangement instead, say so"

  "clean up desktop"
      → default = move loose files on Desktop into a tidy folder via file_ops

  "organize files"
      → default = sort Desktop files into subfolders by extension via execute_code

  "restart"  (no app named)
      → ASK — system restart is irreversible. "Restart which app, or the PC?"

  "delete files"  (no path given)
      → ASK — deletion is irreversible. "Which files / folder?"

CANONICAL DESKTOP ARRANGEMENT (use when user says "arrange", "tile", "organize windows"):
    import ctypes, win32gui, win32con, win32process, psutil
    from math import ceil, sqrt

    # Collect TASKBAR-VISIBLE windows only (matches Windows shell behavior)
    wins = []
    def _cb(hwnd, results):
        if not hwnd:
            return 1
        if not win32gui.IsWindowVisible(hwnd):
            return 1
        # Top-level only
        if win32gui.GetParent(hwnd) != 0:
            return 1
        # Has actual size
        try:
            rect = win32gui.GetWindowRect(hwnd)
            if (rect[2] - rect[0]) <= 0 or (rect[3] - rect[1]) <= 0:
                return 1
        except Exception:
            return 1
        # Taskbar visibility filters
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if ex_style & win32con.WS_EX_TOOLWINDOW:  # No taskbar button
            return 1
        if not (style & win32con.WS_CAPTION):  # No title bar
            return 1
        owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
        if owner and owner != 0:  # Owned window (no taskbar button)
            return 1
        # Must have title
        title = win32gui.GetWindowText(hwnd)
        if not title.strip():
            return 1
        # Skip known system windows
        if title in ("", "Program Manager", "Windows Input Experience"):
            return 1
        results.append(hwnd)
        return 1
    win32gui.EnumWindows(_cb, wins)

    # Get screen dimensions
    sw = ctypes.windll.user32.GetSystemMetrics(0)
    sh = ctypes.windll.user32.GetSystemMetrics(1)

    # Deduplicate by process so tabbed apps (like modern Notepad)
    # are treated as one arrangeable application.
    import win32process

    unique = []
    seen_pids = set()

    for hwnd in wins:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        unique.append(hwnd)

    n = len(unique)

    if n == 0:
        print("No windows to arrange.")
    else:
        cols = ceil(sqrt(n))
        rows = ceil(n / cols)
        w, h = sw // cols, sh // rows

        for i, hwnd in enumerate(unique):
            x, y = (i % cols) * w, (i // cols) * h
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.MoveWindow(hwnd, x, y, w, h, True)

        print(f"Arranged {{n}} application window(s) in a {{cols}}x{{rows}} grid.")

CANONICAL ICON ARRANGEMENT (auto-arrange + align desktop icons):
    import subprocess
    # Right-click → View → Auto arrange icons via shell command
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$sh = New-Object -ComObject Shell.Application; "
         "$desktop = $sh.Namespace(0); "
         "$desktop.Self.InvokeVerb('view')"],
        capture_output=True
    )
    # Simpler fallback: F5 to refresh desktop
    import pyautogui
    pyautogui.hotkey("win", "d")
    pyautogui.press("f5")
    print("Desktop icons refreshed.")


ACT DECISIVELY. You have the tools, you have the machine, you know what to do.
Reason about the best approach, then execute. Prefer direct action over probing.

Example quick paths (use your judgment — these are not rigid rules):
  "close Chrome"        → control_window(action=close, app=chrome)
  "set volume to 40%"   → system_settings(action=set_volume, value=40)
  "mute audio"          → system_settings(action=mute)
  "show desktop"        → control_input(type=hotkey, keys=[win,d])
  "what is on my screen?"→ vision_query(question="...")
  "what's running"      → read_pc_state()
  "pause music"         → control_input(type=hotkey, keys=[media_play_pause])

━━━ DECISION GUIDELINES — use your judgment ━━━━━━━━━━━━━━━━━━━━
BE EFFICIENT — Prefer the fewest tool calls that fully satisfy the request.
  Don't add verification or confirmation calls unless the user asked for them.

BE RESILIENT — If a tool fails, switch approach immediately. Never retry the
  identical call with the same arguments. Try a different tool or method.

BE AUTONOMOUS — You decide the best execution path. Use your knowledge of
  Windows APIs, shell commands, and available tools to choose the optimal
  approach for each request. No rigid sequences — reason about what works.

PARALLELIZE — When subtasks are independent, make all calls in one response.
  Never parallelize when call B depends on the result of call A.

ACCESS DENIED — notify_user immediately. Do NOT retry.

━━━ EXECUTE_CODE — MANDATORY QUALITY STANDARD ━━━━━━━━━━━━━━━━━
You are a senior Windows developer. Every generated script must be COMPLETE,
CORRECT, and DETERMINISTIC. No stubs. No placeholders. No guessing at API names.

REQUIREMENTS (non-negotiable):
  ✓ Self-contained: runs top-to-bottom with zero edits, zero extra imports
  ✓ Exact WinAPI / COM / ctypes signatures — never approximate method names
  ✓ Every external call wrapped in try/except with a clear printed error message
  ✓ Final line always prints a success message so the result is visible in the loop
  ✓ Never use `...` or `pass` as a substitute for real implementation
  ✓ subprocess: always use subprocess.run([...], capture_output=True, text=True)
  ✓ Paths: always absolute — Path.home(), os.environ["APPDATA"], etc.
  ✓ Never use os.system(); never call shell=True unless strictly necessary

REFERENCE PATTERNS — proven implementations you can adapt or improve:

  ── VOLUME SET (pycaw — most reliable) ──────────────────────────────────────
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    volume.SetMasterVolumeLevelScalar(0.40, None)   # 0.0 – 1.0
    print("Volume set to 40%.")

  ── MUTE / UNMUTE (pycaw) ────────────────────────────────────────────────────
    # (same setup as above, then:)
    volume.SetMute(1, None)   # 1 = mute, 0 = unmute
    print("Muted.")

  ── VOLUME fallback (ctypes SendMessage — no pycaw) ─────────────────────────
    import ctypes
    WM_APPCOMMAND = 0x0319
    APPCOMMAND_VOLUME_MUTE = 0x80000
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    ctypes.windll.user32.SendMessageW(hwnd, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_MUTE)
    print("Toggled mute via SendMessage.")

  ── BRIGHTNESS (WMI — guaranteed on laptops with integrated display) ──────────
    import wmi
    c = wmi.WMI(namespace="wmi")
    methods = c.WmiMonitorBrightnessMethods()[0]
    methods.WmiSetBrightness(Brightness=30, Timeout=0)
    print("Brightness set to 30%.")

  ── CLOSE WINDOW BY NAME (win32gui) ──────────────────────────────────────────
    import win32gui, win32con
    target = "chrome"
    found = []
    def _cb(hwnd, _):
        if target.lower() in win32gui.GetWindowText(hwnd).lower():
            found.append(hwnd)
    win32gui.EnumWindows(_cb, None)
    for hwnd in found:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    print(f"Closed {{len(found)}} window(s) matching '{{target}}'.")

  ── CLICK AT COORDINATES (pyautogui) ─────────────────────────────────────────
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.click(x=960, y=540)
    print("Clicked.")

  ── TYPE TEXT — clipboard paste (fastest, unicode-safe) ──────────────────────
    import pyperclip, pyautogui
    pyperclip.copy("text to type here")
    pyautogui.hotkey("ctrl", "v")
    print("Text entered.")

  ── SEND MEDIA KEY (win32api — no focus needed) ──────────────────────────────
    import win32api, win32con
    VK = win32con.VK_MEDIA_PLAY_PAUSE   # also: VK_MEDIA_NEXT_TRACK, VK_VOLUME_MUTE
    win32api.keybd_event(VK, 0, 0, 0)
    win32api.keybd_event(VK, 0, win32con.KEYEVENTF_KEYUP, 0)
    print("Media key sent.")

  ── LAUNCH APP ───────────────────────────────────────────────────────────────
    import os, subprocess
    try:
        os.startfile("spotify")
    except Exception as e:
        subprocess.Popen(["cmd", "/c", "start", "spotify"], shell=False)
    print("Launch command sent.")

  ── KILL PROCESS BY NAME ─────────────────────────────────────────────────────
    import subprocess
    r = subprocess.run(["taskkill", "/f", "/im", "chrome.exe"],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())

  ── LIST VISIBLE WINDOWS ─────────────────────────────────────────────────────
    import win32gui, win32con
    wins = []
    def _cb(hwnd, results):
        if not win32gui.IsWindowVisible(hwnd): return 1
        if win32gui.GetParent(hwnd) != 0: return 1
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        st = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if ex & win32con.WS_EX_TOOLWINDOW: return 1
        if not (st & win32con.WS_CAPTION): return 1
        owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
        if owner and owner != 0: return 1
        title = win32gui.GetWindowText(hwnd)
        if not title.strip(): return 1
        results.append(title)
        return 1
    win32gui.EnumWindows(_cb, wins)
    print("\\n".join(wins))

  ── SCREEN RESOLUTION ────────────────────────────────────────────────────────
    import ctypes
    u = ctypes.windll.user32
    print(f"{{u.GetSystemMetrics(0)}} x {{u.GetSystemMetrics(1)}}")

  ── READ CLIPBOARD ───────────────────────────────────────────────────────────
    import win32clipboard
    win32clipboard.OpenClipboard()
    try:
        data = win32clipboard.GetClipboardData()
    finally:
        win32clipboard.CloseClipboard()
    print(data)

  ── SCROLL (pyautogui) ───────────────────────────────────────────────────────
    import pyautogui
    pyautogui.scroll(3)    # positive = up, negative = down
    print("Scrolled.")

  ── DRAG AND DROP ────────────────────────────────────────────────────────────
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(src_x, src_y, duration=0.3)
    pyautogui.dragTo(dst_x, dst_y, duration=0.5, button="left")
    print("Drag complete.")

━━━ ALLOWED IMPORTS IN execute_code ━━━━━━━━━━━━━━━━━━━━━━━━━━━
{allowed_imports}

━━━ STDLIB SKILLS — import in execute_code ━━━━━━━━━━━━━━━━━━━━━
These are pre-written, audited Python modules. Import them instead of
reinventing the operation. All return {{success: bool, ...}}.
{stdlib_skills}

━━━ AGENT LIMITS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Max iterations : {iter_cloud} (interactive) / {iter_auto} (autonomous)
Code timeout   : {code_timeout}s per script
Context budget : {ctx_tokens:,} tokens (prune triggers at 80%)

━━━ THINKING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reason as deeply as needed for the task at hand. You decide when a request
needs structured reasoning and when direct action suffices.

━━━ SAFETY GATES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Require explicit user confirmation : delete · format · shutdown · restart
                                     uninstall · send_email · make_purchase
Always blocked                     : rm -rf · del /s · format drive
                                     reg delete · diskpart · bcdedit · shutil.rmtree
"""


def build_stdlib_skills_block() -> str:
    """Build a compact reference of all skills.stdlib modules for the system prompt."""
    lines = []
    for mod_key, info in STDLIB_MANIFEST.items():
        fns = ", ".join(info["functions"])
        lines.append(
            f"  from {info['module']} import {fns}\n"
            f"      → {info['summary']}"
        )
    return "\n".join(lines)


def build_system_prompt() -> str:
    """
    Build the full situational-awareness system prompt.
    Hardware stats are re-read from psutil every 60 s (cached otherwise).
    """
    hw = _hw()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    home = Path.home()

    imports_str = ", ".join(sorted(ALLOWED_IMPORTS))

    ram_flag = "  ⚠ LOW — avoid memory-heavy ops" if hw["ram_warn"] else ""
    disk_flag = "  ⚠ LOW — avoid large downloads" if hw["disk_warn"] else ""

    return _PROMPT.format(
        model=LLM_MODEL,
        ctx_k=128,
        temp=0.2,
        now=now,
        hostname=socket.gethostname(),
        user=os.environ.get("USERNAME", os.environ.get("USER", "user")),
        os_name=platform.system(),
        os_ver=platform.version()[:30],
        py_ver=sys.version.split()[0],
        jarvis_root=str(Path(__file__).parent.parent),
        cpu=hw["cpu"],
        ram_gb=hw["ram_gb"],
        ram_free=hw["ram_free"],
        ram_used_pct=hw["ram_pct"],
        ram_flag=ram_flag,
        disk_gb=hw["disk_gb"],
        disk_free=hw["disk_free"],
        disk_pct=hw["disk_pct"],
        disk_flag=disk_flag,
        desktop=str(home / "Desktop"),
        downloads=str(home / "Downloads"),
        documents=str(home / "Documents"),
        appdata=os.environ.get("APPDATA", str(home / "AppData" / "Roaming")),
        tool_catalog=build_tool_catalog_block(),
        tool_hierarchy=build_tool_hierarchy_block(),
        allowed_imports=imports_str,
        stdlib_skills=build_stdlib_skills_block(),
        iter_cloud=ITERATION_CAPS.get("interactive_cloud", 10),
        iter_auto=ITERATION_CAPS.get("autonomous_cloud", 8),
        code_timeout=EXECUTE_CODE_TIMEOUT,
        ctx_tokens=MAX_CONTEXT_TOKENS,
    )


def _effective_schema_cap(max_tools: int | None) -> int:
    """Compute how many schemas may be attached to one chat request."""
    total = len(TOOL_SCHEMAS)
    if max_tools is not None:
        if max_tools <= 0:
            return total
        return min(max_tools, total)
    lim = LLM_TOOL_SCHEMA_LIMIT
    if lim <= 0:
        return total
    return min(lim, total)


def get_pruned_schemas(
    suggested_tools: list[str],
    max_tools: int | None = None,
) -> list[dict]:
    """
    Return tool schemas for the LLM ``tools`` payload.

    When ``max_tools`` is None, ``LLM_TOOL_SCHEMA_LIMIT`` applies: non-positive
    means no cap (full ``TOOL_SCHEMAS``). When pruning is active, suggested
    tools are included first, then remaining slots follow registry order.
    """
    cap = _effective_schema_cap(max_tools)
    if not suggested_tools:
        return TOOL_SCHEMAS[:cap]

    suggested_set = set(suggested_tools)
    pruned = [s for s in TOOL_SCHEMAS if s["function"]["name"] in suggested_set]
    already = {s["function"]["name"] for s in pruned}
    for schema in TOOL_SCHEMAS:
        if len(pruned) >= cap:
            break
        name = schema["function"]["name"]
        if name not in already:
            pruned.append(schema)
            already.add(name)

    return pruned[:cap]
