import os
import sys
import time
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pygetwindow as gw
from tools.adapters import open_app, close_app

def test_open_app_waits_for_focus():
    if sys.platform != "win32":
        return

    # Capture the starting active window title
    start_win = gw.getActiveWindow()
    start_title = start_win.title if start_win else ""

    # Open Notepad using open_app
    print(f"Launching Notepad... current active window is: '{start_title}'")
    res = open_app(name="notepad")
    assert res.get("success") is True, f"Failed to launch notepad: {res.get('error')}"

    # Get new active window
    new_win = gw.getActiveWindow()
    new_title = new_win.title if new_win else ""
    print(f"Notepad launched! New active window is: '{new_title}'")

    # Assert that the active window is indeed Notepad and not the starting window
    assert "notepad" in new_title.lower() or "untitled" in new_title.lower(), (
        f"Expected Notepad to be focused, but active window is '{new_title}'"
    )
    
    # Close notepad
    print("Closing Notepad...")
    close_res = close_app(name="notepad", force=True)
    print(f"Close result: {close_res}")
