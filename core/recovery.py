"""
Hierarchical error recovery manager with Phase 2 enhancements.
Classifies failures, enforces per-tool retry caps, escalates with structured context.
Implements smart retry with exponential backoff, circuit breakers, and enhanced diagnostics.
"""

import logging
import time
import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

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
    "NETWORK_ERROR": "Network connectivity issue",
    "RATE_LIMITED": "API rate limit exceeded",
    "DEPENDENCY_FAILURE": "Required dependency unavailable",
}


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3


@dataclass
class CircuitBreaker:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    half_open_calls: int = 0
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    
    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.reset()
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker reopened after failure in half-open state")
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.config.timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
                logger.info("Circuit breaker entering half-open state for testing")
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.config.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False
        return False
    
    def reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0
        logger.info("Circuit breaker reset to closed state")
    
    def get_state(self) -> dict:
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "half_open_calls": self.half_open_calls,
        }


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass 
class FailurePattern:
    error_type: str
    tool_name: str
    occurrence_count: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    common_context: List[str] = field(default_factory=list)
    suggested_fix: Optional[str] = None


class RecoveryManager:
    def __init__(self):
        self._failure_log: list[dict] = []
        self._consecutive_failures = 0
        self._tool_attempts: dict[str, int] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._failure_patterns: Dict[str, FailurePattern] = {}
        self._default_config = CircuitBreakerConfig()
        self._retry_config = RetryConfig()
        self._error_solutions: Dict[str, str] = {
            "PERMISSION_DENIED": "Check if the application has necessary permissions or run as administrator",
            "RESOURCE_NOT_FOUND": "Verify the resource exists and the path/name is correct",
            "TIMEOUT": "The operation took too long. Try simplifying or breaking into smaller steps",
            "NETWORK_ERROR": "Check internet connection and firewall settings",
            "RATE_LIMITED": "Too many requests. Wait before retrying or reduce frequency",
            "DEPENDENCY_FAILURE": "A required service or application is not running",
        }

    def get_circuit_breaker(self, tool_name: str) -> CircuitBreaker:
        if tool_name not in self._circuit_breakers:
            self._circuit_breakers[tool_name] = CircuitBreaker(config=self._default_config)
        return self._circuit_breakers[tool_name]

    def calculate_backoff(self, attempt: int, tool_name: Optional[str] = None) -> float:
        config = self._retry_config
        delay = config.base_delay * (config.exponential_base ** attempt)
        delay = min(delay, config.max_delay)
        if config.jitter:
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
        return max(0, delay)

    def classify_error(self, error_msg: str) -> str:
        err = error_msg.lower()
        if "timeout" in err or "timed out" in err:
            return "TIMEOUT"
        if "permission" in err or "access denied" in err or "access is denied" in err:
            return "PERMISSION_DENIED"
        if "not found" in err or "no window" in err or "does not exist" in err or "no such file" in err:
            return "RESOURCE_NOT_FOUND"
        if "unknown tool" in err or "not in registry" in err:
            return "TOOL_NOT_FOUND"
        if "json" in err or "parse" in err or "malformed" in err or "invalid json" in err:
            return "LLM_MALFORMED"
        if "argument" in err or "required" in err or "missing" in err or "invalid argument" in err:
            return "ARGS_INVALID"
        if "context" in err or "token" in err or "too long" in err or "max_tokens" in err:
            return "CONTEXT_OVERFLOW"
        if "network" in err or "connection" in err or "connect" in err:
            return "NETWORK_ERROR"
        if "rate limit" in err or "too many requests" in err or "429" in err:
            return "RATE_LIMITED"
        if "dependency" in err or "service unavailable" in err:
            return "DEPENDENCY_FAILURE"
        return "VERIFICATION_FAILED"

    def track_failure_pattern(self, tool_name: str, error_type: str, context: Optional[str] = None):
        pattern_key = f"{tool_name}:{error_type}"
        if pattern_key in self._failure_patterns:
            pattern = self._failure_patterns[pattern_key]
            pattern.occurrence_count += 1
            pattern.last_seen = time.time()
            if context and context not in pattern.common_context:
                pattern.common_context.append(context)
                pattern.common_context = pattern.common_context[-5:]
        else:
            self._failure_patterns[pattern_key] = FailurePattern(
                error_type=error_type,
                tool_name=tool_name,
                common_context=[context] if context else []
            )
        if self._failure_patterns[pattern_key].occurrence_count >= 3:
            if error_type in self._error_solutions:
                self._failure_patterns[pattern_key].suggested_fix = self._error_solutions[error_type]

    def get_diagnosis(self, tool_name: str, error_msg: str) -> dict:
        error_type = self.classify_error(error_msg)
        pattern_key = f"{tool_name}:{error_type}"
        diagnosis = {
            "error_type": error_type,
            "description": ERROR_TYPES.get(error_type, "Unknown error"),
            "tool": tool_name,
            "original_error": error_msg,
            "severity": "high" if error_type in ["PERMISSION_DENIED", "DEPENDENCY_FAILURE"] else "medium",
        }
        if error_type in self._error_solutions:
            diagnosis["suggested_fix"] = self._error_solutions[error_type]
        if pattern_key in self._failure_patterns:
            pattern = self._failure_patterns[pattern_key]
            diagnosis["occurrence_count"] = pattern.occurrence_count
            if pattern.suggested_fix:
                diagnosis["learned_fix"] = pattern.suggested_fix
            if pattern.common_context:
                diagnosis["common_context"] = pattern.common_context
        if error_type in ["TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"]:
            diagnosis["retry_recommended"] = True
            diagnosis["retry_strategy"] = "exponential_backoff"
        elif error_type in ["PERMISSION_DENIED", "RESOURCE_NOT_FOUND", "ARGS_INVALID"]:
            diagnosis["retry_recommended"] = False
            diagnosis["retry_strategy"] = "fix_first_then_retry"
        else:
            diagnosis["retry_recommended"] = True
            diagnosis["retry_strategy"] = "standard_retry"
        return diagnosis

    def should_retry(self, tool_name: str, error_msg: str) -> tuple[bool, float]:
        error_type = self.classify_error(error_msg)
        circuit_breaker = self.get_circuit_breaker(tool_name)
        if not circuit_breaker.can_execute():
            logger.warning(f"Circuit breaker OPEN for {tool_name}. Rejecting request.")
            return False, 0.0
        max_retries = TOOL_RETRY_LIMITS.get(tool_name, self._retry_config.max_retries)
        attempts = self._tool_attempts.get(tool_name, 0)
        if error_type in ["PERMISSION_DENIED", "RESOURCE_NOT_FOUND", "ARGS_INVALID", "TOOL_NOT_FOUND"]:
            if attempts >= 1:
                circuit_breaker.record_failure()
                self.track_failure_pattern(tool_name, error_type)
                self._consecutive_failures += 1
                return False, 0.0
        if attempts >= max_retries:
            circuit_breaker.record_failure()
            self.track_failure_pattern(tool_name, error_type)
            self._consecutive_failures += 1
            logger.warning(f"Recovery: {tool_name} failed {max_retries} times. Escalating.")
            if self._consecutive_failures >= 5:
                logger.error("Recovery: 5 consecutive failures — circuit breaker triggered")
                try:
                    notify_user("JARVIS has encountered repeated failures and is pausing to avoid damage. Please check the logs.", urgency="high")
                except Exception:
                    pass
            return False, 0.0
        delay = self.calculate_backoff(attempts, tool_name)
        self._tool_attempts[tool_name] = attempts + 1
        self._failure_log.append({"ts": time.time(), "tool": tool_name, "error": error_msg, "type": error_type, "attempt": attempts + 1})
        if len(self._failure_log) > 100:
            self._failure_log = self._failure_log[-50:]
        logger.info(f"Recovery: retrying {tool_name} (attempt {attempts + 1}/{max_retries}) after {delay:.2f}s backoff")
        return True, delay

    def record_success(self, tool_name: str):
        circuit_breaker = self.get_circuit_breaker(tool_name)
        circuit_breaker.record_success()
        self._consecutive_failures = 0
        if tool_name in self._tool_attempts:
            del self._tool_attempts[tool_name]
        logger.debug(f"Recorded success for {tool_name}")

    def escalate(self, goal: str, tool_name: str, error_msg: str) -> str:
        last_3 = self._failure_log[-3:] if self._failure_log else []
        diagnosis = self.get_diagnosis(tool_name, error_msg)
        summary = f"I couldn't complete: '{goal}'.\n\n"
        summary += f"**Diagnosis**: {diagnosis['description']}\n"
        summary += f"**Severity**: {diagnosis['severity'].upper()}\n\n"
        if diagnosis.get("suggested_fix"):
            summary += f"**Suggested Fix**: {diagnosis['suggested_fix']}\n\n"
        if diagnosis.get("learned_fix"):
            summary += f"**Learned Fix**: {diagnosis['learned_fix']}\n\n"
        summary += "What I tried:\n"
        for i, fail in enumerate(last_3, 1):
            summary += f"{i}. {fail['tool']} (attempt {fail.get('attempt', 1)}): {fail['error']}\n"
        if diagnosis.get("occurrence_count", 0) > 1:
            summary += f"\n⚠️ This error has occurred {diagnosis['occurrence_count']} times with this tool.\n"
        summary += "\n\n**Next Steps**:\n- Rephrase the request\n- Confirm the resource exists\n- Check system permissions\n- Try a simpler task"
        logger.warning(f"Recovery: escalating to user — {error_msg}")
        notify_user(summary, urgency="normal")
        self._tool_attempts.clear()
        return summary

    def reset(self):
        self._consecutive_failures = 0
        self._tool_attempts.clear()
        self._failure_log.clear()

    def get_circuit_breaker_status(self, tool_name: Optional[str] = None) -> dict:
        if tool_name:
            if tool_name in self._circuit_breakers:
                return {tool_name: self._circuit_breakers[tool_name].get_state()}
            return {tool_name: {"state": "not_tracked"}}
        return {name: cb.get_state() for name, cb in self._circuit_breakers.items()}

    def get_failure_summary(self) -> dict:
        if not self._failure_log:
            return {"recent_failures": [], "patterns": []}
        recent = self._failure_log[-10:]
        patterns = [{"tool": p.tool_name, "error_type": p.error_type, "count": p.occurrence_count, "suggested_fix": p.suggested_fix} for p in self._failure_patterns.values() if p.occurrence_count >= 2]
        return {"recent_failures": recent, "patterns": sorted(patterns, key=lambda x: x["count"], reverse=True), "consecutive_failures": self._consecutive_failures}

    def reset_circuit_breaker(self, tool_name: str):
        if tool_name in self._circuit_breakers:
            self._circuit_breakers[tool_name].reset()
            logger.info(f"Manually reset circuit breaker for {tool_name}")


# Global instance
recovery_manager = RecoveryManager()
