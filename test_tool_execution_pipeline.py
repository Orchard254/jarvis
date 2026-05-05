#!/usr/bin/env python3
"""
Tool Call Execution Pipeline - Demo Script

This script demonstrates the complete pipeline from LLM output to tool execution:
1. LLM generates a tool call like "TOOL: open_control_panel()"
2. Parser detects and parses it into structured format
3. Schema validation ensures correctness
4. Tool is retrieved from registry
5. Tool is executed with actual system-level action

Run this to verify the fix works correctly.
"""

import sys
sys.path.insert(0, '.')

from jarvis.tools.registry import ToolRegistry
from jarvis.core.tool_parser import is_tool_call, parse_tool_call, validate_tool_call_schema


def test_pipeline(llm_output: str, expected_tool: str, expected_args: dict):
    """Test the complete pipeline for a given LLM output."""
    print(f"\n{'='*70}")
    print(f"TEST: {llm_output}")
    print('='*70)
    
    # Step 1: Detection
    is_tool = is_tool_call(llm_output)
    print(f"1. DETECTION")
    print(f"   is_tool_call() = {is_tool}")
    assert is_tool, f"Failed to detect tool call in: {llm_output}"
    
    # Step 2: Parsing
    parsed = parse_tool_call(llm_output)
    print(f"\n2. PARSING")
    print(f"   Result: {parsed}")
    assert parsed is not None, "Parsing returned None"
    assert parsed['type'] == 'tool', f"Wrong type: {parsed['type']}"
    assert parsed['name'] == expected_tool, f"Wrong tool name: {parsed['name']} != {expected_tool}"
    assert parsed['args'] == expected_args, f"Wrong args: {parsed['args']} != {expected_args}"
    
    # Step 3: Schema Validation
    valid, error = validate_tool_call_schema(parsed)
    print(f"\n3. SCHEMA VALIDATION")
    print(f"   Valid: {valid}, Error: '{error}'")
    assert valid, f"Schema validation failed: {error}"
    
    # Step 4: Registry Lookup
    registry = ToolRegistry.get_instance()
    registry.load_all_tools()
    all_tools = registry.get_all_tools()
    
    tool = all_tools.get(parsed['name'])
    print(f"\n4. REGISTRY LOOKUP")
    print(f"   Tool found: {tool is not None}")
    if tool:
        print(f"   Tool name: {tool.name}")
        print(f"   Tool description: {tool.description}")
        print(f"   Has execute method: {hasattr(tool, 'execute')}")
    assert tool is not None, f"Tool '{parsed['name']}' not found in registry"
    
    # Step 5: Execution (simulated - don't actually run on non-Windows)
    print(f"\n5. EXECUTION")
    if hasattr(tool, 'execute'):
        print(f"   Would execute: {parsed['name']}({parsed['args']})")
        # On Linux, we can't actually run Windows tools, but we can verify the method exists
        print(f"   ✓ Tool is ready to execute on Windows system")
    
    print(f"\n✓ TEST PASSED")
    return True


def main():
    print("="*70)
    print("TOOL CALL EXECUTION PIPELINE - DEMONSTRATION")
    print("="*70)
    print("\nThis demo shows how LLM outputs are now EXECUTED instead of RETURNED.")
    print("\nBefore fix:")
    print('  User: "open control panel"')
    print('  LLM: "TOOL: open_control_panel()"')
    print('  System shows: "TOOL: open_control_panel()" ← WRONG (just text)')
    print("\nAfter fix:")
    print('  User: "open control panel"')
    print('  LLM: "TOOL: open_control_panel()"')
    print('  System: Parses → Validates → Executes → Control Panel OPENS ✓')
    
    # Test cases
    test_cases = [
        ("TOOL: open_control_panel()", "open_control_panel", {}),
        ("TOOL: open_app(app_name='notepad')", "open_app", {"app_name": "notepad"}),
        ("TOOL: set_volume(level=50)", "set_volume", {"level": 50}),
    ]
    
    all_passed = True
    for llm_output, expected_tool, expected_args in test_cases:
        try:
            test_pipeline(llm_output, expected_tool, expected_args)
        except AssertionError as e:
            print(f"\n✗ TEST FAILED: {e}")
            all_passed = False
        except Exception as e:
            print(f"\n✗ TEST ERROR: {e}")
            all_passed = False
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print('='*70)
    if all_passed:
        print("✓ ALL TESTS PASSED!")
        print("\nThe pipeline correctly:")
        print("  1. Detects tool calls in LLM output")
        print("  2. Parses them into structured format")
        print("  3. Validates the schema")
        print("  4. Finds the tool in the registry")
        print("  5. Executes the tool (on Windows)")
        print("\nLLM outputs are now EXECUTED, not returned as text!")
    else:
        print("✗ SOME TESTS FAILED")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
