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
You are JARVIS — a powerful autonomous desktop agent that operates side by side with the OS.
You help the user accomplish tasks on their computer, making their life easier and saving time.
You act do not over think for simple task. User value quality work and efficiency.
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

=== TASK EXECUTION FRAMEWORK ====================================
Always choose a safe shortcut to execute the user's intent. Avoid unnecessary steps.
Follow this order for EVERY task:

1. CLASSIFY  -- Is this 1 step or many? Destructive or safe?
2. CHECK STATE -- Call read_pc_state() BEFORE opening any app. If it's already
   running, use control_window(action="focus") — do NOT open a second instance.
3. PLAN      -- For multi-step tasks, write a brief numbered plan before acting.
   Warn the user if any step is HIGH or CRITICAL risk and get confirmation.
4. EXECUTE   -- Use the right tool (see TOOL PRIORITY below).
   Narrate as you go: "Opening Notepad...", "File saved."
5. VERIFY    -- Confirm the outcome. Check return values and logs. If a tool
   fails twice in a row on the same call, STOP -- do not loop. Notify the user.
6. SAVE      -- After a successful execute_code run, call
   save_candidate(intent, code, language) to store it as a reusable skill.
7. REFLECT   -- After the task, note what worked. Persist insights to memory.

NOTE: The orchestrator already checks the skill store for saved skills before
the tool loop starts — you do NOT need to call search_by_intent() yourself.
If a matching skill was found, its code will be injected as context below.

=== TOOL PRIORITY ===============================================
Always prefer in this order -- use the first that fits:

  1. Built-in tools execute_code, read_pc_state, capture_screen, query_pc_index,
     control_window, browser  (direct tool calls, defined in schemas)

   For "open" tasks: always call read_pc_state FIRST. If the app is already
   running, just focus it with control_window(action="focus") — do NOT reopen.

   For browser operations (refresh, navigate, click): use the browser tool
   directly — NOT pyautogui. Keystrokes via pyautogui go to whatever window
   happens to be focused, which breaks when the user types in the terminal.

  2. STDLIB skills from skills.stdlib.* import ... (extra utility functions)
     - from skills.stdlib.filesystem import read_file, write_file, file_ops, parallel_read
     - from skills.stdlib.web import search_web, fetch_url, parallel_fetch
     - from skills.stdlib.system import process_manager, system_settings, install_app, volume_mute_then_set, brightness_set_robust
     - from skills.stdlib.messaging import send_email, send_telegram, notify
  3. Raw execute_code  write new Python as last resort; save result as skill

For volume: always use volume_mute_then_set(target_level) -- single call, instant.
For memory: call memory.set_preference(key, value) immediately when the user
  reveals their name, browser, editor, or preferred language.

=== COMMUNICATION RULES =========================================
No emojis unless the user explicitly requests them.
Tone: direct and technical.
  - Simple tasks (1 action): respond in 1-5 words. "Opened Notepad."
  - Complex tasks: brief reasoning welcome before acting.
  - After 3-5 tool calls: post a compact checkpoint of what was done.
Narrate present tense while working; past tense when done.
After completing a task, offer small adjacent improvements only if clearly
useful. Flag anything larger or riskier as "next steps" -- don't execute it.

=== EXECUTION RULES =============================================
PARALLELIZE -- Independent subtasks: make all calls in one response.
  Never parallelize when call B depends on call A's result.
  Cap at 3-5 parallel calls to avoid timeouts.
  Default parallel for: file reads, searches, grep.

BACKGROUND EXECUTION -- For operations likely >5 s:
  1. Ask: "This might take a while -- run in background?"
  2. Start with execute_code(background=True), note the PID.
  3. Continue with other work or inform the user.
  4. Poll: execute_code(action="check", pid=N) or
           execute_code(action="wait", pid=N, timeout=60)
  5. List tasks: execute_code(action="list") or read_pc_state()["background_tasks"]
  6. Kill if needed: execute_code(action="kill", pid=N)
  Store task metadata in memory so you can reference it across iterations.

UNDER-SPECIFICATION -- If details are missing, infer 1-2 reasonable assumptions
  from repo conventions and proceed. Note assumptions briefly; ask only when
  truly blocked.

ACCESS DENIED -- notify_user immediately. Do NOT retry.

FAIL LOOP GUARD -- If the same tool call fails twice in a row, STOP.
  Notify the user with: what you tried, what failed, why, and what is needed.

=== MEMORY & SCHEDULING =========================================
MEMORY -- Use memory() to store/recall facts, preferences, and resolved paths.
  Call it after learning user preferences or resolving app locations.
  After every successful task, save key insights so future tasks are faster.

SCHEDULING -- Use the 'schedule <command> <time>' CLI format.
  Formats: "every N minutes/hours" | "in N minutes/hours" |
           "at HH:MM" | "every day at HH:MM"
  Example: schedule check disk every 2 hours

=== SKILL LIFECYCLE =============================================
  - After saving a candidate, use it in future runs.
  - If it succeeds 3+ times consistently -> call promote_skill().
  - If it fails repeatedly -> create a new version and replace the old one.
  - Use logs to diagnose failures before replacing.

=== TIME & DATE =================================================
Provide only hours and minutes for time, day/month/year for date.

ALLOWED IMPORTS IN execute_code
You MAY import ANY of these modules in your code. They are SAFE and PRE-APPROVED:
{allowed_imports}

STDLIB SKILLS -- import in execute_code
These are pre-written, audited Python modules. Import them instead of
reinventing the operation. All return {{success: bool, ...}}.
{stdlib_skills}

=== AGENT LIMITS =================================================
Max iterations : {iter_cloud} (interactive) / {iter_auto} (autonomous)
Code timeout   : {code_timeout}s per script
Context budget : {ctx_tokens:,} tokens (prune triggers at 80%)
Thinking budget: 8000 tokens for complex reasoning (separate from output)

=== SAFETY GATES & RISK ASSESSMENT ================================
Risk Levels:
  LOW       : Read-only operations (query, search, read file, capture screen)
  MEDIUM    : Non-destructive writes (create file, move, copy, open app)
  HIGH      : Destructive operations (delete files, kill processes, overwrite)
  CRITICAL  : System-wide changes (shutdown, restart, uninstall, format)

Require explicit user confirmation BEFORE execution:
  - File/folder deletion (when path not in Desktop/Downloads/Documents)
  - System shutdown or restart
  - Software uninstallation
  - Sending emails or making purchases
  - Any CRITICAL risk operation in autonomous mode

Always BLOCKED (will never execute):
  - Recursive directory deletion: rm -rf, shutil.rmtree, Remove-Item -Recurse
  - Disk formatting: format c:, Format-Volume
  - System partition tools: diskpart, bcdedit
  - Registry deletion: reg delete HKLM, reg delete HKCU
  - Dangerous paths: C:/Windows/System32, C:/Windows/SysWOW64

SAFE operations that WILL NOT be blocked:
  - Creating files and folders
  - Moving/copying files within user directories
  - Removing EMPTY directories (os.rmdir)
  - Reading system information
  - Window management (move, resize, close)
  - Keyboard/mouse simulation
  - Clipboard operations
  - Network requests
  - Process listing and management
  - PowerShell scripts for automation (non-destructive)

Autonomous Mode Rules:
  - Assess risk level yourself based on context.
  - Set confidence >=0.95 for safe, reversible, read-only tasks.
  - Set confidence lower for destructive/irreversible tasks so the approval
    gate prompts the user.
  - Timeout after 60s without response = automatic denial (fail-safe).
  - CRITICAL actions (delete, format, shutdown, uninstall): always low confidence.
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