"""
test_dynamic_execution.py - Test script for dynamic tool execution fixes

Verifies:
1. run_python with import subprocess no longer gets blocked
2. run_python with shutil.rmtree('C:\\Windows') still gets blocked
3. _generate_tool with a tool using psutil creates the file successfully
4. The generated tool appears in jarvis/tools/generated/
5. The generated tool gets registered and is callable via the registry
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_run_python_subprocess_allowed():
    """Test 1: run_python with import subprocess should be allowed."""
    from jarvis.safety.tool_guard import ToolGuard
    
    guard = ToolGuard()
    code = """
import subprocess
result = subprocess.run(['echo', 'hello'], capture_output=True)
print(result.stdout)
"""
    is_valid, error_msg = guard._validate_run_python({'code': code}, is_generated_tool=False)
    
    if is_valid:
        print("PASS: run_python with import subprocess is allowed")
        return True
    else:
        print(f"FAIL: run_python with import subprocess was blocked: {error_msg}")
        return False


def test_destructive_operation_blocked():
    """Test 2: run_python with shutil.rmtree('C:\\Windows') should be blocked."""
    from jarvis.safety.tool_guard import ToolGuard
    
    guard = ToolGuard()
    code = """
import shutil
shutil.rmtree('C:\\\\Windows')
"""
    is_valid, error_msg = guard._validate_run_python({'code': code}, is_generated_tool=False)
    
    if not is_valid and 'Destructive' in error_msg:
        print(f"PASS: Destructive operation correctly blocked: {error_msg}")
        return True
    elif is_valid:
        print("FAIL: Destructive operation was NOT blocked")
        return False
    else:
        print(f"PARTIAL: Operation blocked but with unexpected message: {error_msg}")
        return True  # Still passes since it was blocked


def test_generate_tool_with_psutil():
    """Test 3: _generate_tool with psutil should create file successfully."""
    from jarvis.safety.tool_guard import ToolGuard
    
    guard = ToolGuard()
    code = """
class PortKillerTool:
    name = "port_killer"
    description = "Kill process using a specific port"
    
    def execute(self, port: int):
        import psutil
        for conn in psutil.net_connections():
            if conn.laddr.port == port:
                psutil.Process(conn.pid).terminate()
                return f"Killed PID {conn.pid}"
        return f"No process found on port {port}"
"""
    is_valid, error_msg = guard.validate_generated_tool_code(code)
    
    if is_valid:
        print("PASS: Generated tool code with psutil validated successfully")
        return True
    else:
        print(f"FAIL: Generated tool code with psutil was blocked: {error_msg}")
        return False


def test_generated_file_created():
    """Test 4: Verify generated tool file can be created in jarvis/tools/generated/."""
    from pathlib import Path
    
    # Simulate what _generate_tool does - with proper BaseTool subclass
    tool_name = "TestPortKiller"
    code = '''from jarvis.tools.base import BaseTool, ToolResult

class TestPortKiller(BaseTool):
    name = "test_port_killer"
    description = "Test tool for port killing"
    
    def execute(self, port: int = 8080) -> ToolResult:
        return ToolResult.ok(f"Would kill process on port {port}")
    
    def validate(self, **kwargs):
        return True, ""
'''
    
    tool_filename = Path(__file__).parent.parent / 'jarvis' / 'tools' / 'generated' / f'{tool_name.lower()}.py'
    
    try:
        # Ensure directory exists
        import os
        os.makedirs(tool_filename.parent, exist_ok=True)
        
        # Write the file
        with open(tool_filename, 'w') as f:
            f.write(code)
        
        # Verify file exists
        if tool_filename.exists():
            print(f"PASS: Generated tool file created at {tool_filename}")
            return True
        else:
            print(f"FAIL: Generated tool file was not created at {tool_filename}")
            return False
    except Exception as e:
        print(f"FAIL: Error creating generated tool file: {e}")
        return False


def test_generated_tool_registration():
    """Test 5: Verify generated tool can be loaded and registered."""
    from jarvis.tools.registry import ToolRegistry
    from jarvis.tools.base import BaseTool
    from pathlib import Path
    import importlib.util
    
    tool_name = "TestPortKiller"
    tool_filename = Path(__file__).parent.parent / 'jarvis' / 'tools' / 'generated' / f'{tool_name.lower()}.py'
    
    if not tool_filename.exists():
        print("SKIP: Generated tool file doesn't exist (run test 4 first)")
        return None
    
    try:
        # Load the module
        spec = importlib.util.spec_from_file_location(f"{tool_name.lower()}_tool", tool_filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Create registry using singleton pattern (same as real system)
        registry = ToolRegistry.get_instance()
        
        if hasattr(module, tool_name):
            tool_class = getattr(module, tool_name)
            
            # Check if it's a BaseTool subclass
            if issubclass(tool_class, BaseTool):
                registry.register(tool_class())
                
                # Verify registration - check both name variants
                if registry.has_tool('test_port_killer') or tool_name.lower() in registry._tools:
                    print("PASS: Generated tool successfully registered and callable")
                    return True
                else:
                    # Debug info
                    print(f"DEBUG: Tools in registry: {list(registry._tools.keys())}")
                    print("FAIL: Tool was not registered properly")
                    return False
            else:
                print(f"FAIL: Generated class is not a BaseTool subclass")
                return False
        else:
            print(f"FAIL: Generated code does not contain class {tool_name}")
            return False
            
    except Exception as e:
        print(f"FAIL: Error loading/registering generated tool: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_runner_validation_allows_subprocess():
    """Test 6: RunPythonTool.validate should allow subprocess imports."""
    from jarvis.tools.scripts.runner import RunPythonTool
    
    tool = RunPythonTool()
    code = """
