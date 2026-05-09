"""System settings control — volume, brightness, mute, wifi, battery."""

import logging
import subprocess

logger = logging.getLogger(__name__)


def system_settings(setting: str, value=None) -> dict:
    """
    Get or set system settings.
    Settings: volume (0-100), mute (True/False/toggle), brightness (0-100),
              wifi (status/enable/disable), battery
    """
    try:
        setting = setting.lower().strip()

        if setting == "volume":
            return _handle_volume(value)
        elif setting == "mute":
            return _handle_mute(value)
        elif setting == "brightness":
            return _handle_brightness(value)
        elif setting == "wifi":
            return _handle_wifi(value)
        elif setting == "battery":
            return _handle_battery()
        else:
            return {"success": False, "error": f"Unknown setting: '{setting}'"}

    except Exception as e:
        logger.error(f"system_settings({setting}): {e}")
        return {"success": False, "error": str(e)}


# ── Volume ────────────────────────────────────────────────────────────────────


def _handle_volume(value) -> dict:
    """Get or set master volume (0-100)."""
    action = "get" if value is None else "set"

    # Primary: pycaw
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol_obj = cast(interface, POINTER(IAudioEndpointVolume))

        if value is None:
            current = round(vol_obj.GetMasterVolumeLevelScalar() * 100)
            return {
                "success": True,
                "setting": "volume",
                "value": current,
                "action": "get",
            }
        else:
            clamped = max(0, min(100, int(value)))
            vol_obj.SetMasterVolumeLevelScalar(clamped / 100.0, None)
            return {
                "success": True,
                "setting": "volume",
                "value": clamped,
                "action": "set",
            }

    except ImportError:
        logger.debug("system_settings: pycaw not available, using pyautogui fallback")
    except Exception as e:
        logger.warning(f"system_settings volume pycaw error: {e}")

    # Fallback: pyautogui key presses (set only; can't reliably get)
    if value is not None:
        try:
            import pyautogui

            # Use nircmd if available for precise set
            result = subprocess.run(
                ["nircmd.exe", "setsysvolume", str(int(int(value) / 100 * 65535))],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return {
                    "success": True,
                    "setting": "volume",
                    "value": int(value),
                    "action": "set",
                }
        except Exception:
            pass

        return {
            "success": False,
            "setting": "volume",
            "error": "pycaw not installed and nircmd not found. Run: pip install pycaw",
        }
    else:
        return {
            "success": False,
            "setting": "volume",
            "error": "Cannot read volume without pycaw. Run: pip install pycaw",
        }


# ── Mute ──────────────────────────────────────────────────────────────────────


def _handle_mute(value) -> dict:
    """Get, set, or toggle system mute."""
    # Primary: pycaw
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol_obj = cast(interface, POINTER(IAudioEndpointVolume))

        current_mute = bool(vol_obj.GetMute())

        if value is None or str(value).lower() == "toggle":
            new_mute = not current_mute
        elif str(value).lower() in ("true", "1", "yes", "on"):
            new_mute = True
        else:
            new_mute = False

        if value is None:
            # get only
            return {
                "success": True,
                "setting": "mute",
                "value": current_mute,
                "action": "get",
            }

        vol_obj.SetMute(new_mute, None)
        return {"success": True, "setting": "mute", "value": new_mute, "action": "set"}

    except ImportError:
        logger.debug("system_settings: pycaw not available, using pyautogui mute key")
    except Exception as e:
        logger.warning(f"system_settings mute pycaw error: {e}")

    # Fallback: press the mute key
    try:
        import pyautogui

        pyautogui.press("volumemute")
        return {"success": True, "setting": "mute", "value": None, "action": "toggle"}
    except Exception as e:
        logger.error(f"system_settings mute pyautogui error: {e}")
        return {"success": False, "setting": "mute", "error": str(e)}


# ── Brightness ────────────────────────────────────────────────────────────────


def _handle_brightness(value) -> dict:
    """Get or set display brightness (0-100) via WMI PowerShell."""
    action = "get" if value is None else "set"

    # Primary: screen_brightness_control if installed
    try:
        import screen_brightness_control as sbc

        if value is None:
            current = sbc.get_brightness(display=0)
            level = current[0] if isinstance(current, list) else current
            return {
                "success": True,
                "setting": "brightness",
                "value": level,
                "action": "get",
            }
        else:
            clamped = max(0, min(100, int(value)))
            sbc.set_brightness(clamped, display=0)
            return {
                "success": True,
                "setting": "brightness",
                "value": clamped,
                "action": "set",
            }

    except ImportError:
        logger.debug(
            "system_settings: screen_brightness_control not available, trying WMI"
        )
    except Exception as e:
        logger.warning(f"system_settings brightness sbc error: {e}")

    # Fallback: WMI via PowerShell
    try:
        if value is None:
            ps = "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
            result = subprocess.run(
                ["powershell", "-c", ps],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                level = int(result.stdout.strip())
                return {
                    "success": True,
                    "setting": "brightness",
                    "value": level,
                    "action": "get",
                }
            return {
                "success": False,
                "setting": "brightness",
                "error": result.stderr.strip() or "WMI brightness query failed",
            }
        else:
            clamped = max(0, min(100, int(value)))
            ps = (
                f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                f".WmiSetBrightness(1, {clamped})"
            )
            result = subprocess.run(
                ["powershell", "-c", ps],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {
                    "success": False,
                    "setting": "brightness",
                    "error": result.stderr.strip() or "WMI brightness set failed",
                }
            return {
                "success": True,
                "setting": "brightness",
                "value": clamped,
                "action": "set",
            }

    except Exception as e:
        logger.error(f"system_settings brightness WMI error: {e}")
        return {"success": False, "setting": "brightness", "error": str(e)}


# ── WiFi ──────────────────────────────────────────────────────────────────────


def _handle_wifi(value) -> dict:
    """Get WiFi status, or enable/disable WiFi adapter."""
    # Normalise
    if value is None:
        value = "status"
    value = str(value).lower().strip()

    try:
        if value == "status":
            ps = (
                "Get-NetAdapter | Where-Object {$_.InterfaceDescription -like '*Wi-Fi*' "
                "-or $_.Name -eq 'Wi-Fi'} | Select-Object Name, Status | ConvertTo-Json"
            )
            result = subprocess.run(
                ["powershell", "-c", ps],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {
                    "success": False,
                    "setting": "wifi",
                    "error": result.stderr.strip() or "WiFi status query failed",
                }
            import json

            raw = result.stdout.strip()
            try:
                data = json.loads(raw)
            except Exception:
                data = raw
            return {"success": True, "setting": "wifi", "value": data, "action": "get"}

        elif value == "enable":
            ps = "Enable-NetAdapter -Name 'Wi-Fi' -Confirm:$false"
            result = subprocess.run(
                ["powershell", "-c", ps],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {
                    "success": False,
                    "setting": "wifi",
                    "error": result.stderr.strip() or "Failed to enable Wi-Fi",
                }
            return {
                "success": True,
                "setting": "wifi",
                "value": "enabled",
                "action": "set",
            }

        elif value == "disable":
            ps = "Disable-NetAdapter -Name 'Wi-Fi' -Confirm:$false"
            result = subprocess.run(
                ["powershell", "-c", ps],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {
                    "success": False,
                    "setting": "wifi",
                    "error": result.stderr.strip() or "Failed to disable Wi-Fi",
                }
            return {
                "success": True,
                "setting": "wifi",
                "value": "disabled",
                "action": "set",
            }

        else:
            return {
                "success": False,
                "setting": "wifi",
                "error": f"Unknown wifi value: '{value}'. Use status/enable/disable.",
            }

    except Exception as e:
        logger.error(f"system_settings wifi error: {e}")
        return {"success": False, "setting": "wifi", "error": str(e)}


# ── Battery ───────────────────────────────────────────────────────────────────


def _handle_battery() -> dict:
    """Get battery status using psutil."""
    try:
        import psutil

        bat = psutil.sensors_battery()
        if bat:
            return {
                "success": True,
                "setting": "battery",
                "value": {
                    "percent": round(bat.percent),
                    "plugged": bat.power_plugged,
                    "seconds_left": bat.secsleft if bat.secsleft != -1 else None,
                },
                "action": "get",
            }
        return {"success": False, "setting": "battery", "error": "No battery detected"}

    except ImportError:
        return {
            "success": False,
            "setting": "battery",
            "error": "psutil not installed. Run: pip install psutil",
        }
    except Exception as e:
        logger.error(f"system_settings battery: {e}")
        return {"success": False, "setting": "battery", "error": str(e)}
