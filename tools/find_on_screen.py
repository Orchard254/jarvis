"""Vision-guided and OCR-based screen element finder."""

import json
import logging
import re

logger = logging.getLogger(__name__)


def _validate_coords(x, y, screen_width, screen_height) -> bool:
    """Check if coordinates fall within screen bounds."""
    return 0 <= x <= screen_width and 0 <= y <= screen_height


def _parse_llm_json(raw_content: str) -> dict:
    """Parse JSON from LLM response, stripping markdown fences."""
    raw_content = re.sub(r"^```[a-z]*\s*", "", raw_content.strip(), flags=re.IGNORECASE)
    raw_content = re.sub(r"\s*```$", "", raw_content.strip())
    return json.loads(raw_content)


def find_on_screen(
    description: str,
    click: bool = False,
    region: dict = None,
    multiple: bool = False,
) -> dict:
    """
    Find a UI element on screen by description using vision AI or OCR text match.
    Optionally click the found element.
    Returns coordinates of the element.

    For text-based elements (buttons, labels, links), the method first tries
    OCR-based location for speed, then falls back to vision LLM.
    """
    # ── 1. Capture screenshot ────────────────────────────────────────────────
    try:
        from tools.capture_screen import capture_screen
    except ImportError:
        return {
            "success": False,
            "found": False,
            "error": "capture_screen tool not available",
        }

    region_arg = None
    if region and isinstance(region, dict):
        try:
            region_arg = (
                int(region["left"]),
                int(region["top"]),
                int(region["left"]) + int(region["width"]),
                int(region["top"]) + int(region["height"]),
            )
        except (KeyError, TypeError, ValueError):
            region_arg = None

    sc = capture_screen(region=region_arg)
    if not sc.get("success"):
        return {
            "success": False,
            "found": False,
            "error": sc.get("error", "Screenshot failed"),
        }

    image_b64 = sc["image_b64"]
    screen_width = sc["width"]
    screen_height = sc["height"]

    # ── 2. Try OCR first for text-based descriptions ─────────────────────────
    ocr_result = _try_ocr_match(description, region_arg)
    if ocr_result:
        x, y, w, h, conf, matched_text = ocr_result
        if _validate_coords(x, y, screen_width, screen_height):
            clicked = _do_click(click, x, y)
            return {
                "success": True,
                "found": True,
                "method": "ocr",
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "center_x": x + w // 2,
                "center_y": y + h // 2,
                "confidence": conf,
                "description": matched_text,
                "clicked": clicked,
            }

    # ── 3. Ask vision LLM to locate the element ──────────────────────────────
    try:
        import requests
        from settings import LLM_TIMEOUT, LLM_VISION_MODEL, OLLAMA_API_KEY
        from verification.vision_summary import _vision_endpoint

        multiple_instruction = (
            'Respond with a JSON array of objects if "multiple" elements exist. '
            'If only one, return a single object (not an array). '
        ) if multiple else ""

        prompt = (
            f'Look at this screenshot carefully. Find the UI element described as: "{description}". '
            f'{multiple_instruction}'
            "Respond with ONLY a JSON object (no markdown, no explanation): "
            '{"found": true, "x": <center_x_pixels>, "y": <center_y_pixels>, '
            '"width": <element_width>, "height": <element_height>, '
            '"confidence": <0.0_to_1.0>, "description": "<what you found>"} '
            'OR if not found: {"found": false, "description": "<why not found>"}. '
            f"The screen resolution is {screen_width}x{screen_height}. "
            "Make sure coordinates are within these bounds."
        )

        payload = {
            "model": LLM_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            "stream": False,
            "temperature": 0.1,
        }

        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

        endpoint = _vision_endpoint()
        resp = requests.post(
            endpoint, json=payload, headers=headers, timeout=LLM_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()

        if "choices" in data:
            raw_content = data["choices"][0].get("message", {}).get("content", "")
        else:
            raw_content = data.get("message", {}).get("content", "")

        result_json = _parse_llm_json(raw_content)

    except Exception as e:
        logger.error(f"find_on_screen vision LLM error: {e}")
        return {"success": False, "found": False, "error": "Vision LLM unavailable"}

    # ── 4. Handle multiple results ────────────────────────────────────────────
    if multiple and isinstance(result_json, list):
        elements = []
        for elem in result_json:
            if not elem.get("found"):
                continue
            parsed = _parse_element_result(elem, click, screen_width, screen_height)
            if parsed:
                elements.append(parsed)
        return {
            "success": True,
            "found": len(elements) > 0,
            "count": len(elements),
            "elements": elements,
            "action": "find_on_screen",
        }

    # ── 5. Handle single result ───────────────────────────────────────────────
    found_val = result_json.get("found", False)
    if isinstance(found_val, str):
        found = found_val.lower() in ("true", "1", "yes")
    else:
        found = bool(found_val)
    elem_description = result_json.get("description", "")

    if not found:
        return {
            "success": True,
            "found": False,
            "description": elem_description,
            "clicked": False,
            "action": "find_on_screen",
        }

    parsed = _parse_element_result(result_json, click, screen_width, screen_height)
    if not parsed:
        return {
            "success": True,
            "found": False,
            "description": f"Coordinates out of bounds for: {elem_description}",
            "clicked": False,
            "action": "find_on_screen",
        }

    return parsed


def _try_ocr_match(description: str, region: tuple = None):
    """Try to find an element by matching its text description via OCR.

    Returns (x, y, width, height, confidence, matched_text) or None.
    """
    try:
        from verification.ocr_match import find_text_on_screen

        # Extract likely button/label text from description
        # Strip common prefixes like "the", "a", "button", "icon", etc.
        cleaned = re.sub(
            r"(?i)^(the|a|an)\s+",
            "",
            description,
        )
        cleaned = re.sub(
            r"(?i)\s+(button|icon|link|tab|menu|item|field|label|box|input|dropdown|checkbox|radio)$",
            "",
            cleaned,
        ).strip()

        # Try the full cleaned text first
        matches = find_text_on_screen(cleaned, region=region)
        if matches:
            best = max(matches, key=lambda m: m["confidence"])
            return (
                best["center_x"],
                best["center_y"],
                best["width"],
                best["height"],
                best["confidence"],
                best["text"],
            )

        # Fallback: search for each word individually (only if multi-word query)
        words = cleaned.split()
        if len(words) > 1:
            # For multi-word descriptions, require all words found
            all_matches = []
            for word in words:
                if len(word) < 2:
                    continue
                matches = find_text_on_screen(word, region=region)
                all_matches.append(matches)
            if all(ms for ms in all_matches):
                # Use the last word's match as the position (most specific)
                best = max(all_matches[-1], key=lambda m: m["confidence"])
                return (
                    best["center_x"],
                    best["center_y"],
                    best["width"],
                    best["height"],
                    best["confidence"],
                    best["text"],
                )
            return None

    except Exception as e:
        logger.debug(f"OCR match attempt failed: {e}")

    return None


def _parse_element_result(result_json: dict, click: bool, screen_width: int, screen_height: int) -> dict:
    """Parse a single element result from vision JSON, validating coordinates."""
    def _safe_int(v, default=0):
        if isinstance(v, list):
            return default
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    x = _safe_int(result_json.get("x", 0))
    y = _safe_int(result_json.get("y", 0))
    width = _safe_int(result_json.get("width", 0))
    height = _safe_int(result_json.get("height", 0))
    confidence = float(result_json.get("confidence", 0.0) or 0)
    elem_description = result_json.get("description", "")

    if not _validate_coords(x, y, screen_width, screen_height):
        logger.warning(
            f"find_on_screen: coords ({x}, {y}) out of bounds "
            f"({screen_width}x{screen_height}) — rejecting"
        )
        return None

    clicked = _do_click(click, x, y)

    return {
        "success": True,
        "found": True,
        "method": "vision",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "center_x": x,
        "center_y": y,
        "confidence": confidence,
        "description": elem_description,
        "clicked": clicked,
        "action": "find_on_screen",
    }


def _do_click(click: bool, x: int, y: int) -> bool:
    """Execute a click at (x, y) if requested."""
    if not click:
        return False
    try:
        from tools.control_input import control_input
        click_result = control_input("click", {"x": x, "y": y})
        return click_result.get("success", False)
    except Exception as e:
        logger.warning(f"find_on_screen click failed: {e}")
        return False