"""
Smoke-test: verify TOOL_SCHEMAS is importable, has exactly 9 tools,
and contains no retired tools (open_app, install_app).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from tools import TOOL_REGISTRY, TOOL_SCHEMAS

EXPECTED = {
    "execute_code",
    "capture_screen",
    "read_pc_state",
    "control_window",
    "control_input",
    "query_pc_index",
    "read_file",
    "write_file",
    "notify_user",
}
RETIRED = {"open_app", "install_app"}

schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
registry_names = set(TOOL_REGISTRY.keys())

assert schema_names == EXPECTED, f"Schema mismatch: {schema_names ^ EXPECTED}"
assert registry_names == EXPECTED, f"Registry mismatch: {registry_names ^ EXPECTED}"
assert not (schema_names & RETIRED), (
    f"Retired tools still present: {schema_names & RETIRED}"
)
assert len(TOOL_SCHEMAS) == 9, f"Expected 9 schemas, got {len(TOOL_SCHEMAS)}"

print(f"✅ TOOL_SCHEMAS: {len(TOOL_SCHEMAS)} tools — {sorted(schema_names)}")
print("✅ TOOL_REGISTRY matches TOOL_SCHEMAS")
print("✅ No retired tools present")
