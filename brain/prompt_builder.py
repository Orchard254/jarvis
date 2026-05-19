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

import yaml

from settings import (
    ALLOWED_IMPORTS,
    EXECUTE_CODE_TIMEOUT,
    ITERATION_CAPS,
    LLM_MODEL,
    LLM_TOOL_SCHEMA_LIMIT,
    LOG_FILE,
    MAX_CONTEXT_TOKENS,
)
from tools import TOOL_SCHEMAS as _FULL_SCHEMAS, get_schemas_by_stage
from skills.stdlib import STDLIB_MANIFEST
from settings import TOOL_STAGE

# Apply stage filtering — expose only tools <= TOOL_STAGE
if TOOL_STAGE > 0:
    TOOL_SCHEMAS = get_schemas_by_stage(TOOL_STAGE)
else:
    TOOL_SCHEMAS = _FULL_SCHEMAS

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

            battery = psutil.sensors_battery()
            battery_pct = round(battery.percent, 0) if battery else None
            battery_plugged = battery.power_plugged if battery else None
            battery_warn = battery_pct is not None and battery_pct < 20 and not battery_plugged

            hw = {
                "cpu": f"{cpu_p}-core / {cpu_l}-thread @ {freq_s}",
                "ram_gb": f"{ram.total / 1e9:.1f}",
                "ram_free": f"{ram.available / 1e9:.1f}",
                "ram_pct": f"{ram.percent:.0f}",
                "ram_warn": ram.percent > 80,
                "disk_gb": f"{disk.total / 1e9:.1f}",
                "disk_free": f"{disk.free / 1e9:.1f}",
                "disk_pct": f"{(1 - disk.free / disk.total) * 100:.0f}",
                "disk_warn": (disk.free / disk.total) < 0.15,
                "battery_pct": battery_pct,
                "battery_plugged": battery_plugged,
                "battery_warn": battery_warn,
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
                "battery_pct": None,
                "battery_plugged": None,
                "battery_warn": False,
            }

        _hw_cache = hw
        _hw_ts = _time.time()
        return hw





# ── Prompt cache ──────────────────────────────────────────────────────────────
_prompt_cache: dict[str, str] = {}
_PROMPT_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts/ directory (cached). Assembles sections."""
    if name not in _prompt_cache:
        path = _PROMPT_DIR / f"{name}.yaml"
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, FileNotFoundError) as exc:
            logger.warning(f"prompt_builder: failed to load '{name}': {exc}")
            return f"[{name} prompt unavailable]"
        sections = data.get("sections", {})
        _prompt_cache[name] = "\n\n".join(
            v.strip() for v in sections.values() if v.strip()
        )
    return _prompt_cache[name]


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
    battery_str = f"{hw['battery_pct']}%{' (plugged)' if hw['battery_plugged'] else ''}" if hw['battery_pct'] is not None else "N/A"
    battery_flag = "  ⚠ LOW — consider plugging in" if hw["battery_warn"] else ""

    tool_list = _build_tool_list()
    prompt_template = _load_prompt("jarvis")

    replacements = {
        "{model}": LLM_MODEL,
        "{ctx_k}": str(MAX_CONTEXT_TOKENS // 1000),
        "{now}": now,
        "{hostname}": socket.gethostname(),
        "{user}": os.environ.get("USERNAME", os.environ.get("USER", "user")),
        "{os_name}": platform.system(),
        "{os_ver}": platform.version()[:30],
        "{cpu}": hw["cpu"],
        "{ram_gb}": hw["ram_gb"],
        "{ram_free}": hw["ram_free"],
        "{ram_used_pct}": hw["ram_pct"],
        "{ram_flag}": ram_flag,
        "{disk_gb}": hw["disk_gb"],
        "{disk_free}": hw["disk_free"],
        "{disk_pct}": hw["disk_pct"],
        "{disk_flag}": disk_flag,
        "{battery}": battery_str,
        "{battery_flag}": battery_flag,
        "{desktop}": str(home / "Desktop"),
        "{downloads}": str(home / "Downloads"),
        "{documents}": str(home / "Documents"),
        "{tool_list}": tool_list,
    }
    for key, value in replacements.items():
        prompt_template = prompt_template.replace(key, value)
    return prompt_template


def _build_tool_list() -> str:
    """Compact tool catalog: name + one-line description for Jarvis."""
    lines = []
    for s in TOOL_SCHEMAS:
        fn = s.get("function", {})
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        # First sentence only
        desc = desc.split(".")[0].strip()
        lines.append(f"  {name}: {desc}")
    return "\n".join(lines)


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


def build_state_context(state: dict | None) -> str:
    """Format a SystemState snapshot as a compact context block for the LLM."""
    if not state:
        return ""
    parts = []
    win = state.get("active_window", "")
    mouse = state.get("mouse_position", (0, 0))
    cpu = state.get("cpu_percent", 0)
    ram = state.get("ram_percent", 0)
    disk = state.get("disk_percent", 0)
    bat = state.get("battery_percent")
    act = state.get("last_action", "")
    ts = state.get("timestamp", "")

    if win:
        parts.append(f"Active window: {win}")
    parts.append(f"Mouse: ({mouse[0]}, {mouse[1]})")
    parts.append(f"CPU: {cpu}% | RAM: {ram}% | Disk: {disk}%")
    if bat is not None:
        plugged = state.get("battery_plugged")
        parts.append(f"Battery: {bat}%{' (plugged)' if plugged else ''}")
    if act:
        parts.append(f"Last action: {act} @ {ts[:19]}")
    return " | ".join(parts)


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