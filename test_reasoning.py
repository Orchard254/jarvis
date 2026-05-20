import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath('.'))
from agents.sub_agent_registry import registry
from agents.base_agent import SubAgentTask
# This will trigger registration
import agents.sub_agents.reasoning_agent

def test():
    print("Initializing ReasoningAgent (Tree of Thoughts)...")
    agent = registry.get("reasoning")
    if not agent:
        print("Failed to find 'reasoning' agent in registry.")
        return
    
    goal = "How can we implement a self-healing error recovery mechanism in Python that automatically catches exceptions, searches StackOverflow, and applies the hotfix at runtime?"
    print(f"\nTask: {goal}\n")
    
    task = SubAgentTask(goal=goal, context={})
    
    print("Running ReasoningAgent (Brainstorming -> Evaluating -> Selecting)...")
    result = agent.run(task)
    
    print("\n--- Result ---")
    print(f"Success: {result.success}")
    print(f"Summary: {result.summary}")
    
    if result.success:
        print("\n--- Brainstormed Paths ---")
        print(result.data.get("paths"))
        
        print("\n--- Evaluation & Final Decision ---")
        print(result.data.get("evaluation"))

if __name__ == "__main__":
    test()
