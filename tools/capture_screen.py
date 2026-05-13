"""
Primitive: capture_screen(region=None, monitor=None, window_title=None, cursor=False, format="png")
Detects black/UAC screens, resizes to limit token bloat.
Supports multi-monitor setups, per-window capture, cursor overlay, and grid overlay.
"""
import base64
import io
import logging
from PIL import Image, ImageDraw, ImageFont
from settings import MAX_SCREENSHOTS_IN_CONTEXT

logger = logging.getLogger(__name__)

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
    with mss.MSS() as sct:
        if region:
            mon = {"left": region[0], "top": region[1], "width": region[2] - region[0], "height": region[3] - region[1]}
        else:
            # sct.monitors[0] is the virtual combined monitor spanning all displays
            # sct.monitors[1] is the primary monitor, sct.monitors[2+] are secondary
            if monitor_idx == 0:
                mon = sct.monitors[0]
            elif monitor_idx < len(sct.monitors):
                mon = sct.monitors[monitor_idx]
            else:
                mon = sct.monitors[0]
        raw = sct.grab(mon)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def _grab_pil(region: tuple = None):
    """Capture via Pillow — primary monitor only."""
    if region:
        return ImageGrab.grab(bbox=region)
    return ImageGrab.grab()


def _capture_window(window_title: str):
    """Capture a specific window by title substring. Returns PIL Image or None."""
    try:
        import win32gui
        import win32con
        import win32ui
    except ImportError:
        logger.warning("capture_window requires pywin32")
        return None

    try:
        def find_hwnd():
            search_title = window_title.lower().strip()
            result = [None]
            def _cb(h, _):
                try:
                    if not h or not win32gui.IsWindow(h):
                        return 1
                    if win32gui.IsWindowVisible(h):
                        t = win32gui.GetWindowText(h).lower()
                        if search_title in t:
                            result[0] = h
                            return 0
                except Exception:
                    pass
                return 1
            win32gui.EnumWindows(_cb, None)
            return result[0]

        hwnd = find_hwnd()
        if not hwnd:
            return None

        # Restore if minimized
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # Bring to foreground
        import ctypes
        ctypes.windll.user32.SwitchToThisWindow(hwnd, True)

        # Get window rect
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            return None

        # Capture via win32gui
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)

        # PrintWindow captures the window contents
        import ctypes
        PW_RENDERFULLCONTENT = 2
        ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), PW_RENDERFULLCONTENT)

        bmpinfo = bitmap.GetInfo()
        bmpstr = bitmap.GetBitmapBits(True)
        img = Image.frombytes("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX")

        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

        return img

    except Exception as e:
        logger.debug(f"_capture_window failed: {e}")
        return None


def _overlay_cursor(img: Image.Image) -> Image.Image:
    """Draw the current mouse cursor position on the image."""
    try:
        import pyautogui
        cursor_x, cursor_y = pyautogui.position()
        draw = ImageDraw.Draw(img)
        r = 6
        draw.ellipse(
            [cursor_x - r, cursor_y - r, cursor_x + r, cursor_y + r],
            outline="red",
            width=2,
        )
        draw.line(
            [cursor_x - r - 4, cursor_y, cursor_x + r + 4, cursor_y],
            fill="red",
            width=2,
        )
        draw.line(
            [cursor_x, cursor_y - r - 4, cursor_x, cursor_y + r + 4],
            fill="red",
            width=2,
        )
    except Exception as e:
        logger.debug(f"Cursor overlay failed: {e}")
    return img


def _overlay_grid(img: Image.Image, grid_size: int = 100) -> Image.Image:
    """Draw a numbered coordinate grid over the screenshot.

    The grid helps the LLM reference precise screen locations by number.
    Each cell is labeled with its (col, row) index. Grid lines are drawn
    semi-transparently so the underlying content stays visible.
    """
    overlay = img.copy()
    draw = ImageDraw.Draw(overlay)
    w, h = img.size

    # Load a small font for labels
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except Exception:
        font = ImageFont.load_default()

    # Draw vertical and horizontal lines
    col = 0
    for x in range(0, w, grid_size):
        draw.line([(x, 0), (x, h)], fill=(255, 0, 0, 128), width=1)
        col += 1
    row = 0
    for y in range(0, h, grid_size):
        draw.line([(0, y), (w, y)], fill=(255, 0, 0, 128), width=1)
        row += 1

    # Label each cell with coordinates
    col_idx = 0
    for x in range(0, w, grid_size):
        row_idx = 0
        for y in range(0, h, grid_size):
            label = f"{col_idx},{row_idx}"
            # Background for readability
            bbox = draw.textbbox((x + 2, y + 1), label, font=font)
            draw.rectangle(bbox, fill=(0, 0, 0, 180))
            draw.text((x + 2, y + 1), label, fill=(255, 255, 0), font=font)
            row_idx += 1
        col_idx += 1

    return overlay


