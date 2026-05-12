"""Vision-guided screen element finder."""

import json
import logging
import re

logger = logging.getLogger(__name__)


def find_on_screen(
    description: str,
    click: bool = False,
    region: dict = None,
) -> dict:
    """
    Find a UI element on screen by description using vision AI.
    Optionally click the found element.
    Returns coordinates of the element.
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

    # capture_screen accepts region as a tuple (left, top, width, height)
    # The public API uses a dict; convert if provided
    region_arg = None
    if region:
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

    # ── 2. Ask vision LLM to locate the element ──────────────────────────────
    try:
        import requests
        from settings import LLM_TIMEOUT, LLM_VISION_MODEL, OLLAMA_API_KEY
        from verification.vision_summary import _vision_endpoint

        prompt = (
            f'Look at this screenshot carefully. Find the UI element described as: "{description}". '
            "Respond with ONLY a JSON object (no markdown, no explanation): "
            '{"found": true, "x": <center_x_pixels>, "y": <center_y_pixels>, '
            '"width": <element_width>, "height": <element_height>, '
            '"confidence": <0.0_to_1.0>, "description": "<what you found>"} '
            'OR if not found: {"found": false, "description": "<why not found>"}'
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

        # Parse response — support both OpenAI-compatible and native Ollama shapes
        if "choices" in data:
            raw_content = data["choices"][0].get("message", {}).get("content", "")
        else:
            raw_content = data.get("message", {}).get("content", "")

        # Strip markdown code fences if present
        raw_content = re.sub(
            r"^```[a-z]*\s*", "", raw_content.strip(), flags=re.IGNORECASE
        )
        raw_content = re.sub(r"\s*```$", "", raw_content.strip())

        result_json = json.loads(raw_content)

    except Exception as e:
        logger.error(f"find_on_screen vision LLM error: {e}")
        return {"success": False, "found": False, "error": "Vision LLM unavailable"}

    # ── 3. Interpret LLM result ───────────────────────────────────────────────
    found = bool(result_json.get("found", False))
    elem_description = result_json.get("description", "")

    if not found:
        return {
            "success": True,
            "found": False,
            "description": elem_description,
            "clicked": False,
            "action": "find_on_screen",
        }

    x = int(result_json.get("x", 0))
    y = int(result_json.get("y", 0))
    width = int(result_json.get("width", 0))
    height = int(result_json.get("height", 0))
    confidence = float(result_json.get("confidence", 0.0))

    # ── 4. Optionally click ───────────────────────────────────────────────────
    clicked = False
    if click:
        try:
            from tools.control_input import control_input

            click_result = control_input("click", {"x": x, "y": y})
            clicked = click_result.get("success", False)
        except Exception as e:
            logger.warning(f"find_on_screen click failed: {e}")

    return {
        "success": True,
        "found": True,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "confidence": confidence,
        "description": elem_description,
        "clicked": clicked,
        "action": "find_on_screen",
    }