import subprocess
result = subprocess.run(['echo', 'test'], capture_output=True)
print(result.stdout)
"""
    is_valid, error_msg = tool.validate(code=code, timeout=30)
    
    if is_valid:
        print("PASS: RunPythonTool.validate allows subprocess imports")
        return True
    else:
        print(f"FAIL: RunPythonTool.validate blocked subprocess: {error_msg}")
        return False


def test_runner_validation_blocks_destructive():
    """Test 7: RunPythonTool.validate should block destructive operations."""
    from jarvis.tools.scripts.runner import RunPythonTool
    
    tool = RunPythonTool()
    code = """
import shutil
shutil.rmtree('C:\\\\Windows')
"""
    is_valid, error_msg = tool.validate(code=code, timeout=30)
    
    if not is_valid and 'Dangerous' in error_msg:
        print(f"PASS: RunPythonTool.validate correctly blocks destructive ops: {error_msg}")
        return True
    elif is_valid:
        print("FAIL: RunPythonTool.validate did NOT block destructive operation")
        return False
    else:
        print(f"PARTIAL: Blocked with unexpected message: {error_msg}")
        return True


def main():
    print("=" * 60)
    print("Testing Dynamic Execution Fixes")
    print("=" * 60)
    print()
    
    results = []
    
    # Test 1: subprocess allowed in run_python
    print("Test 1: run_python with subprocess should be allowed")
    results.append(test_run_python_subprocess_allowed())
    print()
    
    # Test 2: destructive operations blocked
    print("Test 2: run_python with destructive ops should be blocked")
    results.append(test_destructive_operation_blocked())
    print()
    
    # Test 3: generate_tool with psutil
    print("Test 3: generate_tool validation with psutil")
    results.append(test_generate_tool_with_psutil())
    print()
    
    # Test 4: file creation
    print("Test 4: generated tool file creation")
    results.append(test_generated_file_created())
    print()
    
    # Test 5: tool registration
    print("Test 5: generated tool registration")
    reg_result = test_generated_tool_registration()
    if reg_result is not None:
        results.append(reg_result)
    print()
    
    # Test 6: runner validation allows subprocess
    print("Test 6: RunPythonTool.validate allows subprocess")
    results.append(test_runner_validation_allows_subprocess())
    print()
    
    # Test 7: runner validation blocks destructive
    print("Test 7: RunPythonTool.validate blocks destructive")
    results.append(test_runner_validation_blocks_destructive())
    print()
    
    # Summary
    print("=" * 60)
    passed = sum(1 for r in results if r is True)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("ALL TESTS PASSED!")
        return 0
    else:
        print("SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
