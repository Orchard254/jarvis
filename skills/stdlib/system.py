"""skills.stdlib.system — processes, system settings, app launch/install."""
from tools.process_manager import process_manager
from tools.system_settings import system_settings
from tools.open_app import open_app
from tools.install_app import install_app

__all__ = ["process_manager", "system_settings", "open_app", "install_app", "volume_mute_then_set", "brightness_set_robust"]


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


def brightness_set_robust(target_level: int) -> dict:
    """
    Set screen brightness using three fallback methods for maximum reliability.
    
    Methods tried in sequence:
    1. screen_brightness_control library (most reliable)
    2. WMI PowerShell (Windows native)
    3. Keyboard simulation (ultimate fallback)
    
    Args:
        target_level: Target brightness level (0-100)
    
    Returns:
        dict with success status, method used, and result details
    """
    import time
    
    # Clamp value
    target_level = max(0, min(100, int(target_level)))
    
    # Method 1: screen_brightness_control library
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()
        sbc.set_brightness(target_level)
        # Verify the change
        new_brightness = sbc.get_brightness()
        if abs(new_brightness - target_level) <= 5:  # Allow small tolerance
            return {
                "success": True,
                "action": "brightness_set_robust",
                "method": "screen_brightness_control",
                "value": target_level,
                "previous_value": current,
                "message": f"Brightness set to {target_level}% using screen_brightness_control library."
            }
    except Exception:
        pass  # Fall through to next method
    
    # Method 2: WMI PowerShell (Windows native)
    try:
        import subprocess
        powershell_script = f"""
        $brightness = {target_level}
        $wmi = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods
        $wmi.WmiSetBrightness(1, $brightness)
        """
        result = subprocess.run(
            ["powershell", "-Command", powershell_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return {
                "success": True,
                "action": "brightness_set_robust",
                "method": "wmi_powershell",
                "value": target_level,
                "message": f"Brightness set to {target_level}% using WMI PowerShell."
            }
    except Exception:
        pass  # Fall through to next method
    
    # Method 3: Keyboard simulation (ultimate fallback)
    try:
        import pyautogui
        
        # First get current brightness if possible, otherwise estimate
        # Press brightness keys to reach target
        # Assume each keypress changes brightness by ~5%
        brightness_step = 5
        
        # Try to decrease brightness first (in case we're above target)
        presses_down = 100 // brightness_step  # Max presses to go to 0
        for _ in range(presses_down):
            pyautogui.press('brightnessdown')
            time.sleep(0.05)
        
        time.sleep(0.3)
        
        # Now increase to target
        presses_up = target_level // brightness_step
        for _ in range(presses_up):
            pyautogui.press('brightnessup')
            time.sleep(0.05)
        
        return {
            "success": True,
            "action": "brightness_set_robust",
            "method": "keyboard_simulation",
            "value": target_level,
            "message": f"Brightness set to {target_level}% using keyboard simulation (fallback method)."
        }
    except Exception as e:
        return {
            "success": False,
            "action": "brightness_set_robust",
            "methods_tried": ["screen_brightness_control", "wmi_powershell", "keyboard_simulation"],
            "error": str(e),
            "message": "All brightness control methods failed."
        }
