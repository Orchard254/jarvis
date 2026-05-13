"""
Custom tool drop-in directory.

Place Python files here that define a ``register()`` function returning
``(name: str, fn: callable, schema: dict)``.  On startup JARVIS auto-discovers
and registers them alongside built-in tools.

Example ``my_tool.py``::

    def my_tool(query: str) -> dict:
        return {"success": True, "result": f"You asked: {query}"}

    def register():
        return (
            "my_tool",
            my_tool,
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "My custom tool.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
        )

No need to edit any other file -- just drop in and restart.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CUSTOM_TOOLS: dict[str, callable] = {}
_CUSTOM_SCHEMAS: list[dict] = []
_INITIALIZED = False


def _discover() -> tuple[dict[str, callable], list[dict]]:
    registry: dict[str, callable] = {}
    schemas: list[dict] = []

    here = Path(__file__).parent
    for py_file in sorted(here.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        name = py_file.stem
        try:
            spec = importlib.util.spec_from_file_location(name, py_file)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "register"):
                logger.debug(f"custom.tools: {name} has no register() -- skipped")
                continue
            reg_result = mod.register()
            if not reg_result or len(reg_result) != 3:
                logger.warning(
                    f"custom.tools: {name}.register() must return (name, fn, schema)"
                )
                continue
            tool_name, tool_fn, tool_schema = reg_result
            if tool_name in registry:
                logger.warning(
                    f"custom.tools: duplicate tool name '{tool_name}' in {name}.py"
                )
                continue
            registry[tool_name] = tool_fn
            schemas.append(tool_schema)
            logger.info(f"custom.tools: registered '{tool_name}' from {name}.py")
        except Exception as exc:
            logger.warning(f"custom.tools: failed to load {name}.py -- {exc}")

    return registry, schemas


def _ensure_discovered():
    global _CUSTOM_TOOLS, _CUSTOM_SCHEMAS, _INITIALIZED
    if not _INITIALIZED:
        _CUSTOM_TOOLS, _CUSTOM_SCHEMAS = _discover()
        _INITIALIZED = True


def get_custom_tools() -> dict[str, callable]:
    _ensure_discovered()
    return dict(_CUSTOM_TOOLS)


def get_custom_schemas() -> list[dict]:
    _ensure_discovered()
    return list(_CUSTOM_SCHEMAS)
