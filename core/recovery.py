"""
Hierarchical error recovery manager.
Classifies failures, enforces per-tool retry caps, escalates with structured context.
"""

import logging
import time

from settings import TOOL_RETRY_LIMITS
from tools.notify_user import notify_user

logger = logging.getLogger(__name__)

ERROR_TYPES = {
    "TOOL_NOT_FOUND": "LLM requested a tool not in registry",
    "ARGS_INVALID": "Tool arguments failed validation",
    "PERMISSION_DENIED": "OS blocked the action",
    "RESOURCE_NOT_FOUND": "App/file/window doesn't exist",
    "TIMEOUT": "Execution exceeded timeout",
    "VERIFICATION_FAILED": "Action ran but expected outcome not observed",
    "LLM_MALFORMED": "LLM output couldn't be parsed",
    "CONTEXT_OVERFLOW": "Token budget exceeded",
}


class RecoveryManager:
    def __init__(self):
        self._failure_log: list[dict] = []
        self._consecutive_failures = 0
        self._tool_attempts: dict[str, int] = {}

    def classify_error(self, error_msg: str) -> str:
        err = error_msg.lower()
        if "timeout" in err or "timed out" in err:
            return "TIMEOUT"
        if "permission" in err or "access denied" in err or "access is denied" in err:
            return "PERMISSION_DENIED"
        if (
            "not found" in err
            or "no window" in err
            or "does not exist" in err
            or "no such file" in err
        ):
            return "RESOURCE_NOT_FOUND"
        if "unknown tool" in err or "not in registry" in err:
            return "TOOL_NOT_FOUND"
        if (
            "json" in err
            or "parse" in err
            or "malformed" in err
            or "invalid json" in err
        ):
            return "LLM_MALFORMED"
        if (
            "argument" in err
            or "required" in err
            or "missing" in err
            or "invalid argument" in err
        ):
            return "ARGS_INVALID"
        if (
            "context" in err
            or "token" in err
            or "too long" in err
            or "max_tokens" in err
        ):
            return "CONTEXT_OVERFLOW"
        return "VERIFICATION_FAILED"

    def should_retry(self, tool_name: str, error_msg: str) -> bool:
        error_type = self.classify_error(error_msg)
        max_retries = TOOL_RETRY_LIMITS.get(tool_name, 2)
        attempts = self._tool_attempts.get(tool_name, 0)

        if attempts >= max_retries:
            self._consecutive_failures += 1
            logger.warning(
                f"Recovery: {tool_name} failed {max_retries} times. Escalating."
            )
            if self._consecutive_failures >= 5:
                logger.error(
                    "Recovery: 5 consecutive failures — circuit breaker triggered"
                )
                try:
                    notify_user(
                        "JARVIS has encountered repeated failures and is pausing to avoid damage. "
                        "Please check the logs.",
                        urgency="high",
                    )
                except Exception:
                    pass
            return False

        self._tool_attempts[tool_name] = attempts + 1
        self._failure_log.append(
            {
                "ts": time.time(),
                "tool": tool_name,
                "error": error_msg,
                "type": error_type,
            }
        )
        # Cap log to prevent unbounded growth in long sessions
        if len(self._failure_log) > 100:
            self._failure_log = self._failure_log[-50:]
        logger.info(
            f"Recovery: retrying {tool_name} (attempt {attempts + 1}/{max_retries})"
        )
        return True

    def escalate(self, goal: str, tool_name: str, error_msg: str) -> str:
        last_3 = self._failure_log[-3:] if self._failure_log else []
        summary = f"I couldn't complete: '{goal}'.\n\nWhat I tried:\n"
        for i, fail in enumerate(last_3, 1):
            summary += f"{i}. {fail['tool']}: {fail['error']}\n"
        summary += (
            "\nPlease rephrase, confirm the resource exists, or try a simpler task."
        )

        logger.warning(f"Recovery: escalating to user — {error_msg}")
        notify_user(summary, urgency="normal")
        self._tool_attempts.clear()
        return summary

    def reset(self):
        self._consecutive_failures = 0
        self._tool_attempts.clear()
        self._failure_log.clear()  # old failures shouldn't persist after success
