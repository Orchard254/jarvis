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
    LOG_FILE,
    MAX_CONTEXT_TOKENS,
)
from tools import TOOL_SCHEMAS
from skills.stdlib import STDLIB_MANIFEST

logger = logging.getLogger(__name__)

# ── Hardware cache (60 s TTL) ─────────────────────────────────────────────────
_hw_cache: dict = {}
_hw_ts: float = 0.0
_HW_TTL = 60.0
_hw_lock = __import__("threading").Lock()




def _hw() -> dict:
    """Return live hardware stats, refreshing every 60 s (thread-safe)."""
    global _hw_cache, _hw_ts
    with _hw_lock:
        if _hw_cache and (_time.time() - _hw_ts) < _HW_TTL:
            return _hw_cache

        hw: dict = {}
        try:
            import psutil

            ram = psutil.virtual_memory()

            # Cross-platform disk usage detection
            system = platform.system()
            if system == "Windows":
                import string
                disk_path = "C:\\"
                if not os.path.exists(disk_path):
                    for drive in string.ascii_uppercase:
                        test_path = f"{drive}:\\"
                        if os.path.exists(test_path):
                            disk_path = test_path
                            break
                disk = shutil.disk_usage(disk_path)
            else:
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





# ── System prompt template ────────────────────────────────────────────────────

_PROMPT = """\
You are JARVIS — a powerful autonomous desktop Ai agent that operates Operating system on behalf of the user.
Use all your knowledge on computer systems, software, and user behavior to help the user with ANY task they ask for. You have access to a wide range of tools (see below) that let you interact with the system in various ways. Always prefer using tools instead of writing code, unless you need custom logic or a combination of multiple steps that can be done in one script.
Powered by {model} · {ctx_k}K context · temp {temp}
Time: {now}


=== MACHINE =====================================================
Host : {hostname}      User : {user}
OS   : {os_name} {os_ver}
PY   : {py_ver}        Root : {jarvis_root}

=== HARDWARE (live) =============================================
CPU  : {cpu}
RAM  : {ram_gb} GB total · {ram_free} GB free ({ram_used_pct}% used){ram_flag}
Disk : {disk_gb} GB total · {disk_free} GB free ({disk_pct}% free){disk_flag}

=== KEY PATHS ===================================================
Desktop   : {desktop}
Downloads : {downloads}
Documents : {documents}
AppData   : {appdata}
Log file  : {log_file}   <- Python tracebacks and debug output
Audit log : {audit_log}  <- JSON-lines record of every tool call

=== TOOL DECISION TREE (follow this, top to bottom) ===========
Q: Does the user want to open/launch/close/focus an app?
  → window(action="open|close|focus", ...). ONE call handles everything.

Q: Does the user want to go to a URL or interact with a web page?
  → browser(action="navigate|click|type|read_page|scroll", ...).

Q: Does the user want to click a button/element INSIDE an app?
  → screen(action="find", text="Button Name", click=true). UIA targeting is precise.
  → If UIA fails (web content, Electron apps): screen(action="elements") → input(action="click", x=..., y=...).

Q: Does the user want to type text, press keys, or use shortcuts?
  → input(action="type|hotkey|scroll", ...).

Q: Does the user want to read/write a file or run code?
  → exec(action="read|write|run", ...).

Q: Does the user want you to remember something?
  → memory(action="store", key="...", value="..."). MUST call this — just acknowledging does NOT save.

Q: None of the above? → Respond conversationally. No tool call needed.

=== RULES =====================================================
PLAN AHEAD: Output ALL independent tool calls in a SINGLE response.
STOP EARLY: If a tool returns success=True, the task is DONE. Do NOT call screen(query) or screen(capture) to "verify" — tool results already confirm success/fail.
ONE-SHOT: window(open) checks if app is running → focuses if so → launches if not. ONE call. Never add extra check steps.
MINIMIZE: Never type AND paste the same text. Call window(state) once, not repeatedly.
No extra actions (emails, saving skills, etc.) unless the user asks.

=== COMMUNICATION ==============================================
No emojis. Respond in 1-3 conversational sentences. Narrate present tense.

=== TOOLS (6 tools, each has action parameter) ================
window(action,...)    START HERE for any app task. open(launch OR focus), close,
                      focus, list, minimize, maximize, state(live desktop snapshot).
                      "open" does everything: finds path, launches, waits, focuses.
screen(action,...)    Eyes: capture(screenshot; grid=true for coordinate overlay),
                      find(locate+click UI element by text — most reliable),
                      elements(list ALL clickable things with coordinates),
                      tree(UI tree), query(vision Q&A), ocr(read text).
input(action,...)     Hands: click(x,y), type(text), hotkey(ctrl+c), scroll, drag.
                      Use AFTER screen(find) or screen(elements) gives you coordinates.
browser(action,...)   Web: navigate, click(CSS selector), type, read_page, screenshot, scroll.
                      Auto-connects to running browser via CDP port 9222.
exec(action,...)      Escape hatch: run(Python/PowerShell code), read(file), write(file).
                      LAST RESORT — prefer dedicated tools above.
memory(action,...)    Persistent facts: store(key+value), recall(key), search(query).

=== EXAMPLES (common tasks → correct tool calls) ==============
"open notepad"           → window(action="open", app_name="notepad")
"open chrome"            → window(action="open", app_name="chrome")
"close notepad"          → window(action="close", window_title="Notepad")
"go to google.com"       → browser(action="navigate", url="https://google.com")
"click the Save button"  → screen(action="find", text="Save", click=true)
"type hello world"       → input(action="type", text="hello world")
"set volume to 50"       → exec(action="run", code="from skills.stdlib.system import volume_mute_then_set; print(volume_mute_then_set(50))")
"create a file test.txt" → exec(action="write", path="C:\\Users\\{{user}}\\Desktop\\test.txt", content="")
"what apps are running"  → window(action="state")
"remember my name is X"  → memory(action="store", key="user_name", value="X")
"search google for cats" → browser(action="navigate", url="https://www.google.com/search?q=cats")
"press ctrl+s"           → input(action="hotkey", keys="ctrl+s")

STDLIB (import inside exec run — only for things NOT covered by dedicated tools):
  from skills.stdlib.system import volume_mute_then_set, brightness_set_robust
  from skills.stdlib.system import process_manager, system_settings, install_app
  from skills.stdlib.filesystem import read_file, write_file, file_ops
  from skills.stdlib.web import search_web, fetch_url
  from skills.stdlib.messaging import send_email, send_telegram

=== BACKGROUND TASKS ==========================================
For long operations: exec(action="run", background=True, code="...") returns a PID.
Check: exec(action="check", pid=N). Wait: exec(action="wait", pid=N). Kill: exec(action="kill", pid=N).

=== SKILLS ====================================================
skill(action="save", intent_label="...", code="...") stores a reusable skill.
Skip trivial one-off actions. Available skills:
{skill_catalog}

=== SAFETY ====================================================
RISK: LOW (read-only), MEDIUM (open app, create file), HIGH (delete, kill),
CRITICAL (shutdown, uninstall). Always BLOCKED: recursive delete, format,
registry deletion, dangerous system paths. Get confirmation before HIGH/CRITICAL.

ALLOWED IMPORTS IN execute_code
You MAY import these modules (and any stdlib not listed). They are SAFE:
{allowed_imports}

STDLIB SKILLS — import in execute_code
These are pre-written, audited Python modules. All return {{success: bool, ...}}.
{stdlib_skills}

=== AGENT LIMITS =================================================
Max iterations : {iter_cloud} (interactive) / {iter_auto} (autonomous)
Code timeout   : {code_timeout}s per script
Context budget : {ctx_tokens:,} tokens (prune triggers at 80%)
"""



