"""
jarvis/core/executor.py — Concurrency & Rate Limiting Manager

Manages tool execution flow to prevent race conditions and API throttling:
- Token Bucket Rate Limiter: Enforces limits on specific tools
- Thread-Safe Execution Pool: Bounded ThreadPoolExecutor (max 4 concurrent tools)
- Timeout Enforcement: Hard timeouts on all tools (default 30s)
"""

import logging
import time
import threading
from typing import Dict, Any, Optional, Callable, List, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
import queue

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting a specific tool type."""
    max_calls: int  # Maximum number of calls allowed
    per_seconds: float  # Time window in seconds
    description: str = ""


# Default rate limits for different tool categories
DEFAULT_RATE_LIMITS: Dict[str, RateLimitConfig] = {
    'web_search': RateLimitConfig(max_calls=5, per_seconds=60.0, description="Web search API calls"),
    'vision_analysis': RateLimitConfig(max_calls=2, per_seconds=60.0, description="Vision analysis calls"),
    'web_scraper': RateLimitConfig(max_calls=10, per_seconds=60.0, description="Web scraping requests"),
    'file_operation': RateLimitConfig(max_calls=20, per_seconds=60.0, description="File system operations"),
    'terminal_command': RateLimitConfig(max_calls=10, per_seconds=60.0, description="Terminal commands"),
    'default': RateLimitConfig(max_calls=30, per_seconds=60.0, description="Default rate limit"),
}


class TokenBucket:
    """
    Token bucket rate limiter implementation.
    
    Tokens are added at a constant rate up to a maximum capacity.
    Each operation consumes one token. If no tokens available, must wait.
    """
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens (bucket size)
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
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire a token from the bucket.
        
        Args:
            blocking: Whether to wait for a token if none available
            timeout: Maximum time to wait (None = infinite)
            
        Returns:
            True if token acquired, False if timeout or non-blocking and no tokens
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
            
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False
            
            # Wait a bit before retrying
            time.sleep(0.1)
    
    def get_available_tokens(self) -> float:
        """Get current number of available tokens."""
        with self._lock:
            self._refill()
            return self.tokens


@dataclass
class ExecutionRequest:
    """Represents a tool execution request."""
    tool_name: str
    params: Dict[str, Any]
    callback: Optional[Callable[[Dict[str, Any]], None]] = None
    priority: int = 0  # Higher = more urgent
    submitted_at: float = field(default_factory=time.time)
    timeout: float = 30.0  # Per-request timeout override


@dataclass
class ExecutionResult:
    """Result of a tool execution."""
    tool_name: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    timed_out: bool = False


class RateLimiter:
    """
    Multi-bucket rate limiter for different tool types.
    """
    
    def __init__(self, configs: Optional[Dict[str, RateLimitConfig]] = None):
        """
        Initialize rate limiter with configurations.
        
        Args:
            configs: Dictionary mapping tool names to rate limit configs
        """
        self.configs = configs or DEFAULT_RATE_LIMITS.copy()
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        
        # Initialize buckets for each configured tool type
        for tool_type, config in self.configs.items():
            refill_rate = config.max_calls / config.per_seconds
            self._buckets[tool_type] = TokenBucket(
                capacity=config.max_calls,
                refill_rate=refill_rate
            )
    
    def add_tool_limit(self, tool_name: str, max_calls: int, per_seconds: float, 
                       description: str = "") -> None:
        """Add or update a rate limit for a specific tool."""
        with self._lock:
            self.configs[tool_name] = RateLimitConfig(
                max_calls=max_calls,
                per_seconds=per_seconds,
                description=description
            )
            refill_rate = max_calls / per_seconds
            self._buckets[tool_name] = TokenBucket(
                capacity=max_calls,
                refill_rate=refill_rate
            )
            logger.info(f"Added rate limit for {tool_name}: {max_calls} calls per {per_seconds}s")
    
    def _get_bucket_for_tool(self, tool_name: str) -> TokenBucket:
        """Get the appropriate rate limit bucket for a tool."""
        # Check for exact match first
        if tool_name in self._buckets:
            return self._buckets[tool_name]
        
        # Check for category matches (e.g., 'web_search_tool' matches 'web_search')
        for bucket_name, bucket in self._buckets.items():
            if bucket_name in tool_name or tool_name.startswith(bucket_name):
                return bucket
        
        # Fall back to default bucket
        if 'default' not in self._buckets:
            # Create default bucket if it doesn't exist
            config = self.configs.get('default', RateLimitConfig(30, 60.0))
            refill_rate = config.max_calls / config.per_seconds
            self._buckets['default'] = TokenBucket(config.max_calls, refill_rate)
        
        return self._buckets['default']
    
    def acquire(self, tool_name: str, blocking: bool = True, 
                timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to execute a tool (consume a rate limit token).
        
        Args:
            tool_name: Name of the tool to execute
            blocking: Whether to wait for rate limit
            timeout: Maximum wait time for rate limit
            
        Returns:
            True if execution permitted, False if rate limited
        """
        bucket = self._get_bucket_for_tool(tool_name)
        acquired = bucket.acquire(blocking=blocking, timeout=timeout)
        
        if not acquired:
            logger.warning(f"Rate limit exceeded for tool: {tool_name}")
        
        return acquired
    
    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current rate limit status for all buckets."""
        status = {}
        for tool_name, bucket in self._buckets.items():
            config = self.configs.get(tool_name, self.configs.get('default'))
            status[tool_name] = {
                'available_tokens': bucket.get_available_tokens(),
                'max_capacity': config.max_calls if config else 'N/A',
                'window_seconds': config.per_seconds if config else 'N/A',
                'description': config.description if config else '',
            }
        return status


class ConcurrencyExecutor:
    """
    Thread-safe executor with bounded concurrency and timeout enforcement.
    """
    
    def __init__(self, 
                 max_workers: int = 4,
                 default_timeout: float = 30.0,
                 rate_limiter: Optional[RateLimiter] = None):
        """
        Initialize the executor.
        
        Args:
            max_workers: Maximum concurrent tool executions (default 4)
            default_timeout: Default timeout in seconds (default 30s)
            rate_limiter: Optional rate limiter instance
        """
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        
        # Thread pool with bounded concurrency
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="jarvis_tool_executor"
        )
        
        # Rate limiter
        self.rate_limiter = rate_limiter or RateLimiter()
        
        # Execution tracking
        self._active_executions: Dict[str, ExecutionResult] = {}
        self._execution_history: List[ExecutionResult] = []
        self._history_lock = threading.Lock()
        self._max_history = 100
        
        # Shutdown flag
        self._shutdown = False
        
        logger.info(f"ConcurrencyExecutor initialized (max_workers={max_workers}, timeout={default_timeout}s)")
    
    def execute(self, 
                tool_name: str, 
                func: Callable[..., Dict[str, Any]],
                params: Optional[Dict[str, Any]] = None,
                timeout: Optional[float] = None,
                callback: Optional[Callable[[ExecutionResult], None]] = None,
                rate_limit_timeout: float = 10.0) -> Future:
        """
        Execute a tool function with rate limiting and timeout enforcement.
        
        Args:
            tool_name: Name of the tool (for rate limiting and logging)
            func: The tool function to execute
            params: Parameters to pass to the function
            timeout: Execution timeout in seconds (overrides default)
            callback: Callback function to call with result
            rate_limit_timeout: How long to wait for rate limit
            
        Returns:
            Future object representing the execution
        """
        if self._shutdown:
            raise RuntimeError("Executor has been shut down")
        
        params = params or {}
        exec_timeout = timeout if timeout is not None else self.default_timeout
        
        # First, check rate limit
        logger.debug(f"Acquiring rate limit for {tool_name}")
        if not self.rate_limiter.acquire(tool_name, blocking=True, timeout=rate_limit_timeout):
            error_msg = f"Rate limit exceeded for {tool_name} after waiting {rate_limit_timeout}s"
            logger.error(error_msg)
            result = ExecutionResult(
                tool_name=tool_name,
                success=False,
                error=error_msg,
                execution_time=0.0,
                timed_out=False
            )
            # Create a completed future with the error
            future: Future = Future()
            future.set_result(result)
            if callback:
                callback(result)
            return future
        
        # Submit to thread pool
        future = self._executor.submit(
            self._execute_with_timeout,
            tool_name,
            func,
            params,
            exec_timeout,
            callback
        )
        
        return future
    
    def _execute_with_timeout(self,
                              tool_name: str,
                              func: Callable[..., Dict[str, Any]],
                              params: Dict[str, Any],
                              timeout: float,
                              callback: Optional[Callable[[ExecutionResult], None]]) -> ExecutionResult:
        """Internal method to execute a function with timeout."""
        start_time = time.time()
        result = None
        error = None
        timed_out = False
        
        try:
            logger.debug(f"Executing {tool_name} with timeout {timeout}s")
            
            # Create a sub-future for the actual execution
            exec_future: Future = Future()
            
            def run_func():
                try:
                    result = func(**params)
                    exec_future.set_result(result)
                except Exception as e:
                    exec_future.set_exception(e)
            
            # Run in a separate thread for timeout enforcement
            worker_thread = threading.Thread(target=run_func, daemon=True)
            worker_thread.start()
            
            try:
                result = exec_future.result(timeout=timeout)
            except FuturesTimeoutError:
                timed_out = True
                error = f"Tool execution timed out after {timeout} seconds"
                logger.error(f"TIMEOUT: {tool_name} - {error}")
            except Exception as e:
                error = str(e)
                logger.error(f"ERROR in {tool_name}: {error}")
            finally:
                # Ensure thread completes or is cleaned up
                worker_thread.join(timeout=1.0)
            
        except Exception as e:
            error = str(e)
            logger.exception(f"Unexpected error in {tool_name}: {error}")
        
        execution_time = time.time() - start_time
        
        # Build result
        exec_result = ExecutionResult(
            tool_name=tool_name,
            success=result is not None and not timed_out and error is None,
            result=result if result else None,
            error=error,
            execution_time=execution_time,
            timed_out=timed_out
        )
        
        # Track execution
        self._track_execution(exec_result)
        
        # Invoke callback if provided
        if callback:
            try:
                callback(exec_result)
            except Exception as e:
                logger.error(f"Callback error for {tool_name}: {e}")
        
        return exec_result
    
    def _track_execution(self, result: ExecutionResult) -> None:
        """Track execution in history."""
        with self._history_lock:
            self._active_executions[result.tool_name] = result
            self._execution_history.append(result)
            
            # Trim history if too long
            if len(self._execution_history) > self._max_history:
                self._execution_history = self._execution_history[-self._max_history:]
    
    def execute_batch(self, 
                      requests: List[ExecutionRequest]) -> List[Future]:
        """
        Execute multiple tool requests concurrently.
        
        Args:
            requests: List of execution requests
            
        Returns:
            List of Future objects
        """
        futures = []
        for req in requests:
            future = self.execute(
                tool_name=req.tool_name,
                func=lambda **p: {"error": "Batch execution requires explicit function"},
                params=req.params,
                timeout=req.timeout,
                callback=req.callback
            )
            futures.append(future)
        
        return futures
    
    def get_active_count(self) -> int:
        """Get number of currently active executions."""
        # Note: This is approximate since we don't track completion precisely
        return len([f for f in self._active_executions.values() if f.execution_time < 1.0])
    
    def get_status(self) -> Dict[str, Any]:
        """Get executor status."""
        return {
            'max_workers': self.max_workers,
            'default_timeout': self.default_timeout,
            'active_executions': len(self._active_executions),
            'total_executions': len(self._execution_history),
            'rate_limiter_status': self.rate_limiter.get_status(),
        }
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shut down the executor.
        
        Args:
            wait: Whether to wait for pending tasks to complete
        """
        logger.info("Shutting down ConcurrencyExecutor")
        self._shutdown = True
        self._executor.shutdown(wait=wait)


