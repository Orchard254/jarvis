"""
Circuit Breaker Module
Implements the circuit breaker pattern to prevent cascading failures.
"""
import time
import asyncio
import threading
from typing import Any, Callable, Optional, Dict, Union
from enum import Enum
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation, requests flow through
    OPEN = "open"           # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitStats:
    """Statistics for a circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0


class CircuitBreaker:
    """
    Circuit breaker implementation to prevent cascading failures.
    
    When failures exceed a threshold, the circuit opens and rejects
    all requests for a cooldown period. After cooldown, it enters
    half-open state to test if the service recovered.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: float = 60.0,
        expected_exceptions: tuple = (Exception,),
        name: str = "default"
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        self.expected_exceptions = expected_exceptions
        self.name = name
        
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._last_state_change: float = time.time()
        self._async_lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for timeout transition."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_state_change >= self.timeout_seconds:
                logger.info(f"Circuit {self.name} transitioning from OPEN to HALF_OPEN")
                self._state = CircuitState.HALF_OPEN
                self._last_state_change = time.time()
        return self._state

    @property
    def stats(self) -> CircuitStats:
        return self._stats

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker (async).
        
        Raises:
            CircuitOpenError: If circuit is open and rejecting requests
        """
        async with self._async_lock:
            current_state = self.state
            
            if current_state == CircuitState.OPEN:
                self._stats.rejected_calls += 1
                logger.warning(f"Circuit {self.name} is OPEN, rejecting request")
                raise CircuitOpenError(f"Circuit breaker {self.name} is open")
            
            self._stats.total_calls += 1

        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            await self._on_success()
            return result
        except self.expected_exceptions as e:
            await self._on_failure(e)
            raise
        except Exception as e:
            await self._on_failure(e)
            raise

    def sync_call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker (sync).
        
        Raises:
            CircuitOpenError: If circuit is open and rejecting requests
        """
        with self._sync_lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                self._stats.rejected_calls += 1
                logger.warning(f"Circuit {self.name} is OPEN, rejecting request")
                raise CircuitOpenError(f"Circuit breaker {self.name} is open")

            self._stats.total_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success_sync()
            return result
        except self.expected_exceptions as e:
            self._on_failure_sync(e)
            raise
        except Exception as e:
            self._on_failure_sync(e)
            raise

    def _on_success_sync(self) -> None:
        """Handle successful call (sync version)."""
        self._stats.successful_calls += 1
        self._stats.last_success_time = time.time()
        self._stats.consecutive_failures = 0
        self._stats.consecutive_successes += 1

        if self._state == CircuitState.HALF_OPEN:
            if self._stats.consecutive_successes >= self.success_threshold:
                logger.info(f"Circuit {self.name} transitioning from HALF_OPEN to CLOSED")
                self._state = CircuitState.CLOSED
                self._last_state_change = time.time()
                self._stats.consecutive_successes = 0

    def _on_failure_sync(self, exception: Exception) -> None:
        """Handle failed call (sync version)."""
        self._stats.failed_calls += 1
        self._stats.last_failure_time = time.time()
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0

        logger.warning(f"Circuit {self.name} failure: {exception}")

        if self._state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit {self.name} failing in HALF_OPEN, reopening")
            self._state = CircuitState.OPEN
            self._last_state_change = time.time()
        elif self._state == CircuitState.CLOSED:
            if self._stats.consecutive_failures >= self.failure_threshold:
                logger.error(
                    f"Circuit {self.name} OPENING after {self._stats.consecutive_failures} "
                    f"consecutive failures"
                )
                self._state = CircuitState.OPEN
                self._last_state_change = time.time()

    async def _on_success(self) -> None:
        self._on_success_sync()

    async def _on_failure(self, exception: Exception) -> None:
        self._on_failure_sync(exception)

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        logger.info(f"Circuit {self.name} manually reset")
        self._state = CircuitState.CLOSED
        self._last_state_change = time.time()
        self._stats.consecutive_failures = 0
        self._stats.consecutive_successes = 0

    def get_info(self) -> Dict[str, Any]:
        """Get circuit breaker information."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout_seconds": self.timeout_seconds,
            "stats": {
                "total_calls": self._stats.total_calls,
                "successful_calls": self._stats.successful_calls,
                "failed_calls": self._stats.failed_calls,
                "rejected_calls": self._stats.rejected_calls,
                "consecutive_failures": self._stats.consecutive_failures,
                "consecutive_successes": self._stats.consecutive_successes,
                "last_failure_time": self._stats.last_failure_time,
                "last_success_time": self._stats.last_success_time
            }
        }


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejecting requests."""
    pass


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: float = 60.0,
        expected_exceptions: tuple = (Exception,)
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout_seconds=timeout_seconds,
                expected_exceptions=expected_exceptions,
                name=name
            )
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        return self._breakers.get(name)

    def remove(self, name: str) -> bool:
        """Remove a circuit breaker."""
        if name in self._breakers:
            del self._breakers[name]
            return True
        return False

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        """List all circuit breakers with their info."""
        return {name: cb.get_info() for name, cb in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._breakers.values():
            cb.reset()


# Decorator for easy circuit breaker usage
def with_circuit_breaker(
    name: str = "default",
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout_seconds: float = 60.0
):
    """Decorator to apply circuit breaker to a function."""
    registry = CircuitBreakerRegistry()
    
    def decorator(func: Callable) -> Callable:
        cb = registry.get_or_create(
            name=f"{name}_{func.__name__}",
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout_seconds=timeout_seconds
        )
        
        async def wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)
        
        wrapper.circuit_breaker = cb
        return wrapper
    
    return decorator