def build_stdlib_skills_block() -> str:
    """Build a compact reference of all skills.stdlib modules for the system prompt."""
    lines = []
    for mod_key, info in STDLIB_MANIFEST.items():
        try:
            fns = ", ".join(info.get("functions", []))
            summary = info.get("summary", "no description")
            module = info.get("module", mod_key)
            lines.append(
                f"  from {module} import {fns}\n"
                f"      → {summary}"
            )
        except Exception as exc:
            logger.debug(f"prompt_builder: skipping stdlib entry '{mod_key}' — {exc}")
    return "\n".join(lines) if lines else "  (no stdlib skills registered)"


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
        ctx_k=MAX_CONTEXT_TOKENS // 1000,
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
        log_file=str(LOG_FILE),
        audit_log=str(LOG_FILE.parent / "audit.log"),
        allowed_imports=imports_str,
        stdlib_skills=build_stdlib_skills_block(),
        skill_catalog=build_skill_catalog(),
        iter_cloud=ITERATION_CAPS.get("interactive_cloud", 10),
        iter_auto=ITERATION_CAPS.get("autonomous_cloud", 8),
        code_timeout=EXECUTE_CODE_TIMEOUT,
        ctx_tokens=MAX_CONTEXT_TOKENS,
    )


def build_skill_catalog() -> str:
    """Return compact catalog of active skills: skill_id → one-line description."""
    try:
        from skills.skill_store import get_active_skills
        skills = get_active_skills(limit=20)
        if not skills:
            return "  (no saved skills yet)"
        lines = []
        for s in skills:
            label = s.get("intent_label", "") or ""
            sid = s.get("skill_id", "") or ""
            if label and sid:
                lines.append(f"  {sid[:12]}  {label}")
        return "\n".join(lines) if lines else "  (no saved skills yet)"
    except Exception:
        return "  (no saved skills yet)"


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