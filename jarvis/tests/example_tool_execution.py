"""
Example: Execute LLM Tool Calls

Demonstrates the new execution pipeline where LLM outputs are executed,
not returned as text.

Pipeline: Input → LLM → detect tool call → parse → execute → return result
"""

import sys
sys.path.insert(0, '.')

from jarvis.core.tool_parser import is_tool_call, parse_tool_call, validate_tool_call_schema
import json

print("=" * 60)
print("JARVIS Tool Call Execution Pipeline Demo")
print("=" * 60)

# Test cases showing different LLM output formats
test_cases = [
    # Explicit TOOL: format (recommended)
    "TOOL: open_app(app_name='notepad')",
    
    # TOOL: with multiple params
    "TOOL: navigate_to_url(url='https://example.com', timeout=30)",
    
    # JSON format (backward compatibility)
    '{"type": "tool", "name": "search_web", "args": {"query": "weather"}}',
    
    # Natural language with tool reference
    "I'll use open_app to launch Chrome",
    
    # Simple command pattern
    "Call the search tool with query 'news'",
    
    # Not a tool call - should be treated as chat
    "The weather is nice today",
]

print("\n1. PARSING TESTS\n" + "-" * 60)

for i, test in enumerate(test_cases, 1):
    print(f"\nTest {i}: {test[:50]}{'...' if len(test) > 50 else ''}")
    print(f"  is_tool_call: {is_tool_call(test)}")
    
    parsed = parse_tool_call(test)
    if parsed:
        print(f"  ✓ Parsed successfully:")
        print(f"    type: {parsed['type']}")
        print(f"    name: {parsed['name']}")
        print(f"    args: {parsed['args']}")
        
        valid, msg = validate_tool_call_schema(parsed)
        print(f"    schema_valid: {valid} ({msg})")
    else:
        print(f"  → Not a tool call (treat as chat/final response)")

print("\n\n2. EXECUTION PIPELINE EXAMPLE\n" + "-" * 60)

# Simulate what happens in the orchestrator
def simulate_execution_pipeline(llm_output: str):
    """Simulates the full execution pipeline from LLM output to action."""
    print(f"\n[LLM Output]: {llm_output}")
    
    # Step 1: Detect if it's a tool call
    if not is_tool_call(llm_output):
        print("[Detect] → Not a tool call, return as text response")
        return {'type': 'response', 'text': llm_output}
    
    print("[Detect] → Tool call detected")
    
    # Step 2: Parse into structured format
    parsed = parse_tool_call(llm_output)
    if not parsed:
        print("[Parse] → Failed to parse, ask LLM to clarify")
        return {'type': 'error', 'message': 'Could not parse tool call'}
    
    print(f"[Parse] → Structured plan: {json.dumps(parsed, indent=2)}")
    
    # Step 3: Validate schema
    valid, msg = validate_tool_call_schema(parsed)
    if not valid:
        print(f"[Validate] → Schema invalid: {msg}")
        return {'type': 'error', 'message': msg}
    
    print("[Validate] → Schema valid")
    
    # Step 4: Would execute here (skipped in demo - needs full orchestrator)
    print(f"[Execute] → Would call: {parsed['name']}({parsed['args']})")
    print("[Execute] → Tool executes system action (e.g., opens app)")
    print("[Execute] → Returns result, NOT the tool call text")
    
    return {
        'type': 'executed',
        'tool': parsed['name'],
        'args': parsed['args'],
        'result': '<tool output>'
    }

# Example: "open control panel" scenario
print("\n" + "=" * 60)
print("EXAMPLE: 'open control panel' actually opens it")
print("=" * 60)

user_command = "open the control panel"
print(f"\nUser says: '{user_command}'")
print("\n[Orchestrator Flow]:")
print("  1. User input → Intent classification")
print("  2. Intent → LLM with tools context")

# Simulated LLM response (what the LLM would output)
llm_response = "TOOL: open_app(app_name='control panel')"
print(f"  3. LLM output: {llm_response}")

# Execute through our pipeline
result = simulate_execution_pipeline(llm_response)

print(f"\n  4. Result: {result['type']}")
if result['type'] == 'executed':
    print(f"     → Control panel ACTUALLY OPENS (not returned as text)")
    print(f"     → User sees: 'Opening control panel'")
elif result['type'] == 'response':
    print(f"     → ERROR: Would show text to user instead of executing!")

print("\n" + "=" * 60)
print("KEY DIFFERENCE:")
print("=" * 60)
print("""
BEFORE (broken):
  LLM: "TOOL: open_app(app_name='notepad')"
  System: Shows "TOOL: open_app(...)" to user ❌

AFTER (fixed):
  LLM: "TOOL: open_app(app_name='notepad')"
  Parser: Detects tool call pattern
  Executor: Actually opens Notepad via subprocess
  System: Shows "Opening notepad" to user ✓
""")

print("=" * 60)
print("Demo complete! The pipeline now executes actions, not text.")
print("=" * 60)
