"""
3-tier verification router. Returns structured dict.

Tier 0: result.success check
Tier 1: OS-level state check (expected vs actual)
Tier 2: output cross-check for execute_code silent failures
"""

import logging
import re

logger = logging.getLogger(__name__)


def verify_action(tool_name: str, result: dict, expected: str = "") -> dict:
    state = result.get("data", {})

    # Tier 0: result.success check
    if result.get("success") is False:
        return {
            "status": "FAILED",
            "method": "result",
            "summary": result.get("message") or f"{tool_name} failed.",
        }

    # Tier 1: OS-level state verification (expected vs actual) for window/app tools
    app_tools = {"open_app", "close_app", "focus_window", "switch_window", "launch"}
    if tool_name in app_tools:
        from verification.state_checks import verify_process_running, verify_window_visible

        app_name = str(state.get("name", "") or result.get("message", ""))
        # Strip prefix like "launched " or "focused " or "closed " — keep just the app name
        for prefix in ("launched ", "focused ", "closed ", "killed ", "minimized ", "maximized "):
            if app_name.startswith(prefix):
                app_name = app_name[len(prefix):]
                break
        # Also try the raw name from result data if available
        if not app_name:
            app_name = state.get("name", "")

        if app_name:
            # Poll briefly — apps need time to start
            import time as _time
            for _ in range(6):
                process_ok = verify_process_running(app_name)
                window_ok = verify_window_visible(app_name)
                if process_ok or window_ok:
                    break
                _time.sleep(0.5)
            else:
                return {
                    "status": "FAILED",
                    "method": "state_check",
                    "summary": f"Expected {tool_name}({app_name}) but no matching process or window found after polling.",
                    "state_checks": {"process": process_ok, "window": window_ok},
                }

    # Tier 2: output cross-check for execute_code silent failures
    if tool_name == "execute_code":
        out_result = _check_output_for_failures(result)
        if out_result:
            return {
                "status": "FAILED",
                "method": "output_check",
                "summary": out_result,
            }

    # Tier 3: post-action state check for interaction tools
    interaction_tools = {"click", "double_click", "right_click", "type_text", "press_keys"}
    if tool_name in interaction_tools and expected:
        from verification.state_checks import verify_window_visible
        # If the expected outcome mentions a window that should appear/disappear,
        # check its state
        for prefix in ("close ", "kill ", "exit "):
            if expected.lower().startswith(prefix):
                target = expected[len(prefix):].strip().split()[0]
                if verify_window_visible(target):
                    return {
                        "status": "FAILED",
                        "method": "post_action_check",
                        "summary": f"Action was to close '{target}' but window is still visible.",
                    }
                return {
                    "status": "CONFIRMED",
                    "method": "post_action_check",
                    "summary": f"Window '{target}' is no longer visible — action verified.",
                }

    return {
        "status": "CONFIRMED",
        "method": "result",
        "summary": f"{tool_name} completed.",
    }


_FAILURE_PATTERNS = re.compile(
    r"^(.*\b(ERROR|Traceback|Exception|Failed|CRITICAL)\b.*)$",
    re.MULTILINE,
)


def _check_output_for_failures(result: dict) -> str:
    """
    Check the tool's own output and error fields for failure signals.
    Returns a human-readable summary if failures found, or empty string if clean.
    This avoids false positives from unrelated errors in the shared application log.
    """
    try:
        outputs = []

        error_field = result.get("error", "")
        if error_field:
            outputs.append(error_field)

        output_field = result.get("output", "")
        if output_field:
            outputs.append(output_field)

        if not outputs:
            return ""

        combined = "\n".join(outputs)

        matches = _FAILURE_PATTERNS.findall(combined)
        if not matches:
            return ""

        seen: set[str] = set()
        failure_lines: list[str] = []
        for full_line, *_ in reversed(matches):
            key = full_line.strip()
            if key and key not in seen:
                seen.add(key)
                failure_lines.append(key)
                if len(failure_lines) >= 3:
                    break

        if failure_lines:
            snippet = " | ".join(reversed(failure_lines))
            return f"Tool output shows errors: {snippet}"

        return ""

    except Exception as exc:
        logger.debug(f"Output check skipped: {exc}")
        return ""
