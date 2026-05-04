"""
TEST SUITE FOR DYNAMIC SCRIPTING VIA RUN_PYTHON TOOL
----------------------------------------------------
Verifies that Python code can be executed dynamically
using the jarvis.tools.scripts.runner module.
"""

import sys
from pathlib import Path

# Try to import the tool - skip tests if not available
try:
    from jarvis.tools.scripts.runner import RunPythonTool
    MODULES_AVAILABLE = True
except ImportError as e:
    MODULES_AVAILABLE = False
    print(f"Warning: Required modules not available: {e}")


class MockLLM:
    """Mock LLM for testing without hitting API"""

    def chat(self, messages, temperature=0.2):
        goal = ""
        for msg in messages:
            if "USER GOAL:" in msg["content"]:
                goal = msg["content"].split("USER GOAL:")[1].split("WRITE THE CODE")[0].strip()
                break

        # Simulate LLM responses for specific goals
        if "list files" in goal.lower():
            return """
import os
files = os.listdir('.')
for f in files:
    print(f"Found: {f}")
print(f"Total files: {len(files)}")
"""
        elif "notepad" in goal.lower():
            return """
import subprocess
import sys

# Cross-platform text editor launch
try:
    if sys.platform == 'win32':
        subprocess.run(["notepad.exe"], check=True)
    elif sys.platform == 'darwin':
        subprocess.run(["open", "-a", "TextEdit"], check=True)
    else:
        # Linux - try common editors
        for editor in ["gedit", "kate", "mousepad", "xed"]:
            try:
                subprocess.run([editor], check=True)
                break
            except FileNotFoundError:
                continue
    print("Text editor launched successfully")
except Exception as e:
    print(f"Note: Could not launch GUI editor (expected in headless environment): {e}")
    print("Task completed in simulation mode")
"""
        elif "cpu" in goal.lower():
            return """
import psutil
cpu = psutil.cpu_percent(interval=1)
print(f"Current CPU Usage: {cpu}%")
if cpu > 50:
    print("Warning: High CPU usage!")
else:
    print("CPU usage is normal.")
"""
        else:
            return """
print("Task completed successfully")
"""


def test_run_python_tool():
    """Test the RunPythonTool directly"""
    if not MODULES_AVAILABLE:
        print("SKIPPED: Required modules not available")
        return True
        
    print("=" * 60)
    print("RUN_PYTHON TOOL TEST SUITE")
    print("=" * 60)

    tool = RunPythonTool()

    tests = [
        {
            "name": "List Files in Directory",
            "code": """
import os
files = os.listdir('.')
for f in files[:5]:
    print(f"Found: {f}")
print(f"Total files shown: {min(5, len(files))}")
""",
            "expected_success": True,
            "expected_output": "Found:"
        },
        {
            "name": "Simple Arithmetic",
            "code": """
result = 2 + 2
print(f"2 + 2 = {result}")
""",
            "expected_success": True,
            "expected_output": "2 + 2 = 4"
        },
        {
            "name": "System Info",
            "code": """
import platform
print(f"Python version: {platform.python_version()}")
print(f"System: {platform.system()}")
""",
            "expected_success": True,
            "expected_output": "Python version:"
        }
    ]

    passed = 0
    failed = 0

    for test in tests:
        print(f"\n{'='*60}")
        print(f"TEST: {test['name']}")
        print(f"{'='*60}")

        result = tool.execute(code=test['code'], timeout=10)

        if result.success == test['expected_success']:
            if test.get('expected_output') and test['expected_output'] not in result.output:
                print(f"❌ FAILED - Expected output not found")
                print(f"Expected to contain: {test['expected_output']}")
                print(f"Got: {result.output[:200]}")
                failed += 1
            else:
                print(f"✅ PASSED")
                passed += 1
        else:
            print(f"❌ FAILED")
            print(f"Error: {result.error}")
            failed += 1

        # Show output for debugging
        if result.output:
            print(f"\n--- Output ---")
            print(result.output[:300] + "..." if len(result.output) > 300 else result.output)
            print("--------------\n")

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} Passed, {failed} Failed")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = test_run_python_tool()
    sys.exit(0 if success else 1)
