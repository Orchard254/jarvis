"""
Multi-signal confidence gate.
Combines per-tool confidence with LLM uncertainty detection and action risk.
"""

import logging

from settings import CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)

# Phrases that strongly indicate LLM uncertainty — significantly reduce confidence
_HIGH_UNCERTAINTY_PHRASES = [
    "i'm not sure",
    "i am not sure",
    "i don't know",
    "i do not know",
    "not confident",
    "not certain",
    "might cause issues",
    "could break",
    "irreversible",
    "cannot guarantee",
    "unsure whether",
    "risky operation",
    "potentially dangerous",
    "this could go wrong",
]

# Phrases that mildly suggest uncertainty — slightly reduce confidence
_MILD_UNCERTAINTY_PHRASES = [
    "might",
    "probably",
    "possibly",
    "i think",
    "perhaps",
    "maybe",
    "should work",
    "likely",
    "i believe",
    "seems like",
    "approximately",
    "i assume",
    "roughly",
    "i expect",
]

# Tools where a higher effective threshold is enforced
_HIGH_RISK_TOOLS = frozenset(
    {"execute_code", "exec", "control_input", "input", "write_file", "file_ops", "process_manager"}
)
_MEDIUM_RISK_TOOLS = frozenset(
    {"control_window", "window", "system_settings", "browser", "clipboard"}
)


def check(plan: dict) -> tuple[bool, str]:
    """
    Multi-signal confidence gate.

    Args:
        plan: dict with keys:
            - confidence: float (required) — base confidence from orchestrator
            - llm_response: str (optional) — LLM content text to scan for uncertainty
            - tool_name: str (optional) — for per-tool risk escalation
            - destructive: bool (optional) — explicit destructive flag

    Returns:
        (ok: bool, reason: str) — reason is empty string when ok=True
    """
    base_confidence = plan.get("confidence", 1.0)
    llm_response = plan.get("llm_response", "")
    tool_name = plan.get("tool_name", "")
    destructive = plan.get("destructive", False)

    confidence = float(base_confidence)

    # ── Signal 1: LLM response uncertainty analysis ────────────────────────
    if llm_response:
        text = llm_response.lower()
        found_high = next((p for p in _HIGH_UNCERTAINTY_PHRASES if p in text), None)
        if found_high:
            confidence *= 0.70
            logger.debug(
                f"confidence_gate: high-uncertainty '{found_high}' → {confidence:.2f}"
            )
        else:
            found_mild = next((p for p in _MILD_UNCERTAINTY_PHRASES if p in text), None)
            if found_mild:
                confidence *= 0.88
                logger.debug(
                    f"confidence_gate: mild-uncertainty '{found_mild}' → {confidence:.2f}"
                )

    # ── Signal 2: Explicit destructive flag ───────────────────────────────
    if destructive:
        confidence = min(confidence, 0.75)
        logger.debug(f"confidence_gate: destructive=True → capped at {confidence:.2f}")

    # ── Threshold selection ────────────────────────────────────────────────
    threshold = float(CONFIDENCE_THRESHOLD)
    if tool_name in _HIGH_RISK_TOOLS:
        threshold = max(threshold, 0.72)
    elif tool_name in _MEDIUM_RISK_TOOLS:
        threshold = max(threshold, 0.68)

    if confidence >= threshold:
        return True, ""

    reason = (
        f"Confidence {confidence:.2f} (base {base_confidence:.2f}) "
        f"below threshold {threshold:.2f} for tool '{tool_name or 'unknown'}'"
    )
    logger.info(f"confidence_gate: BLOCKED — {reason}")
    return False, reason
