"""
Smoke-test: verify TOOL_SCHEMAS is importable, has exactly 10 tools,
and contains no retired/collapsed tools.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from tools import TOOL_REGISTRY, TOOL_SCHEMAS

EXPECTED = {
    "execute_code",
    "query_pc_index",
    "vision_query",
    "browser",
    "speak",
    "listen",
    "send_message",
    "schedule",
    "time_calendar",
    "memory",
}
RETIRED = {"open_app", "install_app", "control_window", "control_input", "read_file",
           "write_file", "notify_user", "network_check",
           "file_ops", "process_manager", "system_settings", "clipboard",
           "search_web", "fetch_url", "capture_screen", "read_pc_state",
           "find_on_screen", "watch_screen", "ask_user"}

schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
registry_names = set(TOOL_REGISTRY.keys())

assert schema_names == EXPECTED, f"Schema mismatch: {schema_names ^ EXPECTED}"
assert registry_names == EXPECTED, f"Registry mismatch: {registry_names ^ EXPECTED}"
assert not (schema_names & RETIRED), (
    f"Retired tools still present: {schema_names & RETIRED}"
)
assert len(TOOL_SCHEMAS) == 10, f"Expected 10 schemas, got {len(TOOL_SCHEMAS)}"

print(f"[OK] TOOL_SCHEMAS: {len(TOOL_SCHEMAS)} tools — {sorted(schema_names)}")
print("[OK] TOOL_REGISTRY matches TOOL_SCHEMAS")
print("[OK] No retired tools present")
