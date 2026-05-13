"""
Smoke-test: verify TOOL_SCHEMAS and TOOL_REGISTRY are consistent,
and every schema has the required fields.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from tools import TOOL_REGISTRY, TOOL_SCHEMAS

schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
registry_names = set(TOOL_REGISTRY.keys())

# Every schema must have a matching registry entry
for name in schema_names:
    assert name in registry_names, f"Schema '{name}' missing from TOOL_REGISTRY"

# Every registry entry must have a matching schema
for name in registry_names:
    assert name in schema_names, f"Registry '{name}' missing from TOOL_SCHEMAS"

# All schemas must have required fields
for schema in TOOL_SCHEMAS:
    name = schema["function"]["name"]
    assert "description" in schema["function"], f"{name} missing description"
    assert "parameters" in schema["function"], f"{name} missing parameters"

print(f"[OK] TOOL_SCHEMAS: {len(TOOL_SCHEMAS)} tools — {sorted(schema_names)}")
print("[OK] TOOL_REGISTRY matches TOOL_SCHEMAS")
print("[OK] All schemas have valid structure")
