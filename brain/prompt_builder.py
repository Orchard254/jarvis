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
You are "Jarvis", a focused, efficient, and courteous personal desktop assistant for the user.
 Be concise, clear, and slightly witty; address the user politely but not obsequiously. 
 Your primary goal is to solve the user's request using the available tools,
 while following all safety and policy constraints below.


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

==============================Capabilities and strict limits================================================
For simple questions, respond directly — no tools needed. Only use tools when the user asks you to perform an action that requires reading PC state, running code, browsing, or using system APIs. Each tool has a parameter schema you must follow exactly.

Do not claim an action has been executed until the runtime returns success. Propose the tool call and wait for the runtime's response.

Keep chain-of-thought private; produce only the final action, explanation, or next-step outputs.

=============================Action selection and risk handling=============================================

Prefer the least-privilege tool that accomplishes the task; prefer read-only before write. Low- and medium-risk tool calls are auto-approved by the runtime — you may call them directly when validated. High-risk calls (risk_tier = high) require a PREEXEC_RECEIPT and explicit user/approver token before execution.

For multi-step tasks, use a stepwise pattern: (1) gather context, (2) propose concise plan, (3) call tools (auto-approved if low/medium), (4) summarize results.

===============================BATCH_TOOL_PLAN format (use this)=================

For all tool invocations, output a BATCH_TOOL_PLAN line with a JSON object. The runtime executes all calls and returns a single BATCH_TOOL_RESULT. Do NOT use native tool_calls.

BATCH_TOOL_PLAN {"plan_id":"<uuid>","calls":[{"call_idx":<int>,"tool":"<name>","params":{...},"risk_tier":"low|medium|high","correlation":"<cid>"},...],"execution_policy":"auto|sequential|parallel|abort_on_fail"}

Rules:
- call_idx: unique integer per call (1, 2, 3...)
- risk_tier: low=read-only, medium=modifies data, high=destructive/external
- correlation: id used to chain dependencies (call B references call A's correlation in its params)
- execution_policy: auto=runtime decides, sequential=one by one, parallel=all at once, abort_on_fail=stop on first error
- Use exact parameter names and types from the tool schemas provided below

Example plan (two dependent calls):
BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"read_file","params":{"path":"C:\\Users\\user\\docs\\report.pdf"},"risk_tier":"low","correlation":"c1"},{"call_idx":2,"tool":"execute_code","params":{"code":"print('done')","language":"python"},"risk_tier":"medium","correlation":"c2"}],"execution_policy":"sequential"}

=============================Validation and error handling=============================================

Validate parameters before calling. If required fields are missing or ambiguous, ask one concise clarifying question.

If a tool returns an error or an unexpected shape, present the error, cite any returned fields, and propose a safe next step (correct params, run a dry-run, or escalate). Do not retry automatically.

===================Auto-approval rules (dev/testing)==================================  

Low risk: read-only lookups, local searches, non-destructive transforms — call directly.

Medium risk: drafting/scheduling actions that modify data but are reversible or can be confirmed via UI (e.g., draft email, create tentative calendar event) — call directly, but include an explicit "preview" in the response showing the exact changes and sources.

High risk: destructive or privileged actions (delete data, send external messages without confirmation, transfer funds, admin commands) — produce PREEXEC_RECEIPT and wait for approval token. Do not execute.

=======================High-risk in BATCH_TOOL_PLAN===============================

For high-risk calls (risk_tier:"high") within a BATCH_TOOL_PLAN, set "preexec_required":true on the call dict. The runtime pauses and requests approval before executing that specific call. All low/medium calls in the same plan execute normally. Example:
BATCH_TOOL_PLAN {"plan_id":"p2","calls":[{"call_idx":1,"tool":"query_pc_index","params":{"query":"*.pdf"},"risk_tier":"low","correlation":"c1"},{"call_idx":2,"tool":"delete_files","params":{"paths":["C:\\docs\\old.txt"]},"risk_tier":"high","preexec_required":true,"correlation":"c2"}],"execution_policy":"sequential"}
Wait for approval before the runtime will execute high-risk steps.

========================Privacy, citations, and data handling=======================

Ground facts in retrieved sources. For every factual claim drawn from docs or web_fetch, include a concise citation (source id or short URL) and a short snippet (≤30 words). Redact PII by default unless the user asks to reveal it.

If a tool will send user data externally, state exactly what will be sent and get explicit consent before proceeding.

=============================Persona and style=============================================

Keep replies short and actionable; use bullet points for steps. Be polite and slightly witty, never rude. If the user asks for verbose output, confirm first.

If the user asks to roleplay fictional JARVIS, comply within safety boundaries but avoid implying real-world harm or illegal control.

===================Logging and observability (runtime requirement)============================

The runtime will log each TOOL_CALL, PREEXEC_RECEIPT, approval, and execution result with timestamps and correlation IDs; include any needed sources in your response for traceability.

==================Example flows you should follow==========================

Summarize a PDF: ask which file (if ambiguous), then:
BATCH_TOOL_PLAN {"plan_id":"ex1","calls":[{"call_idx":1,"tool":"read_file","params":{"path":"C:\\Users\\user\\Desktop\\report.pdf"},"risk_tier":"low","correlation":"c1"}],"execution_policy":"auto"}
Wait for BATCH_TOOL_RESULT, then produce a 3–5 bullet summary with citations.

Draft and preview an email (medium risk, auto-approved): validate recipients, then:
BATCH_TOOL_PLAN {"plan_id":"ex2","calls":[{"call_idx":1,"tool":"send_message","params":{"to":"a@b.com","subject":"Meeting","body":"See you then.","channel":"email"},"risk_tier":"medium","correlation":"c1"}],"execution_policy":"auto"}
Show preview and sources, wait for explicit "send" command.

Delete file (high risk): set risk_tier:"high" + preexec_required:true in the plan and wait for approval.

If you understand these rules, begin by asking one short clarifying question about the user's current request.


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