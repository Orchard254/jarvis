"""
Skill Runner — executes stored skills through the safety funnel and verifies outcomes.

Verification strategy (app-launch skills only):
  1. Detect whether the skill is an app-launch intent via keyword heuristics.
  2. Extract the most likely process name from the intent label and/or the
     skill code (exe references are more reliable than parsed intent text).
  3. Wait a short grace period so the OS has time to spawn the process.
  4. Call verification.state_checks.verify_process_running() — a sub-10ms
     deterministic psutil check.
  5. If the process is absent: flip result["success"] to False, attach
     diagnostic keys, and write a dedicated audit-log entry.
  6. Pass the (possibly corrected) success flag to record_run() so the
     skill-lifecycle state machine (promote / demote / retire) sees the
     true outcome, not just "did the code run without raising?".

Layer rules observed:
  • skills/ → safety/, verification/ : ALLOWED (infrastructure layers)
  • skills/ → brain/, core/          : FORBIDDEN (never happens here)
  • Config via settings.py only      : ALLOWED_IMPORTS not duplicated here
"""

from __future__ import annotations

import logging
import re
import sys
import time
from typing import Dict

from safety import audit_log
from safety.executor import execute
from settings import ENABLE_SKILLS
from tools import TOOL_REGISTRY

from skills.skill_store import get_skill, record_run

logger = logging.getLogger(__name__)

# ── Tunables (no .env keys needed — these are internal constants) ──────────────

# Seconds to wait after execution before probing the process list.
# Most GUI apps appear within 1 s; give 2 s to be safe without blocking long.
_VERIFICATION_GRACE_SECONDS: float = 2.0

# Intent-label keywords that indicate an app-launch skill.
# Checked against the *lowercased* intent_label.
_LAUNCH_KEYWORDS: frozenset[str] = frozenset(
    {
        "open",
        "launch",
        "start",
        "run",
        "execute",
        "load",
        "boot",
    }
)

# Words in intent labels that are NOT the app name — stripped before extraction.
_FILLER_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "app",
        "application",
        "program",
        "software",
        "please",
        "me",
        "my",
        "for",
    }
)

# Regex that pulls bare exe names out of skill code (e.g. 'notepad.exe').
_EXE_RE = re.compile(r"['\"](\w[\w.\-]+\.exe)['\"]", re.IGNORECASE)


# ── Public API ─────────────────────────────────────────────────────────────────


