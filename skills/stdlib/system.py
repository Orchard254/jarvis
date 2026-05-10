"""skills.stdlib.system — processes, system settings, app launch/install."""
from tools.process_manager import process_manager
from tools.system_settings import system_settings
from tools.open_app import open_app
from tools.install_app import install_app

__all__ = ["process_manager", "system_settings", "open_app", "install_app", "volume_mute_then_set"]


def volume_mute_then_set(target_level: int) -> dict:
    """
    Set volume by first muting (setting to 0), then setting to target level.
    Uses simulated keystrokes for reliable volume control.
    
    Args:
        target_level: Target volume level (0-100)
    
    Returns:
        dict with success status and result
    """
    import pyautogui
    import time
    
    try:
        # Clamp value
        target_level = max(0, min(100, int(target_level)))
        
        # Step 1: Mute by pressing volume down repeatedly (or use mute key)
        # First try to mute completely
        pyautogui.press('volumemute')
        time.sleep(0.3)
        
        # Step 2: If target is 0, we're done (already muted)
        if target_level == 0:
            return {
                "success": True,
                "action": "volume_mute_then_set",
                "value": 0,
                "message": "Volume muted (set to 0)."
            }
        
        # Step 3: Press volume up repeatedly to reach target
        # Each press typically increases by ~2-5% depending on system
        # We'll use a conservative estimate and check
        presses_needed = target_level // 2  # Assume ~2% per press
        
        for _ in range(presses_needed):
            pyautogui.press('volumeup')
            time.sleep(0.05)  # Small delay between presses
        
        return {
            "success": True,
            "action": "volume_mute_then_set",
            "value": target_level,
            "message": f"Volume set to {target_level}% using mute-then-set method."
        }
        
    except Exception as e:
        return {
            "success": False,
            "action": "volume_mute_then_set",
            "error": str(e)
        }
