"""
Smoke-test: verify TOOL_SCHEMAS is importable, has exactly 14 tools,
and contains no retired/collapsed tools.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from tools import TOOL_REGISTRY, TOOL_SCHEMAS

EXPECTED = {
    "execute_code",
    "capture_screen",
    "read_pc_state",
    "browser",
    "find_on_screen",
    "vision_query",
    "time_calendar",
    "memory",
    "speak",
    "schedule",
    "ask_user",
    "listen",
    "watch_screen",
    "send_message",
}
RETIRED = {"open_app", "install_app", "control_window", "control_input", "read_file",
           "write_file", "notify_user", "network_check", "query_pc_index"}

schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
registry_names = set(TOOL_REGISTRY.keys())

assert schema_names == EXPECTED, f"Schema mismatch: {schema_names ^ EXPECTED}"
assert registry_names == EXPECTED, f"Registry mismatch: {registry_names ^ EXPECTED}"
assert not (schema_names & RETIRED), (
    f"Retired tools still present: {schema_names & RETIRED}"
)
assert len(TOOL_SCHEMAS) == 14, f"Expected 14 schemas, got {len(TOOL_SCHEMAS)}"

print(f"[OK] TOOL_SCHEMAS: {len(TOOL_SCHEMAS)} tools — {sorted(schema_names)}")
print("[OK] TOOL_REGISTRY matches TOOL_SCHEMAS")
print("[OK] No retired tools present")
