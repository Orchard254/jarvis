"""
Smoke-test: verify every schema in TOOL_SCHEMAS round-trips cleanly through
JSON (required for Ollama/OpenAI API calls) and that the count is exactly 9.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from tools import TOOL_SCHEMAS

print(f"Testing {len(TOOL_SCHEMAS)} schemas...")

try:
    serialised = json.dumps(TOOL_SCHEMAS)
    roundtrip = json.loads(serialised)
    assert len(roundtrip) == len(TOOL_SCHEMAS)
    print("✅ JSON serialisation OK")
except Exception as e:
    print(f"❌ JSON error: {e}")
    sys.exit(1)

assert len(TOOL_SCHEMAS) == 9, f"Expected 9 schemas, got {len(TOOL_SCHEMAS)}"
print(f"✅ Schema count: {len(TOOL_SCHEMAS)}")

for schema in TOOL_SCHEMAS:
    name = schema["function"]["name"]
    assert "description" in schema["function"], f"{name} missing description"
    assert "parameters" in schema["function"], f"{name} missing parameters"
    print(f"  ✅ {name}")

print("\n✅ All schema checks passed")
