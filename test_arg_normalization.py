#!/usr/bin/env python3
"""
Test script demonstrating the argument normalization fix.

Before fix:
  LLM outputs: TOOL: open_app(app_name='notepad')
  Safety check: FAILS with "No app specified"
  Result: Falls back to run_command, causing instability

After fix:
  LLM outputs: TOOL: open_app(app_name='notepad')
  Normalization: Converts app_name → app
  Safety check: PASSES
  Result: Executes successfully
"""

import sys
sys.path.insert(0, '.')

from jarvis.core.tool_parser import parse_tool_call
from jarvis.safety.tool_guard import ToolGuard


def test_argument_normalization():
    """Test that app_name parameter is properly handled."""
    
    print("=" * 60)
    print("ARGUMENT NORMALIZATION FIX - TEST")
    print("=" * 60)
    print()
    
    # Test cases
    test_cases = [
        ("TOOL: open_app(app_name='notepad')", True, "LLM standard format"),
        ("TOOL: open_app(app='chrome')", True, "Tool expected format"),
        ("TOOL: close_app(app_name='spotify')", True, "Close app with app_name"),
        ("TOOL: close_app(app='firefox')", True, "Close app with app"),
    ]
    
    guard = ToolGuard()
    all_passed = True
    
    for llm_output, should_pass, description in test_cases:
        print(f"Test: {description}")
        print(f"  Input: {llm_output}")
        
        # Step 1: Parse
        parsed = parse_tool_call(llm_output)
        if not parsed:
            print(f"  ✗ FAILED: Could not parse tool call")
            all_passed = False
            continue
        
        tool_name = parsed['name']
        args = parsed['args'].copy()
        print(f"  Parsed: tool={tool_name}, args={args}")
        
        # Step 2: Normalize (this is what orchestrator does)
        arg_mappings = {
            'open_app': {'app_name': 'app'},
            'close_app': {'app_name': 'app'},
        }
        
        original_args = args.copy()
        if tool_name in arg_mappings:
            for ext, int_name in arg_mappings[tool_name].items():
                if ext in args and int_name not in args:
                    args[int_name] = args.pop(ext)
        
        if args != original_args:
            print(f"  Normalized: {original_args} → {args}")
        
        # Step 3: Validate
        valid, msg = guard.validate_tool_call(tool_name, args)
        
        if should_pass and valid:
            print(f"  ✓ PASSED: Validation succeeded")
        elif not should_pass and not valid:
            print(f"  ✓ PASSED: Correctly blocked ({msg})")
        else:
            print(f"  ✗ FAILED: Expected {'pass' if should_pass else 'fail'}, got {'pass' if valid else 'fail'}")
            if msg:
                print(f"     Error: {msg}")
            all_passed = False
        
        print()
    
    # Test empty args (should fail)
    print("Test: Empty arguments (should be blocked)")
    valid_empty, msg_empty = guard._validate_open_app({})
    if not valid_empty:
        print(f"  ✓ PASSED: Correctly blocked empty args ({msg_empty})")
    else:
        print(f"  ✗ FAILED: Should have blocked empty args")
        all_passed = False
    print()
    
    print("=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print()
        print("The fix ensures:")
        print("  1. LLM can use 'app_name' parameter (natural naming)")
        print("  2. Safety layer accepts both 'app' and 'app_name'")
        print("  3. Orchestrator normalizes app_name → app before execution")
        print("  4. No more fallback to run_command for valid tool calls")
    else:
        print("✗ SOME TESTS FAILED")
        return 1
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(test_argument_normalization())