class ToolExecutor:
    """
    High-level tool execution manager combining safety, rate limiting, and concurrency.
    """
    
    def __init__(self,
                 max_concurrent: int = 4,
                 default_timeout: float = 30.0,
                 rate_limits: Optional[Dict[str, RateLimitConfig]] = None):
        """
        Initialize the tool executor.
        
        Args:
            max_concurrent: Maximum concurrent tool executions
            default_timeout: Default timeout in seconds
            rate_limits: Custom rate limit configurations
        """
        self.rate_limiter = RateLimiter(rate_limits)
        self.executor = ConcurrencyExecutor(
            max_workers=max_concurrent,
            default_timeout=default_timeout,
            rate_limiter=self.rate_limiter
        )
        
        logger.info(f"ToolExecutor initialized (max_concurrent={max_concurrent})")
    
    def execute_tool(self,
                     tool_name: str,
                     func: Callable[..., Dict[str, Any]],
                     params: Optional[Dict[str, Any]] = None,
                     timeout: Optional[float] = None,
                     callback: Optional[Callable[[ExecutionResult], None]] = None) -> Future:
        """
        Execute a tool with full safety and rate limiting.
        
        Args:
            tool_name: Name of the tool
            func: Tool function to execute
            params: Tool parameters
            timeout: Execution timeout
            callback: Result callback
            
        Returns:
            Future with execution result
        """
        return self.executor.execute(
            tool_name=tool_name,
            func=func,
            params=params,
            timeout=timeout,
            callback=callback
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get execution metrics and status."""
        return self.executor.get_status()
    
    def shutdown(self, wait: bool = True) -> None:
        """Shut down the executor."""
        self.executor.shutdown(wait=wait)


# Global executor instance
_executor_instance: Optional[ToolExecutor] = None


def get_executor(max_concurrent: int = 4, 
                 default_timeout: float = 30.0,
                 rate_limits: Optional[Dict[str, RateLimitConfig]] = None) -> ToolExecutor:
    """Get or create the global tool executor."""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = ToolExecutor(
            max_concurrent=max_concurrent,
            default_timeout=default_timeout,
            rate_limits=rate_limits
        )
    return _executor_instance


def reset_executor() -> None:
    """Reset the global executor (useful for testing)."""
    global _executor_instance
    if _executor_instance:
        _executor_instance.shutdown(wait=False)
    _executor_instance = None
