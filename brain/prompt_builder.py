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

try:
    import yaml
except ImportError:
    yaml = None

from settings import LLM_MODEL, MAX_CONTEXT_TOKENS
from tools import TOOL_SCHEMAS as _FULL_SCHEMAS, get_schemas_by_stage
from settings import TOOL_STAGE

# Apply stage filtering — expose only tools <= TOOL_STAGE
if TOOL_STAGE > 0:
    TOOL_SCHEMAS = get_schemas_by_stage(TOOL_STAGE)
else:
    TOOL_SCHEMAS = _FULL_SCHEMAS

# Register default agents so every prompt can reference them
from core.agent_registry import AgentRegistry, register_defaults
register_defaults()

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
                "disk_pct": f"{(1 - disk.free / disk.total) * 100:.0f}",
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





# ── Prompt cache ──────────────────────────────────────────────────────────────
_prompt_cache: dict[str, str] = {}
_prompt_mtimes: dict[str, float] = {}
_PROMPT_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts/ directory (mtime-cached). Assembles sections."""
    path = _PROMPT_DIR / f"{name}.yaml"
    mtime = path.stat().st_mtime if path.exists() else 0
    if name not in _prompt_cache or _prompt_mtimes.get(name) != mtime:
        try:
            with open(path, encoding="utf-8") as f:
                if yaml is None:
                    logger.warning("yaml library not available; reading raw prompt for %s", name)
                    # Return raw file content (unformatted) when yaml is missing
                    return f.read()
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.warning(f"prompt_builder: failed to load '{name}': {exc}")
            return f"[{name} prompt unavailable]"
        sections = data.get("sections", {})
        _prompt_cache[name] = "\n\n".join(
            v.strip() for v in sections.values() if v.strip()
        )
        _prompt_mtimes[name] = mtime
    return _prompt_cache[name]




_prompt_cache_str: str = ""
_prompt_cache_ts: float = 0.0
_PROMPT_CACHE_TTL = 60.0


def build_system_prompt() -> str:
    """
    Build the full situational-awareness system prompt.
    Hardware stats are re-read from psutil every 60 s (cached otherwise).
    Result is cached with TTL to avoid re-formatting on every LLM call.
    """
    global _prompt_cache_str, _prompt_cache_ts
    if _prompt_cache_str and (_time.time() - _prompt_cache_ts) < _PROMPT_CACHE_TTL:
        return _prompt_cache_str

    hw = _hw()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ram_flag = "  ⚠ LOW — avoid memory-heavy ops" if hw["ram_warn"] else ""
    disk_flag = "  ⚠ LOW — avoid large downloads" if hw["disk_warn"] else ""

    info = AgentRegistry.get_info()

    prompt_template = _load_prompt("jarvis")
    try:
        _prompt_cache_str = prompt_template.format(
            model=LLM_MODEL,
            ctx_k=MAX_CONTEXT_TOKENS // 1000,
            now=now,
            hostname=socket.gethostname(),
            user=os.environ.get("USERNAME", os.environ.get("USER", "user")),
            os_name=platform.system(),
            os_ver=platform.version()[:30],
            desktop=str(Path.home() / "Desktop"),
            downloads=str(Path.home() / "Downloads"),
            documents=str(Path.home() / "Documents"),
            ram_flag=ram_flag,
            disk_flag=disk_flag,
            cpu=hw["cpu"],
            ram_gb=hw["ram_gb"],
            ram_free=hw["ram_free"],
            ram_pct=hw["ram_pct"],
            disk_gb=hw["disk_gb"],
            disk_free=hw["disk_free"],
            disk_pct=hw["disk_pct"],
            tool_count=info["tool_count"],
            tool_domains=info["tool_domains"],
            agent_count=info["agent_count"],
            agent_info=info["agent_info"],
        )
        _prompt_cache_ts = _time.time()
        return _prompt_cache_str
    except Exception as exc:
        logger.warning(f"build_system_prompt formatting failed: {exc}")
        return prompt_template


def build_executor_prompt() -> str:
    info = AgentRegistry.get_info()
    prompt_template = _load_prompt("executor")
    tool_list = "\n".join(
        f"  {s['function']['name']}: {s['function'].get('description', '').split('.')[0]}"
        for s in TOOL_SCHEMAS
    )
    try:
        return prompt_template.format(
            tools=tool_list,
            tool_count=info["tool_count"],
            agent_info=info["agent_info"],
        )
    except Exception as exc:
        logger.warning(f"build_executor_prompt formatting failed: {exc}")
        return prompt_template






