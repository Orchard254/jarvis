"""Verify TOOL_SCHEMAS / TOOL_REGISTRY consistency."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import TOOL_REGISTRY, TOOL_SCHEMAS


def test_tool_schemas_loaded():
    assert len(TOOL_SCHEMAS) > 0


def test_tool_registry_loaded():
    assert len(TOOL_REGISTRY) > 0


def test_schemas_match_registry():
    schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    registry_names = set(TOOL_REGISTRY.keys())
    missing_impl = schema_names - registry_names
    missing_schema = registry_names - schema_names
    assert not missing_impl, f"Schemas without impl: {missing_impl}"
    assert not missing_schema, f"Impl without schema: {missing_schema}"
