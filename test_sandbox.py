import os
import sys
import time

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.abspath("."))

from tools.system.sandbox import execute_sandboxed
from tools.custom.sandbox_execute import sandbox_execute, register, schema

def test_basic_execution():
    print("\n--- Test 1: Basic Python Execution ---")
    code = "print('Hello from the digital sandbox!')\nx = 10 + 20\nprint(f'Result: {x}')"
    res = execute_sandboxed(code=code)
    print(f"Success: {res.get('success')}")
    print(f"Stdout:\n{res.get('stdout')}")
    print(f"Stderr: {res.get('stderr')}")
    print(f"Elapsed: {res.get('elapsed_s')}s")
    assert res.get("success") is True
    assert "Result: 30" in res.get("stdout")

def test_isolation():
    print("\n--- Test 2: File System Isolation ---")
    # Try to look for jarvis.py in the sandbox's working directory
    code = "import os\nprint(f'cwd: {os.getcwd()}')\nprint(f'jarvis.py exists: {os.path.exists(\"jarvis.py\")}')"
    res = execute_sandboxed(code=code)
    print(f"Success: {res.get('success')}")
    print(f"Stdout:\n{res.get('stdout')}")
    assert res.get("success") is True
    assert "jarvis.py exists: False" in res.get("stdout")

def test_timeout():
    print("\n--- Test 3: Timeout Enforcement ---")
    code = "import time\nprint('Starting sleep...')\ntime.sleep(10)\nprint('Sleep done!')"
    res = execute_sandboxed(code=code, timeout=2)
    print(f"Success: {res.get('success')}")
    print(f"Error: {res.get('error')}")
    print(f"Elapsed: {res.get('elapsed_s')}s")
    assert res.get("success") is False
    assert "timed out" in res.get("error").lower()

def test_package_installation():
    print("\n--- Test 4: Sandbox Package Installation ---")
    # We will install a tiny package 'pybase64' and use it
    code = "import pybase64\nencoded = pybase64.b64encode(b'sandbox_test')\nprint(f'Encoded: {encoded.decode()}')"
    res = execute_sandboxed(code=code, install_packages=["pybase64"])
    print(f"Success: {res.get('success')}")
    print(f"Stdout:\n{res.get('stdout')}")
    print(f"Stderr: {res.get('stderr')}")
    if not res.get("success"):
        print(f"Error detail: {res.get('error')}")
    assert res.get("success") is True
    assert "Encoded: c2FuZGJveF90ZXN0" in res.get("stdout")

def test_custom_tool_registration():
    print("\n--- Test 5: Custom Tool Registration and Schema ---")
    reg = register()
    sch = schema()
    
    print(f"Registered tools: {list(reg.keys())}")
    print(f"Schema Name: {sch['function']['name']}")
    print(f"Schema Required Params: {sch['function']['parameters']['required']}")
    
    assert "sandbox_execute" in reg
    assert sch["function"]["name"] == "sandbox_execute"
    assert "code" in sch["function"]["parameters"]["required"]

    # Test executing code using the custom tool wrapper
    print("Testing wrapper execution...")
    res = sandbox_execute(code="print('Wrapper test passed!')")
    print(f"Wrapper Success: {res.get('success')}")
    print(f"Wrapper Stdout: {res.get('stdout').strip()}")
    assert res.get("success") is True
    assert "Wrapper test passed!" in res.get("stdout")

if __name__ == "__main__":
    print("==================================================")
    print("              RUNNING SANDBOX TESTS               ")
    print("==================================================")
    
    start_time = time.time()
    try:
        test_basic_execution()
        test_isolation()
        test_timeout()
        test_package_installation()
        test_custom_tool_registration()
        
        print("\n==================================================")
        print(f"         ALL TESTS PASSED SUCCESSFULLY! ({round(time.time() - start_time, 2)}s)")
        print("==================================================")
    except AssertionError as e:
        print("\n==================================================")
        print("               TEST FAILURE OCCURRED              ")
        print("==================================================")
        raise e
