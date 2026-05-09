
"""
Tier 2: Regional OCR text match. ~0.5-1.5s.
"""
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from PIL import ImageGrab
    _ocr_available = True
except ImportError:
    _ocr_available = False

# ── Windows: auto-detect Tesseract binary ────────────────────────────────────
if _ocr_available and sys.platform == "win32":
    # If the user hasn't already configured it, try common install paths
    if not pytesseract.pytesseract.tesseract_cmd or not Path(
        pytesseract.pytesseract.tesseract_cmd
    ).exists():
        _candidates = [
            shutil.which("tesseract"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            str(Path.home() / "AppData" / "Local" / "Tesseract-OCR" / "tesseract.exe"),
            str(Path.home() / "scoop" / "apps" / "tesseract" / "current" / "tesseract.exe"),
            str(Path.home() / "tools" / "Tesseract-OCR" / "tesseract.exe"),
        ]
        for _cand in _candidates:
            if _cand and Path(_cand).exists():
                pytesseract.pytesseract.tesseract_cmd = _cand
                logger.debug(f"OCR: auto-detected tesseract at {_cand}")
                break
        else:
            logger.warning(
                "OCR: tesseract.exe not found in common paths. "
                "Set pytesseract.pytesseract.tesseract_cmd manually or install Tesseract."
            )

def verify_text_on_screen(target_text: str, region: tuple = None) -> bool:
    if not _ocr_available: return False
    try:
        img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
        text = pytesseract.image_to_string(img).lower()
        return target_text.lower() in text
    except Exception as e:
        logger.warning(f"OCR failed: {e}")
        return False
