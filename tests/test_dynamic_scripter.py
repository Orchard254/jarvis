"""
TEST SUITE FOR DYNAMIC SCRIPTER
-------------------------------
Verifies that the LLM can generate working code for tasks 
without relying on hardcoded tools.
"""

import sys
from pathlib import Path

# Add parent directory (workspace root) to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dynamic_scripter import DynamicScripter
# Removed unused import that was causing errors

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

def test_dynamic_scripter():
    print("="*60)
    print("DYNAMIC SCRIPTER TEST SUITE")
    print("="*60)
    
    llm = MockLLM()
    scripter = DynamicScripter(llm)
    
    tests = [
        {
            "name": "List Files in Directory",
            "goal": "List all files in the current directory and count them",
            "expected_success": True
        },
        {
            "name": "Launch Notepad",
            "goal": "Open the Notepad application on Windows",
            "expected_success": True
        },
        {
            "name": "Check System Resources",
            "goal": "Check current CPU usage and report if it's high",
            "expected_success": True
        }
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        print(f"\n{'='*60}")
        print(f"TEST: {test['name']}")
        print(f"GOAL: {test['goal']}")
        print(f"{'='*60}")
        
        result = scripter.run_task(test['goal'])
        
        if result['success'] == test['expected_success']:
            print(f"✅ PASSED")
            passed += 1
        else:
            print(f"❌ FAILED")
            print(f"Error: {result.get('error', 'Unknown error')}")
            failed += 1
            
        # Show generated code for debugging
        if 'code' in result:
            print("\n--- Generated Code ---")
            print(result['code'][:500] + "..." if len(result['code']) > 500 else result['code'])
            print("---------------------\n")
    
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} Passed, {failed} Failed")
    print(f"{'='*60}")
    
    return failed == 0

if __name__ == "__main__":
    success = test_dynamic_scripter()
    sys.exit(0 if success else 1)
