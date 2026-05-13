
"""
Tier 2: Regional OCR text match. ~0.5-1.5s.

Provides both boolean verification (verify_text_on_screen) and
positional text finding (find_text_on_screen) for clicking on text.
"""

import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from PIL import ImageGrab
    _ocr_available = True
except ImportError:
    _ocr_available = False

# ── Windows: auto-detect Tesseract binary ────────────────────────────────────
if _ocr_available and sys.platform == "win32":
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
    """Check if text appears anywhere on screen (or region). Returns True/False."""
    if not _ocr_available:
        return False
    try:
        img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
        text = pytesseract.image_to_string(img).lower()
        return target_text.lower() in text
    except Exception as e:
        logger.warning(f"OCR failed: {e}")
        return False


def _box_center(box) -> tuple:
    """Return (x, y) center pixel from a Tesseract OCR box dict."""
    xs = [box.get(k, 0) for k in ("x", "left", "x1")]
    ys = [box.get(k, 0) for k in ("y", "top", "y1")]
    w = box.get("width", 0) or (box.get("right", 0) - xs[0])
    h = box.get("height", 0) or (box.get("bottom", 0) - ys[0])
    return (xs[0] + w // 2, ys[0] + h // 2)


def find_text_on_screen(
    target_text: str,
    region: tuple = None,
    fuzzy: bool = True,
) -> list:
    """
    Find text on screen and return list of match locations with bounding boxes.

    Args:
        target_text: Text to search for (case-insensitive).
        region: Optional (left, top, right, bottom) bbox to constrain search.
        fuzzy: If True, matches substrings (default). If False, exact word match.

    Returns:
        List of dicts:
            {"text": str, "confidence": float, "x": int, "y": int,
             "width": int, "height": int, "center_x": int, "center_y": int}
        Empty list if text not found or OCR unavailable.
    """
    if not _ocr_available:
        return []

    results = []
    try:
        from PIL import ImageGrab

        img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
        offset_x = region[0] if region else 0
        offset_y = region[1] if region else 0

        # Get word-level data with bounding boxes
        word_data = pytesseract.image_to_data(
            img, output_type=pytesseract.Output.DICT
        )

        target_lower = target_text.lower()
        n = len(word_data.get("text", []))

        # Collect matching word entries
        matches = []
        for i in range(n):
            word = (word_data["text"][i] or "").strip()
            if not word:
                continue
            raw_conf = word_data.get("conf", [None])[i]
            if raw_conf is None:
                conf = 0
            elif isinstance(raw_conf, int):
                conf = max(raw_conf, 0)
            elif isinstance(raw_conf, str) and raw_conf.strip().lstrip("-").isdigit():
                conf = max(int(raw_conf), 0)
            else:
                conf = 0

            if fuzzy:
                matched = target_lower in word.lower()
            else:
                matched = word.lower() == target_lower

            if matched:
                x = int(word_data.get("left", [0])[i]) + offset_x
                y = int(word_data.get("top", [0])[i]) + offset_y
                w = int(word_data.get("width", [0])[i])
                h = int(word_data.get("height", [0])[i])
                matches.append({
                    "text": word,
                    "confidence": conf / 100.0,
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "center_x": x + w // 2,
                    "center_y": y + h // 2,
                })

        # Merge adjacent matches for multi-word targets
        if fuzzy and len(target_text.split()) > 1:
            merged = _merge_ocr_matches(matches, target_lower)
            if merged:
                return merged

        return matches

    except Exception as e:
        logger.warning(f"find_text_on_screen failed: {e}")
        return []


def _merge_ocr_matches(matches: list, target_lower: str) -> list:
    """
    Attempt to merge adjacent word-level OCR matches into a single
    bounding box for multi-word targets. Returns merged list or empty.
    """
    if not matches:
        return []

    matches_sorted = sorted(matches, key=lambda m: (m["y"], m["x"]))
    combined_text = " ".join(m["text"] for m in matches_sorted).lower()

    if target_lower in combined_text:
        x1 = min(m["x"] for m in matches_sorted)
        y1 = min(m["y"] for m in matches_sorted)
        x2 = max(m["x"] + m["width"] for m in matches_sorted)
        y2 = max(m["y"] + m["height"] for m in matches_sorted)
        avg_conf = sum(m["confidence"] for m in matches_sorted) / len(matches_sorted)
        return [{
            "text": target_lower,
            "confidence": avg_conf,
            "x": x1,
            "y": y1,
            "width": x2 - x1,
            "height": y2 - y1,
            "center_x": (x1 + x2) // 2,
            "center_y": (y1 + y2) // 2,
        }]

    return matches
