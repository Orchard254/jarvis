"""
Smoke-test: verify every schema in TOOL_SCHEMAS round-trips cleanly through
JSON (required for Ollama/OpenAI API calls) and has required fields.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from tools import TOOL_SCHEMAS

count = len(TOOL_SCHEMAS)
print(f"Testing {count} schemas...")

try:
    serialised = json.dumps(TOOL_SCHEMAS)
    roundtrip = json.loads(serialised)
    assert len(roundtrip) == count
    print("[OK] JSON serialisation OK")
except Exception as e:
    print(f"[FAIL] JSON error: {e}")
    sys.exit(1)

print(f"[OK] Schema count: {count}")

for schema in TOOL_SCHEMAS:
    name = schema["function"]["name"]
    assert "description" in schema["function"], f"{name} missing description"
    assert "parameters" in schema["function"], f"{name} missing parameters"
    print(f"  [OK] {name}")

print("\n[OK] All schema checks passed")