def run_skill(skill_id: str, intent: str) -> Dict:
    """
    Execute a stored skill through the safety funnel and verify its outcome.

    Returns a dict with at minimum:
        success           (bool)
        skill_id          (str)
        intent            (str)
        stdout / stderr   (str, may be empty)
        error             (str, may be empty)

    Additional keys present on verification failure:
        verification_failed  (bool, True)
        verified_app         (str)   — the process name we probed
    """
    if not ENABLE_SKILLS:
        return {
            "success": False,
            "error": "Skills disabled",
            "skill_id": skill_id,
            "intent": intent,
        }

    skill = get_skill(skill_id)
    if not skill:
        return {
            "success": False,
            "error": "Skill not found",
            "skill_id": skill_id,
            "intent": intent,
        }

    if skill["status"] == "retired":
        return {
            "success": False,
            "error": "Skill retired",
            "skill_id": skill_id,
            "intent": intent,
        }

    try:
        tool_name = "execute_code"
        tool_fn = TOOL_REGISTRY[tool_name]
        args = {"code": skill["code"], "language": skill["language"]}

        # ── 1. Execute through the safety funnel ──────────────────────────────
        result = execute(
            tool_name=tool_name,
            tool_fn=tool_fn,
            args=args,
            plan={"confidence": 0.95, "source": f"skill:{skill_id}"},
        )

        # ── 2. Post-execution verification (app-launch skills only) ───────────
        if result.get("success") and _is_launch_skill(skill["intent_label"]):
            app_name = _extract_app_name(skill["intent_label"], skill.get("code", ""))

            if app_name:
                # Give the OS a moment to spawn the process before probing.
                # Use non-blocking wait on Windows to allow message pumping
                if sys.platform == "win32":
                    import pythoncom
                    deadline = time.monotonic() + _VERIFICATION_GRACE_SECONDS
                    while time.monotonic() < deadline:
                        pythoncom.PumpWaitingMessages()
                        time.sleep(0.05)  # Small sleep to avoid busy-waiting
                else:
                    time.sleep(_VERIFICATION_GRACE_SECONDS)

                # Lazy import keeps the verification layer out of module-load
                # critical path and makes unit-testing easier to mock.
                from verification.state_checks import verify_process_running  # noqa

                process_found = verify_process_running(app_name)

                if not process_found:
                    # Execution "succeeded" (no Python exception, exit-code 0)
                    # but the target process is absent — treat as a real failure.
                    result["success"] = False
                    result["verification_failed"] = True
                    result["verified_app"] = app_name
                    result["error"] = (
                        result.get("error")
                        or f"App '{app_name}' did not launch (process not found)"
                    )

                    logger.warning(
                        f"skill_runner: verification FAILED for skill "
                        f"'{skill_id[:8]}' — '{app_name}' not running after "
                        f"{_VERIFICATION_GRACE_SECONDS}s"
                    )

                    # Write a dedicated audit entry so the failure is visible in
                    # audit.log independently of the original execute() log call.
                    audit_log.log_call(
                        tool_name="skill_verification",
                        args={
                            "skill_id": skill_id,
                            "intent_label": skill["intent_label"],
                            "verified_app": app_name,
                        },
                        result={
                            "success": False,
                            "error": result["error"],
                            "verification_failed": True,
                        },
                    )
                else:
                    logger.info(
                        f"skill_runner: verification PASSED for skill "
                        f"'{skill_id[:8]}' — '{app_name}' is running"
                    )
            else:
                # Could not determine an app name — skip verification rather
                # than incorrectly marking a successful skill as failed.
                logger.debug(
                    f"skill_runner: launch skill '{skill_id[:8]}' — "
                    "could not extract app name, skipping process check"
                )

        # ── 3. Record outcome (now reflects verification result) ──────────────
        success = result.get("success", False)
        record_run(skill_id, success)

        return {
            "success": success,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "error": result.get("error", ""),
            "skill_id": skill_id,
            "intent": intent,
            # Propagate verification metadata when present
            **(
                {
                    "verification_failed": result["verification_failed"],
                    "verified_app": result.get("verified_app", ""),
                }
                if result.get("verification_failed")
                else {}
            ),
        }

    except Exception as exc:
        logger.error(
            f"skill_runner: skill '{skill_id[:8]}' raised unexpectedly: {exc}",
            exc_info=True,
        )
        record_run(skill_id, False)
        return {
            "success": False,
            "error": str(exc),
            "skill_id": skill_id,
            "intent": intent,
        }


# ── Internal helpers ───────────────────────────────────────────────────────────


def _is_launch_skill(intent_label: str) -> bool:
    """
    Return True if the intent label suggests this skill launches an application.

    Checks the first *meaningful* token of the intent against _LAUNCH_KEYWORDS
    so that labels like "open calculator", "launch notepad", "start vlc" all
    trigger verification, while "list files" or "write a report" do not.
    """
    tokens = intent_label.lower().split()
    # The launch keyword is almost always the first word, but search the first
    # three tokens to tolerate labels like "please open notepad".
    return bool(tokens) and any(t in _LAUNCH_KEYWORDS for t in tokens[:3])


def _extract_app_name(intent_label: str, code: str) -> str | None:
    """
    Heuristically extract the most likely process name to verify.

    Priority order:
      1. Bare .exe name found in the skill code  (most precise)
      2. Last non-filler word in the intent label after stripping filler words
         (handles "open calculator", "launch the browser", etc.)

    Returns a short string suitable for passing to verify_process_running(),
    or None if no plausible name could be extracted.
    """
    # ── Priority 1: exe reference in code ─────────────────────────────────────
    exe_matches = _EXE_RE.findall(code)
    if exe_matches:
        # Return the stem (without .exe) — psutil names often omit the extension
        # but verify_process_running does substring matching so either works.
        raw = exe_matches[0]  # e.g. "notepad.exe"
        stem = raw.rsplit(".", 1)[0]  # e.g. "notepad"
        logger.debug(f"_extract_app_name: found exe in code → '{stem}'")
        return stem

    # ── Priority 2: meaningful word from intent label ─────────────────────────
    tokens = intent_label.lower().split()
    # Remove filler words and the launch verb itself
    candidates = [
        t
        for t in tokens
        if t not in _FILLER_WORDS
        and t not in _LAUNCH_KEYWORDS
        and re.match(r"[a-z]", t)  # must start with a letter
    ]
    if candidates:
        # Take the last remaining word — for "open the media player" → "player"
        # is wrong, but "open ultraviewr" → "ultraviewr" is right.
        # For compound names use the *first* candidate (more discriminating).
        app = candidates[0]
        logger.debug(f"_extract_app_name: derived from intent label → '{app}'")
        return app

    return None
