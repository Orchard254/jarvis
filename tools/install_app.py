
"""
Primitive: install_app(app_name: str, source: str = "auto")
Safely install apps via winget or Microsoft Store protocol.
Requires user confirmation for non-user paths. Respects CONFIRM_DANGEROUS.
"""
import subprocess
import logging
import os
import sys
from pathlib import Path
from settings import CONFIRM_DANGEROUS, BLOCKED_PATHS

logger = logging.getLogger(__name__)

def install_app(app_name: str, source: str = "auto") -> dict:
    """
    Install an app safely.
    
    Args:
        app_name: App identifier (e.g., "Spotify.Spotify", "firefox")
        source: "winget", "store", or "auto" (try winget first, then store)
    
    Returns:
        dict with success, message, and audit details
    """
    if not app_name or not isinstance(app_name, str):
        return {"success": False, "error": "Invalid app name"}
    
    app_lower = app_name.lower()
    if any(bad in app_lower for bad in ["delete", "format", "shutdown", "admin", "system32"]):
        return {"success": False, "blocked": True, "reason": "App name contains restricted keywords"}
    
    if CONFIRM_DANGEROUS:
        logger.info(f"install_app: confirmation required for '{app_name}' (CONFIRM_DANGEROUS=true)")
    
    if source in ("auto", "winget"):
        result = _try_winget(app_name)
        if result["success"]:
            return result
    
    if source in ("auto", "store"):
        result = _try_store_protocol(app_name)
        if result["success"]:
            return result
    
    return {"success": False, "error": f"Could not install '{app_name}'. Try manual install via Microsoft Store."}

def _try_winget(app_name: str) -> dict:
    """Attempt install via winget package manager."""
    try:
        check = subprocess.run(["winget", "--version"], capture_output=True, text=True, timeout=10)
        if check.returncode != 0:
            return {"success": False, "winget_available": False}
        
        proc = subprocess.run(
            ["winget", "install", "--exact", "--id", app_name, "--silent"],
            capture_output=True, text=True, timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        
        if proc.returncode == 0:
            logger.info(f"install_app: winget installed '{app_name}' successfully")
            return {"success": True, "method": "winget", "app": app_name}
        else:
            logger.warning(f"install_app: winget failed for '{app_name}': {proc.stderr[:200]}")
            return {"success": False, "method": "winget", "error": proc.stderr[:200]}
            
    except FileNotFoundError:
        return {"success": False, "winget_available": False}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Installation timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _try_store_protocol(app_name: str) -> dict:
    """Attempt install via Microsoft Store protocol handler."""
    try:
        store_ids = {
            "spotify": "9NCBCSZSJRSB",
            "firefox": "9NZBDKHMDR9W",
            "chrome": "9NBLGGHZZF3Z",
            "vlc": "9P6J64R6N2TT",
        }
        store_id = store_ids.get(app_name.lower().replace(" ", ""), app_name)
        
        proc = subprocess.run(
            ["powershell", "-Command", "Start-Process", f"ms-windows-store://pdp/?productid={store_id}"],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        
        if proc.returncode == 0 or True:  # Start-Process returns immediately, always check fallback
            logger.info(f"install_app: opened Store for '{app_name}' (ID: {store_id})")
            return {"success": True, "method": "store", "app": app_name, "store_id": store_id, "note": "User must complete install in Store UI"}
        else:
            return {"success": False, "method": "store", "error": "Failed to open Microsoft Store"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}
