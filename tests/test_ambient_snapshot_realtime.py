import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pygetwindow as gw
from core.ambient_state import get_state

def test_snapshot_active_window_realtime():
    if sys.platform != "win32":
        return

    ambient = get_state()

    # Capture start window title from snapshot
    snap1 = ambient.snapshot()
    title1 = snap1.get("active_window_title")

    # Launch Notepad
    print("Launching Notepad...")
    proc = subprocess.Popen(["notepad.exe"])
    try:
        # Wait a moment for notepad window to register and focus
        start_time = time.time()
        notepad_title = ""
        while time.time() - start_time < 3:
            w = gw.getActiveWindow()
            if w and "notepad" in w.title.lower():
                notepad_title = w.title
                break
            time.sleep(0.1)

        assert notepad_title != "", "Notepad did not receive active focus"
        print(f"Notepad focused with title: '{notepad_title}'")

        # Now, immediately query ambient snapshot. It should return Notepad title instantly,
        # even if the background window monitor thread hasn't ticked yet!
        snap2 = ambient.snapshot()
        title2 = snap2.get("active_window_title")
        print(f"Snapshot returned active window: '{title2}'")

        assert title2 == notepad_title, (
            f"Expected snapshot active window to be '{notepad_title}', but got '{title2}'"
        )
    finally:
        # Clean up
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        print("Notepad closed.")
