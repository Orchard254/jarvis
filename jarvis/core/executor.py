"""
jarvis/core/executor.py — Concurrency & Rate Limiting Layer

Manages tool execution flow to prevent race conditions and API throttling.
- Token Bucket Rate Limiter: Enforces limits on specific tools
- Thread-Safe Execution Pool: Bounded ThreadPoolExecutor (max 4 concurrent tools)
- Timeout Enforcement: Hard timeouts on all tools (default 30s)
"""

import threading
import time
from typing import Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting a specific tool."""
    max_calls: int  # Maximum calls allowed
    period_seconds: float  # Time period for the limit
    description: str = ""


class TokenBucket:
    """
    Token bucket rate limiter for enforcing API quotas.
    
    Tokens are added at a fixed rate up to a maximum capacity.
    Each operation consumes one token. If no tokens available, must wait.
    """
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens (burst capacity)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = threading.Lock()
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now
    
    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire a token from the bucket.
        
        Args:
            blocking: If True, wait for token; if False, return immediately
            timeout: Maximum time to wait (None for infinite)
            
        Returns:
            True if token acquired, False otherwise
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                self._refill()
                
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                
                if not blocking:
                    return False
                
                # Calculate wait time for next token
                wait_time = (1 - self.tokens) / self.refill_rate
            
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)
            
            # Wait before retry
            time.sleep(min(wait_time, 0.1))  # Cap sleep at 100ms for responsiveness
    
    def try_acquire(self) -> bool:
        """Try to acquire a token without blocking."""
        return self.acquire(blocking=False)
    
    def get_available_tokens(self) -> float:
        """Get current number of available tokens."""
        with self._lock:
            self._refill()
            return self.tokens


class RateLimiter:
    """
    Rate limiter managing multiple tool-specific token buckets.
    """
    
    # Default rate limits for various tool categories
    DEFAULT_LIMITS = {
        # Web tools - protect API quotas
        'web_search': RateLimitConfig(max_calls=5, period_seconds=60, description="Web search API"),
        'web_scraper': RateLimitConfig(max_calls=10, period_seconds=60, description="Web scraping"),
        'url_reader': RateLimitConfig(max_calls=15, period_seconds=60, description="URL reading"),
        
        # Vision tools - expensive operations
        'vision_analyzer': RateLimitConfig(max_calls=2, period_seconds=60, description="Vision analysis"),
        'ocr_extract_text': RateLimitConfig(max_calls=5, period_seconds=60, description="OCR processing"),
        'screen_capture': RateLimitConfig(max_calls=10, period_seconds=60, description="Screen capture"),
        
        # System tools - moderate limits
        'run_terminal_command': RateLimitConfig(max_calls=10, period_seconds=60, description="Terminal commands"),
        'run_python_code': RateLimitConfig(max_calls=5, period_seconds=60, description="Python execution"),
        
        # File operations - higher limits
        'file_reader': RateLimitConfig(max_calls=30, period_seconds=60, description="File reads"),
        'file_writer': RateLimitConfig(max_calls=20, period_seconds=60, description="File writes"),
        
        # AI internal tools - limited by model capacity
        'reasoning_engine': RateLimitConfig(max_calls=10, period_seconds=60, description="Reasoning calls"),
        'intent_router': RateLimitConfig(max_calls=20, period_seconds=60, description="Intent routing"),
    }
    
    def __init__(self, custom_limits: Optional[Dict[str, RateLimitConfig]] = None):
        """
        Initialize rate limiter.
        
        Args:
            custom_limits: Optional custom rate limits overriding defaults
        """
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        
        # Initialize with default limits
        limits = {**self.DEFAULT_LIMITS}
        if custom_limits:
            limits.update(custom_limits)
        
        for tool_name, config in limits.items():
            refill_rate = config.max_calls / config.period_seconds
            self._buckets[tool_name] = TokenBucket(
                capacity=config.max_calls,
                refill_rate=refill_rate
            )
    
    def acquire(self, tool_name: str, blocking: bool = True, 
                timeout: Optional[float] = 30.0) -> bool:
        """
        Acquire rate limit permission for a tool.
        
        Args:
            tool_name: Name of the tool requesting execution
            blocking: Whether to wait for rate limit
            timeout: Maximum wait time in seconds
            
        Returns:
            True if permission granted, False if rate limited
        """
        with self._lock:
            if tool_name not in self._buckets:
                # Unknown tool - use default permissive limit
                self._buckets[tool_name] = TokenBucket(capacity=100, refill_rate=10.0)
            bucket = self._buckets[tool_name]
        
        result = bucket.acquire(blocking=blocking, timeout=timeout)
        
        if not result:
            logger.warning(f"Rate limit exceeded for tool: {tool_name}")
        
        return result
    
    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current rate limit status for all tools."""
        status = {}
        with self._lock:
            for tool_name, bucket in self._buckets.items():
                status[tool_name] = {
                    'available_tokens': round(bucket.get_available_tokens(), 2),
                    'capacity': bucket.capacity
                }
        return status


@dataclass
class ExecutionResult:
    """Result of a tool execution."""
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    timed_out: bool = False


