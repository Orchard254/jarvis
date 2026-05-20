import asyncio
import os
import sys

# Add the jarvis directory to path so imports work
sys.path.insert(0, os.path.abspath('.'))

from agents.sub_agents.tool_creator_agent import ToolCreatorAgent
from agents.base_agent import SubAgentTask

async def run_test():
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
    print("Initializing ToolCreatorAgent...")
    agent = ToolCreatorAgent()
    
    task = SubAgentTask(
        task_id="test_123",
        goal="Create a tool named 'reverse_string' that takes a string 'text' and returns the reversed string.",
        context={"info": "Keep it very simple and safe."}
    )
    
    print("Running ToolCreatorAgent...")
    result = agent.run(task)
    
    print("\n--- Result ---")
    print(f"Success: {result.success}")
    print(f"Summary: {result.summary}")
    if not result.success:
        print(f"Error: {result.error}")
    else:
        print(f"Data: {result.data}")
        
    # Check if file was created
    if result.success and "file_path" in result.data:
        path = result.data["file_path"]
        if os.path.exists(path):
            print(f"\nFile {path} exists! Content:")
            with open(path, "r") as f:
                print(f.read())
        else:
            print(f"\nError: File {path} was not actually created.")

if __name__ == "__main__":
    asyncio.run(run_test())
