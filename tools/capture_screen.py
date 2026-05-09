
"""
Primitive: capture_screen(region=None, monitor=None)
Detects black/UAC screens, resizes to limit token bloat.
Supports multi-monitor setups via mss (preferred) or Pillow fallback.
"""
import base64
import io
import logging
from PIL import Image
from settings import MAX_SCREENSHOTS_IN_CONTEXT

logger = logging.getLogger(__name__)

# Try mss first for multi-monitor support
try:
    import mss
    _mss_available = True
except ImportError:
    _mss_available = False

try:
    from PIL import ImageGrab
    _pil_grab_available = True
except ImportError:
    _pil_grab_available = False


def _grab_mss(monitor_idx: int = 0, region: tuple = None):
    """Capture via mss — supports multiple monitors."""
    with mss.mss() as sct:
        if region:
            # region is (left, top, right, bottom)
            mon = {"left": region[0], "top": region[1], "width": region[2] - region[0], "height": region[3] - region[1]}
        else:
            # monitor 0 = all monitors combined; 1+ = individual monitors
            if monitor_idx == 0:
                # Default to primary monitor (first real monitor, not combined)
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            elif monitor_idx < len(sct.monitors):
                mon = sct.monitors[monitor_idx]
            else:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        raw = sct.grab(mon)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def _grab_pil(region: tuple = None):
    """Capture via Pillow — primary monitor only."""
    if region:
        return ImageGrab.grab(bbox=region)
    # Pillow 8.2+ supports all_screens, but it merges them into one giant image.
    # We default to primary only for predictable behaviour.
    try:
        return ImageGrab.grab()
    except Exception:
        return ImageGrab.grab(bbox=None)


def capture_screen(region: tuple = None, monitor: int = None) -> dict:
    """
    Capture screen and return base64 PNG.

    Args:
        region: Optional (left, top, right, bottom) bbox.
        monitor: Monitor index (0 = default/primary, 1+ = specific monitor).
                 Only effective when mss is installed.
    """
    try:
        monitor_idx = monitor if monitor is not None else 0

        if _mss_available:
            try:
                img = _grab_mss(monitor_idx=monitor_idx, region=region)
            except Exception as _mss_err:
                logger.debug(f"mss grab failed ({_mss_err}), falling back to PIL")
                img = _grab_pil(region=region)
        elif _pil_grab_available:
            img = _grab_pil(region=region)
        else:
            return {"success": False, "error": "No screen capture backend available (mss or Pillow)"}

        max_dim = 1280
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return {
            "image_b64": b64,
            "width": img.width,
            "height": img.height,
            "success": True,
            "monitor": monitor_idx,
        }
    except Exception as e:
        logger.error(f"capture_screen failed: {e}")
        return {"success": False, "error": str(e)}