def capture_screen(
    region: tuple = None,
    monitor: int = None,
    window_title: str = None,
    cursor: bool = False,
    img_format: str = "png",
    quality: int = 85,
    active: bool = False,
    grid: bool = False,
    grid_size: int = 100,
) -> dict:
    """
    Capture screen and return base64 encoded image.

    Args:
        region: Optional (left, top, right, bottom) bbox.
        monitor: Monitor index (0 = all monitors combined, 1+ = specific).
        window_title: Optional window title substring to capture (Windows only).
        cursor: If True, overlay cursor position on the image.
        img_format: "png" (lossless, default) or "jpeg" (smaller, faster).
        quality: JPEG quality 1-100 (default 85, only used for JPEG format).
        active: If True, capture only the active/foreground window.
    """
    try:
        # ── Active window shortcut ─────────────────────────────────────────────
        if active:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            if title:
                return capture_screen(window_title=title, cursor=cursor, img_format=img_format, quality=quality)
            return {"success": False, "error": "No active window found"}

        # ── Normalize region: accept dict {left,top,width,height} OR tuple (l,t,r,b) ─
        normalized_region = region
        if isinstance(normalized_region, dict):
            l = int(normalized_region.get("left", 0))
            t = int(normalized_region.get("top", 0))
            w = int(normalized_region.get("width", 0))
            h = int(normalized_region.get("height", 0))
            normalized_region = (l, t, l + w, t + h)
        elif normalized_region is not None:
            normalized_region = tuple(int(v) for v in normalized_region)

        # ── Per-window capture ───────────────────────────────────────────────
        if window_title:
            img = _capture_window(window_title)
            if img is None:
                return {
                    "success": False,
                    "error": f"Window '{window_title}' not found or could not be captured",
                }
        else:
            monitor_idx = monitor if monitor is not None else 0

            if _mss_available:
                try:
                    img = _grab_mss(monitor_idx=monitor_idx, region=normalized_region)
                except Exception as _mss_err:
                    logger.debug(f"mss grab failed ({_mss_err}), falling back to PIL")
                    img = _grab_pil(region=normalized_region)
            elif _pil_grab_available:
                img = _grab_pil(region=normalized_region)
            else:
                return {"success": False, "error": "No screen capture backend available (mss or Pillow)"}

        if img is None:
            return {"success": False, "error": "Capture returned no image"}

        # ── Cursor overlay ───────────────────────────────────────────────────
        if cursor:
            img = _overlay_cursor(img)

        # ── Grid overlay ─────────────────────────────────────────────────────
        if grid:
            img = _overlay_grid(img, grid_size)

        # ── Resize to limit token bloat ──────────────────────────────────────
        max_dim = 1280
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        # ── Encode ───────────────────────────────────────────────────────────
        buffer = io.BytesIO()
        if img_format == "jpeg":
            img = img.convert("RGB")
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
        else:
            img.save(buffer, format="PNG", optimize=True)

        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return {
            "image_b64": b64,
            "width": img.width,
            "height": img.height,
            "success": True,
            "monitor": monitor if monitor is not None else 0,
            "format": img_format,
            "cursor_overlay": cursor,
            "grid_overlay": grid,
            "grid_size": grid_size if grid else None,
        }
    except Exception as e:
        logger.error(f"capture_screen failed: {e}")
        return {"success": False, "error": str(e)}


def capture_active_window(cursor: bool = False, img_format: str = "png") -> dict:
    """Capture the currently active/foreground window."""
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        if title:
            return capture_screen(window_title=title, cursor=cursor, img_format=img_format)
        return {"success": False, "error": "No active window found"}
    except Exception as e:
        return {"success": False, "error": str(e)}