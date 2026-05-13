"""
Tool: manage_bluetooth(action, device_id)
List, disconnect, block, scan, or pair Bluetooth devices on Windows.
"""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger(__name__)


def manage_bluetooth(action: str = "list", device_id: str = "") -> dict:
    """
    Manage Bluetooth devices on Windows.

    Args:
        action:    "list"       → paired devices
                   "disconnect" → disable device by name or InstanceId
                   "block"      → same as disconnect
                   "scan"       → open Bluetooth add-device wizard and start scanning
                   "pair"       → click a device name in the pairing list to initiate pairing
        device_id: Device name for disconnect/block/pair actions.
    """

    def run_ps(script: str) -> tuple[str, int]:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True, capture_output=True,
        )
        return result.stdout + result.stderr, result.returncode

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action == "list":
        out, code = run_ps(r"""
$devices = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue |
    Where-Object { $_.FriendlyName -and $_.Status -eq 'OK' }
$devices | Select-Object InstanceId, FriendlyName | ConvertTo-Json -Compress
""")
        if code != 0:
            return {"success": False, "message": out, "devices": []}
        import json
        try:
            raw = json.loads(out)
            if isinstance(raw, dict):
                raw = [raw]
            devices = [{"id": d.get("InstanceId", ""), "name": d.get("FriendlyName", "")} for d in raw]
        except json.JSONDecodeError:
            devices = []
        return {"success": True, "devices": devices, "message": f"{len(devices)} devices found"}

    # ── SCAN — open add-device wizard via classic control panel ──────────────
    if action == "scan":
        try:
            subprocess.Popen("control bthprops.cpl", shell=True)
            time.sleep(1)
            import pyautogui
            import pygetwindow as gw
            time.sleep(1)
            wins = gw.getWindowsWithTitle("Bluetooth")
            bt_win = None
            for w in wins:
                if "Device" in w.title or "Bluetooth" in w.title:
                    bt_win = w
                    break
            if bt_win:
                bt_win.activate()
                time.sleep(0.3)
                pyautogui.hotkey("alt", "a")
                time.sleep(2)
                pyautogui.press("enter")
                time.sleep(3)
                return {"success": True, "message": "Bluetooth scanning started.", "devices": []}
            return {"success": True, "message": "Bluetooth control panel opened. Look for 'Add a device' button.", "devices": []}
        except Exception:
            return {"success": True, "message": "Bluetooth control panel opened. Select 'Add a device' manually.", "devices": []}

    # ── PAIR — click a device in the pairing wizard ─────────────────────────
    if action == "pair":
        if not device_id:
            return {"success": False, "message": "device_id is required for pair.", "devices": []}
        try:
            import pyautogui
            import pygetwindow as gw
            # Find the Bluetooth device wizard window
            time.sleep(1)
            wins = gw.getWindowsWithTitle("Bluetooth")
            bt_win = None
            for w in wins:
                if "Wizard" in w.title or "Device" in w.title or "Bluetooth" in w.title:
                    bt_win = w
                    break
            if bt_win:
                bt_win.activate()
                time.sleep(0.5)
            # Type device name to filter the list
            pyautogui.write(device_id, interval=0.05)
            time.sleep(1)
            # Click in the device list area and press down then enter
            screen_w, screen_h = pyautogui.size()
            pyautogui.click(screen_w // 2, screen_h // 2 - 50)
            time.sleep(0.5)
            pyautogui.press("down")
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(2)
            return {"success": True, "message": f"Attempted to select '{device_id}' for pairing. Check for PIN confirmation dialog.", "devices": []}
        except ImportError:
            return {"success": False, "message": "pyautogui not installed.", "devices": []}
        except Exception as exc:
            return {"success": False, "message": f"Pair automation failed: {exc}. Pair manually via control bthprops.cpl", "devices": []}

    # ── DISCONNECT / BLOCK ────────────────────────────────────────────────────
    if not device_id:
        return {"success": False, "message": "device_id is required for disconnect/block/scan/pair.", "devices": []}

    device_id = device_id.replace("\\\\", "\\").replace("\\", "\\")
    lookup = rf"""
$id = '{device_id}'
$device = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue |
    Where-Object {{ `$_.Status -eq 'OK' }} |
    Where-Object {{ `$_.InstanceId -eq `$id -or `$_.FriendlyName -eq `$id -or `$_.FriendlyName -like "*`$id*" }}
if (-not `$device) {{
    `$device = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue |
        Where-Object {{ `$_.Status -eq 'OK' -and `$_.InstanceId -like "*`$id*" }}
}}
if (-not `$device) {{ Write-Output "NOT_FOUND"; exit 0 }}
foreach (`$d in `$device) {{
    Disable-PnpDevice -InstanceId "`$(`$d.InstanceId)" -Confirm:`$false
    Start-Sleep -Milliseconds 200
    `$after = Get-PnpDevice -InstanceId `$d.InstanceId -ErrorAction SilentlyContinue
    `$status = if (`$after) {{ `$after.Status }} else {{ "REMOVED" }}
    Write-Output ("`$(`$d.InstanceId)|`$(`$d.FriendlyName)|`$status")
}}
"""
    out, code = run_ps(lookup)
    if "NOT_FOUND" in out.splitlines():
        return {"success": False, "message": f"No Bluetooth device matching '{device_id}' found.", "devices": []}

    disabled = 0
    for line in out.splitlines():
        line = line.strip()
        parts = line.split("|")
        if len(parts) == 3 and parts[2] != "OK":
            disabled += 1

    if disabled > 0:
        return {"success": True, "message": f"Disabled {disabled} device(s)", "devices": []}
    elif code == 0:
        return {"success": True, "message": "Device processed", "devices": []}
    else:
        return {"success": False, "message": out.strip(), "devices": []}


def register():
    return (
        "manage_bluetooth",
        manage_bluetooth,
        {
            "type": "function",
            "function": {
                "name": "manage_bluetooth",
                "description": "Manage Bluetooth devices on Windows. 'list' to see paired devices. 'scan' to open the add-device wizard and start scanning for new devices. 'pair' to click a device name in the pairing list. 'disconnect'/'block' to disable a device by name. Do NOT use for controlling non-Bluetooth hardware or managing Wi-Fi.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "disconnect", "block", "scan", "pair"],
                            "description": "'list' to see paired devices. 'scan' to open add-device wizard and scan. 'pair' to click a device name in the pairing list. 'disconnect'/'block' to disable.",
                        },
                        "device_id": {
                            "type": "string",
                            "description": "Device name (e.g. 'V527', 'BT5.4 Mouse') for disconnect/block/pair. Not required for 'list' or 'scan'.",
                        },
                    },
                    "required": ["action"],
                },
            },
        },
    )
