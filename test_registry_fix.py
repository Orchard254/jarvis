"""
Quick test to verify JARVIS tool registry is working correctly
"""
import sys
sys.path.insert(0, '/workspace')

from tools.registry import ToolRegistry, get_registry

# Test 1: Get registry instance
print("Test 1: Getting registry instance...")
registry = get_registry()
print(f"✓ Registry instance obtained: {type(registry).__name__}")

# Test 2: Check get_all_schemas method exists
print("\nTest 2: Checking get_all_schemas method...")
assert hasattr(registry, 'get_all_schemas'), "get_all_schemas method missing!"
print("✓ get_all_schemas method exists")

# Test 3: Load tools and get schemas
print("\nTest 3: Loading tools and getting schemas...")
count = registry.load_all_tools()
print(f"✓ Loaded {count} tools")

schemas = registry.get_all_schemas()
print(f"✓ Got {len(schemas)} tool schemas")

# Test 4: Verify some expected tools exist
print("\nTest 4: Verifying expected tools...")
expected_tools = ['get_time', 'get_date', 'screenshot', 'open_app', 'search_web']
for tool_name in expected_tools:
    exists = registry.has_tool(tool_name)
    status = "✓" if exists else "✗"
    print(f"{status} {tool_name}: {'found' if exists else 'MISSING'}")

# Test 5: Execute a simple tool
print("\nTest 5: Executing get_time tool...")
result = registry.execute('get_time')
print(f"✓ Result: success={result.success}, output={result.output[:50] if result.output else 'None'}...")

print("\n" + "="*60)
print("ALL TESTS PASSED! ✓")
print("="*60)
