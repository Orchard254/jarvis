#!/usr/bin/env python3
"""
Test script to verify dynamic scripting integration with JARVIS.
This tests the execute_dynamic_script tool end-to-end.
"""

from pc_control import execute_dynamic_script
from control_plane import validate_tool_call

def test_basic_script():
    """Test basic script execution"""
    print("=" * 60)
    print("TEST 1: Basic Script Execution")
    print("=" * 60)
    
    script = '''
import os
print("Current directory:", os.getcwd())
files = os.listdir('.')
print(f"Found {len(files)} files")
for f in files[:5]:
    print(f"  - {f}")
'''
    
    result = execute_dynamic_script(script, "List current files", timeout=10)
    
    assert result["success"], f"Script failed: {result['error']}"
    assert "Current directory" in result["output"]
    print("✅ PASSED: Basic script execution works\n")
    return True

def test_validation_safe():
    """Test validation for safe script"""
    print("=" * 60)
    print("TEST 2: Validation - Safe Script")
    print("=" * 60)
    
    params = {
        'script': 'print("hello")',
        'description': 'Test script',
        'timeout': 10
    }
    
    is_valid, error_msg = validate_tool_call('execute_dynamic_script', params)
    
    assert is_valid, f"Safe script was rejected: {error_msg}"
    print("✅ PASSED: Safe scripts pass validation\n")
    return True

def test_validation_dangerous():
    """Test validation blocks dangerous patterns"""
    print("=" * 60)
    print("TEST 3: Validation - Dangerous Patterns Blocked")
    print("=" * 60)
    
    dangerous_scripts = [
        ('import socket; s = socket.socket()', 'socket'),
        ('import requests; requests.get("http://evil.com")', 'requests'),
        ('eval("os.system(\'rm -rf /\')")', 'eval'),
        ('exec("import os; os.remove(\'/etc/passwd\')")', 'exec'),
    ]
    
    for script, pattern_name in dangerous_scripts:
        params = {
            'script': script,
            'description': 'Malicious script',
            'timeout': 10
        }
        
        is_valid, error_msg = validate_tool_call('execute_dynamic_script', params)
        
        assert not is_valid, f"Dangerous script ({pattern_name}) was allowed!"
        print(f"  ✅ Blocked {pattern_name}: {error_msg[:60]}...")
    
    print("✅ PASSED: All dangerous patterns blocked\n")
    return True

def test_file_operations():
    """Test file creation and reading"""
    print("=" * 60)
    print("TEST 4: File Operations")
    print("=" * 60)
    
    # Create a test file
    create_script = '''
import os
test_file = "test_dynamic_output.txt"
with open(test_file, "w") as f:
    f.write("Dynamic scripting works!\\n")
    f.write("Line 2\\n")
print(f"Created {test_file}")
'''
    
    result = execute_dynamic_script(create_script, "Create test file", timeout=10)
    assert result["success"], f"File creation failed: {result['error']}"
    print("  ✅ File created successfully")
    
    # Read it back
    read_script = '''
with open("test_dynamic_output.txt", "r") as f:
    content = f.read()
print("File content:")
print(content)
'''
    
    result = execute_dynamic_script(read_script, "Read test file", timeout=10)
    assert result["success"], f"File read failed: {result['error']}"
    assert "Dynamic scripting works!" in result["output"]
    print("  ✅ File read successfully")
    
    # Cleanup
    cleanup_script = '''
import os
os.remove("test_dynamic_output.txt")
print("Cleanup complete")
'''
    execute_dynamic_script(cleanup_script, "Cleanup", timeout=10)
    
    print("✅ PASSED: File operations work correctly\n")
    return True

def test_timeout():
    """Test timeout protection"""
    print("=" * 60)
    print("TEST 5: Timeout Protection")
    print("=" * 60)
    
    # Script that sleeps too long
    slow_script = '''
import time
print("Starting...")
time.sleep(10)
print("Done")
'''
    
    result = execute_dynamic_script(slow_script, "Slow script", timeout=2)
    
    assert not result["success"], "Slow script should have timed out"
    assert "timed out" in result["error"].lower()
    print(f"  ✅ Timeout enforced: {result['error'][:50]}")
    print("✅ PASSED: Timeout protection works\n")
    return True

def main():
    print("\n" + "=" * 60)
    print("DYNAMIC SCRIPTING INTEGRATION TESTS")
    print("=" * 60 + "\n")
    
    tests = [
        ("Basic Execution", test_basic_script),
        ("Validation - Safe", test_validation_safe),
        ("Validation - Dangerous", test_validation_dangerous),
        ("File Operations", test_file_operations),
        ("Timeout Protection", test_timeout),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {name} - {e}\n")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {name} - {e}\n")
            failed += 1
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Dynamic scripting is ready for production.\n")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Review before deploying.\n")
        return 1

if __name__ == "__main__":
    exit(main())
