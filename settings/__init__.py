"""
JARVIS — Single Source of Truth Configuration
All paths, thresholds, timeouts, model names, and caps.
Loaded from .env with sensible defaults.

This package re-exports everything from domain-specific submodules so that
existing ``from settings import X`` imports continue to work unchanged.
"""

# Helpers (public so consumers can use them too)
from settings._helpers import (
    BASE_DIR,
    get_env_str,
    get_env_int,
    get_env_float,
    get_env_bool,
    load_dotenv,
)

# Domain modules — order matters when submodules depend on each other
from settings.paths import *
from settings.llm import *
from settings.safety import *
from settings.voice import *
from settings.autonomous import *
from settings.integrations import *
from settings.log_cfg import *

# ── Explicit re-exports for tools like pyright/mypy ───────────────────────────
# NOTE: __all__ is computed from submodule names so it never drifts.
# If you add a new setting, just define it in the appropriate submodule.
_SUBMODULES = ["paths", "llm", "safety", "voice", "autonomous", "integrations", "log_cfg"]
_HIDDEN_PREFIXES = ("_",)
_HIDDEN_NAMES = {"load_dotenv"}  # not useful for consumers

def _collect_exports():
    names: set[str] = set()
    for _mod_name in _SUBMODULES:
        _mod = __import__(f"settings.{_mod_name}", fromlist=[""])
        for _name in dir(_mod):
            if _name.startswith(_HIDDEN_PREFIXES):
                continue
            names.add(_name)
    # Add explicit helper names
    names.update(["BASE_DIR", "get_env_str", "get_env_int", "get_env_float", "get_env_bool"])
    names.difference_update(_HIDDEN_NAMES)
    return sorted(names)

__all__ = _collect_exports()
del _SUBMODULES, _HIDDEN_PREFIXES, _HIDDEN_NAMES, _collect_exports
