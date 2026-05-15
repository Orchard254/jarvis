"""
JARVIS Tool Registry.

Tools that require non-trivial integration code the LLM would struggle to
write correctly inline via execute_code.  Simple operations (screenshots,
window control, file ops, etc.) the LLM can do directly with Python/PowerShell.

Schemas are loaded from schemas.json — the single source of truth for tool
definitions.  Python implementations are imported below and registered in
TOOL_REGISTRY.
"""

import json
from pathlib import Path

# ── Load tool schemas from JSON registry ──────────────────────────────────────
_SCHEMAS_PATH = Path(__file__).parent / "schemas.json"
with open(_SCHEMAS_PATH, encoding="utf-8") as f:
    _SCHEMA_REGISTRY = json.load(f)

# Strip the $schema key if present
_SCHEMA_REGISTRY.pop("$schema", None)

TOOL_SCHEMAS = []
TOOL_STAGES: dict[str, int] = {}
for name, data in _SCHEMA_REGISTRY.items():
    TOOL_STAGES[name] = data.get("stage", 99)
    TOOL_SCHEMAS.append({
        "type": "function",
        "function": {
            "name": name,
            "description": data.get("description", ""),
            "parameters": data.get("input", {"type": "object", "properties": {}}),
        },
    })

# Stage-grouped schema accessors for graduated tool exposure
_STAGE_SCHEMA_CACHE: dict[int, list[dict]] = {}

def get_schemas_by_stage(max_stage: int) -> list[dict]:
    """Return TOOL_SCHEMAS for tools up to and including *max_stage*."""
    if max_stage in _STAGE_SCHEMA_CACHE:
        return _STAGE_SCHEMA_CACHE[max_stage]
    result = [
        s for s in TOOL_SCHEMAS
        if TOOL_STAGES.get(s["function"]["name"], 99) <= max_stage
    ]
    _STAGE_SCHEMA_CACHE[max_stage] = result
    return result

def get_tools_by_stage(max_stage: int) -> tuple[list[dict], dict]:
    """Return (schemas, registry) filtered to tools <= *max_stage*."""
    schemas = get_schemas_by_stage(max_stage)
    names = {s["function"]["name"] for s in schemas}
    registry = {k: v for k, v in TOOL_REGISTRY.items() if k in names}
    return schemas, registry


# ── Import Python implementations ─────────────────────────────────────────────
from tools import adapters
from tools.system import execute_code


# Build TOOL_REGISTRY from schemas.json — each tool name maps to its adapter function
TOOL_REGISTRY = {}
for name in _SCHEMA_REGISTRY:
    if hasattr(adapters, name):
        TOOL_REGISTRY[name] = getattr(adapters, name)
    elif name == "execute_code":
        TOOL_REGISTRY[name] = execute_code


# ── Merge custom drop-in tools ───────────────────────────────────────────────
from tools.custom import get_custom_schemas, get_custom_tools

_CUSTOM_REGISTRY = get_custom_tools()
_CUSTOM_SCHEMAS = get_custom_schemas()

if _CUSTOM_REGISTRY:
    TOOL_REGISTRY.update(_CUSTOM_REGISTRY)
    TOOL_SCHEMAS.extend(_CUSTOM_SCHEMAS)
