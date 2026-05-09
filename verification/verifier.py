"""
3-tier router. Returns structured text report ONLY.
"""

import logging

from tools.capture_screen import capture_screen

from verification.ocr_match import verify_text_on_screen
from verification.state_checks import verify_process_running, verify_window_visible
from verification.vision_summary import summarize_screen

logger = logging.getLogger(__name__)


def verify_action(tool_name: str, result: dict, expected: str = "") -> dict:
    if tool_name == "read_pc_state":
        if result.get("success") is False:
            return {
                "status": "FAILED",
                "method": "state_read",
                "summary": result.get("error") or "read_pc_state failed.",
            }
        return {
            "status": "CONFIRMED",
            "method": "state_read",
            "summary": "Desktop state retrieved.",
        }

    if tool_name in ("execute_code", "control_window", "open_app"):
        # Try window visibility with the expected string (any app, not just notepad)
        if expected and verify_window_visible(expected):
            return {
                "status": "CONFIRMED",
                "method": "state_check",
                "summary": f"Window '{expected}' visible.",
            }
        # Try process check as fallback
        if expected and verify_process_running(expected):
            return {
                "status": "CONFIRMED",
                "method": "process_check",
                "summary": f"Process '{expected}' is running.",
            }
        if result.get("returncode") == 0 or result.get("success"):
            return {
                "status": "CONFIRMED",
                "method": "return_code",
                "summary": f"{tool_name} succeeded.",
            }

    if expected and verify_text_on_screen(expected):
        return {
            "status": "CONFIRMED",
            "method": "ocr",
            "summary": f"Text '{expected}' found on screen.",
        }

    if result.get("image_b64"):
        summary = summarize_screen(result["image_b64"], expected)
        return {
            "status": "INCONCLUSIVE",
            "method": "vision_summary",
            "summary": summary,
        }

    return {
        "status": "FAILED",
        "method": "none",
        "summary": f"Verification inconclusive for {tool_name}.",
    }
