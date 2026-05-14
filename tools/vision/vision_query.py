"""
vision_query — ask a targeted question about what's on screen.

Combines capture_screen + vision model inference into a single tool call.
gpt-oss 120b cannot process images, so this is the correct way to answer
any visual question: call vision_query(question="...") and get plain text back.

Design
------
- Always captures a fresh screenshot (no stale-image risk from prior calls).
- Sends the screenshot + question to gemma3:27b-cloud via the same endpoint
  already used by verification/vision_summary.py.
- Returns {success, answer, width, height} — never raw base64 into context.
- Never raises: failures return {success: False, error: ...}.

When to use
-----------
Use vision_query instead of capture_screen when:
  • You need to know what's on the screen before deciding the next action
  • You need pixel-level detail (button positions, dialog text, error messages)
  • You need a targeted answer ("is there an error dialog?", "what tab is active?")

Do NOT use vision_query as a verification step after every tool call —
that adds latency. Only call it when visual content is the actual goal.
"""

from __future__ import annotations

import base64
import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)


def vision_query(question: str, region: dict | None = None) -> dict:
    """
    Capture the screen and ask gemma3:27b a specific question about it.

    Parameters
    ----------
    question : str
        What you want to know about the current screen state.
        Be specific: "Is there an error dialog open?" is better than "what do you see?".
    region : dict, optional
        Crop region {"left": x, "top": y, "width": w, "height": h}.
        Omit for full-desktop capture.

    Returns
    -------
    dict
        {
            "success": bool,
            "answer":  str,   # gemma3's plain-text response
            "width":   int,   # screenshot dimensions (useful for coordinate math)
            "height":  int,
            "error":   str,   # only present on failure
        }
    """
    # ── Step 1: capture ──────────────────────────────────────────────────────
    try:
        import mss

        with mss.mss() as sct:
            if region is not None:
                mon = {
                    "left": region["left"],
                    "top": region["top"],
                    "width": region["width"],
                    "height": region["height"],
                }
            else:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        max_dim = 1280
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        width, height = img.width, img.height
    except Exception as exc:
        logger.error(f"vision_query: capture step failed — {exc}")
        return {"success": False, "error": f"Capture error: {exc}", "answer": ""}

    # ── Step 2: ask gemma3 ───────────────────────────────────────────────────
    try:
        import requests
        from settings import LLM_TIMEOUT, LLM_VISION_MODEL, OLLAMA_API_KEY
        from verification.vision_summary import _vision_endpoint

        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

        endpoint = _vision_endpoint()

        # Prompt is question-driven: gemma3 answers specifically what gpt-oss asked.
        # Keeping the prompt tight prevents verbose scene descriptions when all
        # gpt-oss needs is a yes/no or a coordinate.
        system_prompt = (
            "You are a visual assistant integrated into a desktop automation agent. "
            "Answer the question about the screenshot concisely and precisely. "
            "If coordinates are relevant, describe positions as fractions of screen width/height "
            f"(screen is {width}x{height} px). "
            "Do not describe the whole screen unless asked — answer only what was asked."
        )

        payload = {
            "model": LLM_VISION_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": question,
                    "images": [image_b64],
                },
            ],
            "stream": False,
            "temperature": 0.1,  # low temp: factual visual answers, not creative
        }

        logger.debug(
            f"vision_query: posting to {endpoint} "
            f"model={LLM_VISION_MODEL} question={question[:80]!r}"
        )

        resp = requests.post(
            endpoint, json=payload, headers=headers, timeout=LLM_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()

        # Support both OpenAI-compatible and native Ollama response shapes
        if "choices" in data:
            answer = (
                data["choices"][0].get("message", {}).get("content", "").strip()
            )
        else:
            answer = data.get("message", {}).get("content", "").strip()

        if not answer:
            return {
                "success": False,
                "error": "Vision model returned an empty response",
                "answer": "",
                "width": width,
                "height": height,
            }

        logger.info(
            f"vision_query: answered ({len(answer)} chars) for question={question[:60]!r}"
        )
        return {
            "success": True,
            "answer": answer,
            "width": width,
            "height": height,
        }

    except Exception as exc:
        logger.error(f"vision_query: inference step failed — {exc}")
        return {
            "success": False,
            "error": f"Vision inference error: {exc}",
            "answer": "",
            "width": width if "width" in locals() else 0,
            "height": height if "height" in locals() else 0,
        }
