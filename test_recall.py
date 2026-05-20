import asyncio
import os
import sys
import subprocess
import time

sys.path.insert(0, os.path.abspath('.'))
from autonomous import context_recorder

def test():
    print("Opening Notepad...")
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2) # Wait for it to open
    
    print("Starting Context Recorder daemon...")
    loop = asyncio.new_event_loop()
    context_recorder.start(loop)
    
    print("Waiting 15 seconds to let it take a snapshot and index it...")
    time.sleep(15)
    
    print("Stopping Context Recorder...")
    context_recorder.stop()
    
    print("\nQuerying Recall Memory for 'Untitled'...")
    results = context_recorder.search_memory("Untitled", n_results=2)
    
    print("\n--- Result ---")
    if results:
        print(f"Success! Found {len(results)} past screens.")
        for r in results:
            text_preview = r["text"][:100] + "..." if len(r["text"]) > 100 else r["text"]
            print(f"  Window: {r['window_title']}")
            print(f"  Preview: {text_preview}")
    else:
        print("Failed to find any memory hits.")

    print("\nClosing Notepad...")
    proc.terminate()

if __name__ == "__main__":
    test()
