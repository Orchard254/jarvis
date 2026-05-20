import os
import sys
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ambient_state import get_state
from brain.intent_engine import _ambient_adjust

def test_terminal_redirect():
    ambient = get_state()
    
    # Patch _refresh_active_window to a no-op so snapshot() doesn't overwrite
    # our mocked state with the real foreground window title.
    original_refresh = ambient._refresh_active_window
    ambient._refresh_active_window = lambda: None
    
    try:
        # Manually configure state to mock active window as terminal and set last non-terminal
        ambient.set("active_window_title", "Windows PowerShell")
        ambient.set("last_non_terminal_window", "Untitled - Notepad")
        
        # Assert is_terminal_window detects PowerShell correctly
        assert ambient.is_terminal_window("Windows PowerShell") is True
        assert ambient.is_terminal_window("Untitled - Notepad") is False

        # Execute ambient adjust for a typing action with no target
        action = "type_text"
        params = {"text": "{ALT}f"}
        
        adjusted = _ambient_adjust(action, params)
        
        assert adjusted is not None, "Adjustment should occur"
        adj_action, adj_params = adjusted
        
        # Assert that action remains the same, but the target was redirected to Notepad!
        assert adj_action == "type_text"
        assert adj_params.get("target") == "Untitled - Notepad", (
            f"Expected target to be redirected to 'Untitled - Notepad', but got '{adj_params.get('target')}'"
        )
        print("Terminal redirection unit test successfully PASSED!")
    finally:
        ambient._refresh_active_window = original_refresh

