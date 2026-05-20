import asyncio
import os
import sys
import pyperclip
import time

sys.path.insert(0, os.path.abspath('.'))
from core.event_bus import event_bus
from agents.sub_agent_registry import registry
from agents.sub_agents.proactive_agent import ProactiveAgent

async def run_test():
    print("Initializing ProactiveAgent (Shadow Mode)...")
    agent = registry.get("proactive")
    if not agent:
        print("ProactiveAgent not found in registry. Registering...")
        agent = ProactiveAgent()
        registry.register(agent)
    
    # Start the monitoring loop in background
    asyncio.create_task(agent._monitor_loop())
    
    # Start the event bus loop
    event_bus.start()
    
    print("\nSimulating user copying a URL to the clipboard...")
    test_url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
    
    # Simulate the event that clipboard_monitor would send
    await event_bus.publish(
        "clipboard_changed", 
        {"content": test_url}, 
        "test_script"
    )
    
    print("Waiting 20 seconds for the Shadow Agent to process and silently fetch data...")
    for i in range(20):
        print(".", end="", flush=True)
        await asyncio.sleep(1)
    print("\nDone waiting. Check the logs above to see if it used web_search and store_memory.")

if __name__ == "__main__":
    # Configure logging to see the output
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_test())
