import asyncio
import os
import sys
import subprocess
import time

sys.path.insert(0, os.path.abspath('.'))
from tools.custom.read_ui_tree import read_ui_tree

def test():
    print("Opening Notepad...")
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2) # Wait for it to open
    
    print("\nScanning active window with UI Tree...")
    result = read_ui_tree("Untitled - Notepad")
    if not result.get("success"):
        # try fallback without title
        print("Fallback to foreground window...")
        result = read_ui_tree()
        
    print("\n--- Result ---")
    if result.get("success"):
        elements = result.get("elements", [])
        print(f"Success! Found {len(elements)} native UI elements.")
        print(f"Window Title: {result.get('window_title')}")
        
        # Print a few elements
        for i, el in enumerate(elements[:5]):
            print(f"  {i+1}: {el['type']} - '{el['text']}' @ {el['bounds']}")
            
        if len(elements) > 5:
            print(f"  ... and {len(elements) - 5} more.")
    else:
        print(f"Failed: {result.get('error')}")

    print("\nClosing Notepad...")
    proc.terminate()

if __name__ == "__main__":
    test()