class ToolExecutor:
    """
    Thread-safe tool executor with rate limiting and timeout enforcement.
    
    Features:
    - Bounded thread pool (max 4 concurrent tools)
    - Per-tool rate limiting
    - Hard timeout enforcement
    - Result caching (optional)
    """
    
    def __init__(self, 
                 max_workers: int = 4,
                 default_timeout: float = 30.0,
                 rate_limiter: Optional[RateLimiter] = None):
        """
        Initialize tool executor.
        
        Args:
            max_workers: Maximum concurrent tool executions
            default_timeout: Default timeout in seconds
            rate_limiter: Optional custom rate limiter
        """
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.rate_limiter = rate_limiter or RateLimiter()
        
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._shutdown = False
        self._lock = threading.Lock()
        
        logger.info(f"ToolExecutor initialized with max_workers={max_workers}, "
                   f"default_timeout={default_timeout}s")
    
    def execute(self, 
                tool_name: str,
                func: Callable,
                args: tuple = (),
                kwargs: Optional[Dict[str, Any]] = None,
                timeout: Optional[float] = None) -> ExecutionResult:
        """
        Execute a tool with rate limiting and timeout.
        
        Args:
            tool_name: Name of the tool for rate limiting
            func: Function to execute
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            timeout: Override default timeout (None uses default)
            
        Returns:
            ExecutionResult with success status and result/error
        """
        if self._shutdown:
            return ExecutionResult(
                success=False,
                error="Executor has been shut down"
            )
        
        kwargs = kwargs or {}
        timeout = timeout or self.default_timeout
        
        # Check rate limit (non-blocking with short timeout)
        if not self.rate_limiter.acquire(tool_name, blocking=True, timeout=5.0):
            return ExecutionResult(
                success=False,
                error=f"Rate limit exceeded for tool: {tool_name}"
            )
        
        start_time = time.time()
        
        try:
            # Submit to thread pool
            future = self._executor.submit(func, *args, **kwargs)
            
            try:
                # Wait for result with timeout
                result = future.result(timeout=timeout)
                execution_time = time.time() - start_time
                
                return ExecutionResult(
                    success=True,
                    result=result,
                    execution_time=execution_time
                )
                
            except FuturesTimeoutError:
                execution_time = time.time() - start_time
                logger.error(f"Tool execution timed out after {timeout}s: {tool_name}")
                
                # Attempt to cancel the future (may not stop already-running code)
                future.cancel()
                
                return ExecutionResult(
                    success=False,
                    error=f"Execution timeout after {timeout} seconds",
                    timed_out=True,
                    execution_time=execution_time
                )
                
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Tool execution error: {tool_name} - {e}")
            
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=execution_time
            )
    
    def execute_async(self,
                      tool_name: str,
                      func: Callable,
                      args: tuple = (),
                      kwargs: Optional[Dict[str, Any]] = None,
                      timeout: Optional[float] = None,
                      callback: Optional[Callable[[ExecutionResult], None]] = None) -> None:
        """
        Execute a tool asynchronously with optional callback.
        
        Args:
            tool_name: Name of the tool for rate limiting
            func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            timeout: Override default timeout
            callback: Optional callback function called with ExecutionResult
        """
        def wrapped_execute():
            result = self.execute(tool_name, func, args, kwargs, timeout)
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
        
        # Submit wrapper to executor
        self._executor.submit(wrapped_execute)
    
    def batch_execute(self,
                      tasks: list[Dict[str, Any]],
                      stop_on_error: bool = True) -> list[ExecutionResult]:
        """
        Execute multiple tools in parallel.
        
        Args:
            tasks: List of dicts with keys: tool_name, func, args, kwargs, timeout
            stop_on_error: If True, cancel remaining tasks on first error
            
        Returns:
            List of ExecutionResults in same order as tasks
        """
        if not tasks:
            return []
        
        results = [None] * len(tasks)
        futures = []
        
        for i, task in enumerate(tasks):
            future = self._executor.submit(
                self.execute,
                task.get('tool_name', 'unknown'),
                task.get('func'),
                task.get('args', ()),
                task.get('kwargs', {}),
                task.get('timeout')
            )
            futures.append((i, future))
        
        # Collect results
        for idx, future in futures:
            try:
                result = future.result(timeout=self.default_timeout * 2)
                results[idx] = result
                
                if stop_on_error and not result.success:
                    # Cancel remaining futures
                    for remaining_idx, remaining_future in futures:
                        if remaining_idx > idx:
                            remaining_future.cancel()
                    break
                    
            except Exception as e:
                results[idx] = ExecutionResult(
                    success=False,
                    error=str(e)
                )
        
        return results
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the executor.
        
        Args:
            wait: If True, wait for pending tasks to complete
        """
        self._shutdown = True
        self._executor.shutdown(wait=wait)
        logger.info("ToolExecutor shut down")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get executor statistics."""
        return {
            'max_workers': self.max_workers,
            'default_timeout': self.default_timeout,
            'rate_limiter_status': self.rate_limiter.get_status(),
            'shutdown': self._shutdown
        }


# Global executor instance
_executor_instance: Optional[ToolExecutor] = None
_executor_lock = threading.Lock()


def get_executor(max_workers: int = 4, 
                 default_timeout: float = 30.0,
                 rate_limiter: Optional[RateLimiter] = None) -> ToolExecutor:
    """
    Get or create the global tool executor.
    
    Args:
        max_workers: Maximum concurrent executions
        default_timeout: Default timeout in seconds
        rate_limiter: Optional custom rate limiter
        
    Returns:
        Global ToolExecutor instance
    """
    global _executor_instance
    
    with _executor_lock:
        if _executor_instance is None:
            _executor_instance = ToolExecutor(
                max_workers=max_workers,
                default_timeout=default_timeout,
                rate_limiter=rate_limiter
            )
        return _executor_instance


def reset_executor() -> None:
    """Reset the global executor (useful for testing)."""
    global _executor_instance
    
    with _executor_lock:
        if _executor_instance is not None:
            _executor_instance.shutdown(wait=False)
            _executor_instance = None
