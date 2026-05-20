import os
import sys

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.abspath("."))

from autonomous.learner import AutoLearner

def dummy_tool_fn(tool, params):
    # This should never be called for sandboxed tools
    print(f"ERROR: dummy_tool_fn called for tool '{tool}' with params {params}")
    return {"success": False, "error": "Should have been sandboxed"}

def test_learner_sandboxing():
    print("==================================================")
    print("        RUNNING AUTO-LEARNER SANDBOX TESTS       ")
    print("==================================================")
    
    # Mock tool registry
    mock_registry = {
        "execute_code": {},
        "run_python": {},
        "write_file": {},
        "create_file": {},
        "move_file": {},
        "delete_file": {},
    }
    
    # Instantiate AutoLearner
    learner = AutoLearner(
        tool_registry=mock_registry,
        tool_fn=dummy_tool_fn,
        idle_threshold_minutes=0,
        min_practice_interval_minutes=0
    )
    
    # Test each tool's sandboxed practice
    sandboxed_tools = ["execute_code", "run_python", "write_file", "create_file", "move_file", "delete_file"]
    
    for tool in sandboxed_tools:
        print(f"\n--- Testing Sandboxed Practice: '{tool}' ---")
        gap = {"topic": tool, "type": "tool"}
        res = learner._practice(gap)
        
        print(f"Tool: {res.get('tool')}")
        print(f"Practiced: {res.get('practiced')}")
        print(f"Success: {res.get('success')}")
        print(f"Notes: {res.get('notes')}")
        
        assert res.get("practiced") is True
        assert res.get("success") is True
        assert "[SANDBOX PRACTICE]" in res.get("notes")
        
    print("\n==================================================")
    print("   AUTO-LEARNER SANDBOX PRACTICE TESTS PASSED!   ")
    print("==================================================")

if __name__ == "__main__":
    test_learner_sandboxing()
