"""
Hierarchical Error Recovery System.
Implements specific recovery strategies per error type instead of generic failure handling.
"""

import logging
import time
from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Classification of error types for targeted recovery."""
    API_RATE_LIMIT = "api_rate_limit"
    API_ERROR = "api_error"
    NETWORK_TIMEOUT = "network_timeout"
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    SYNTAX_ERROR = "syntax_error"
    LOGIC_ERROR = "logic_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Available recovery strategies."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    RETRY_WITH_DELAY = "retry_with_delay"
    ALTERNATIVE_APPROACH = "alternative_approach"
    FIX_AND_RETRY = "fix_and_retry"
    REPLAN = "replan"
    ESCALATE = "escalate"
    ABORT = "abort"


@dataclass
class RecoveryConfig:
    """Configuration for recovery behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_errors: List[ErrorType] = field(default_factory=list)
    

@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""
    success: bool
    strategy_used: RecoveryStrategy
    retries_attempted: int
    total_time_seconds: float
    error_message: str = ""
    recovered_value: Any = None


class HierarchicalRecovery:
    """
    Implements hierarchical error recovery with type-specific strategies.
    
    Recovery Hierarchy:
    1. Transient errors (rate limits, timeouts) → Exponential backoff retry
    2. Fixable errors (syntax, validation) → Auto-fix and retry
    3. Logic errors → Replan with different approach
    4. Critical errors → Escalate or abort
    """
    
    def __init__(self, config: Optional[RecoveryConfig] = None):
        self.config = config or RecoveryConfig()
        self._error_handlers: Dict[ErrorType, Callable] = {}
        self._setup_default_handlers()
    
    def _setup_default_handlers(self):
        """Register default error handlers."""
        
        # Rate limit errors - exponential backoff
        self.register_handler(
            ErrorType.API_RATE_LIMIT,
            self._handle_rate_limit
        )
        
        # Network timeouts - retry with delay
        self.register_handler(
            ErrorType.NETWORK_TIMEOUT,
            self._handle_network_timeout
        )
        
        # API errors - retry with backoff
        self.register_handler(
            ErrorType.API_ERROR,
            self._handle_api_error
        )
        
        # File not found - check alternative paths
        self.register_handler(
            ErrorType.FILE_NOT_FOUND,
            self._handle_file_not_found
        )
        
        # Permission denied - suggest privilege escalation
        self.register_handler(
            ErrorType.PERMISSION_DENIED,
            self._handle_permission_denied
        )
        
        # Syntax errors - attempt auto-fix
        self.register_handler(
            ErrorType.SYNTAX_ERROR,
            self._handle_syntax_error
        )
        
        # Logic errors - trigger replanning
        self.register_handler(
            ErrorType.LOGIC_ERROR,
            self._handle_logic_error
        )
        
        # Resource exhausted - wait and retry
        self.register_handler(
            ErrorType.RESOURCE_EXHAUSTED,
            self._handle_resource_exhausted
        )
        
        # Validation errors - fix parameters
        self.register_handler(
            ErrorType.VALIDATION_ERROR,
            self._handle_validation_error
        )
    
    def register_handler(self, error_type: ErrorType, handler: Callable):
        """
        Register a custom handler for an error type.
        
        Args:
            error_type: Type of error to handle
            handler: Function that takes (error, context) and returns (should_retry, modified_context)
        """
        self._error_handlers[error_type] = handler
        logger.debug(f"Registered handler for {error_type.value}")
    
    def classify_error(self, error: Exception) -> ErrorType:
        """
        Classify an exception into an ErrorType.
        
        Args:
            error: The exception to classify
            
        Returns:
            ErrorType classification
        """
        error_str = str(error).lower()
        error_type_str = type(error).__name__.lower()
        
        # Rate limiting
        if 'rate limit' in error_str or '429' in error_str or 'too many requests' in error_str:
            return ErrorType.API_RATE_LIMIT
        
        # Network issues
        if 'timeout' in error_str or 'timed out' in error_str:
            return ErrorType.NETWORK_TIMEOUT
        if 'connection' in error_str or 'network' in error_str:
            return ErrorType.API_ERROR
        
        # File system errors
        if 'no such file' in error_str or 'not found' in error_str or isinstance(error, FileNotFoundError):
            return ErrorType.FILE_NOT_FOUND
        if 'permission' in error_str or 'access denied' in error_str or isinstance(error, PermissionError):
            return ErrorType.PERMISSION_DENIED
        
        # Code errors
        if 'syntax' in error_str or isinstance(error, SyntaxError):
            return ErrorType.SYNTAX_ERROR
        if 'invalid' in error_str or 'validation' in error_str:
            return ErrorType.VALIDATION_ERROR
        
        # Resource issues
        if 'memory' in error_str or 'disk' in error_str or 'quota' in error_str:
            return ErrorType.RESOURCE_EXHAUSTED
        
        # Default
        return ErrorType.UNKNOWN
    
    def execute_with_recovery(
        self,
        operation: Callable,
        context: Optional[Dict[str, Any]] = None,
        operation_name: str = "operation"
    ) -> RecoveryResult:
        """
        Execute an operation with automatic error recovery.
        
        Args:
            operation: Function to execute
            context: Optional context dictionary passed to handlers
            operation_name: Name of the operation for logging
            
        Returns:
            RecoveryResult with outcome details
        """
        context = context or {}
        start_time = time.time()
        retries = 0
        last_error = None
        
        while retries <= self.config.max_retries:
            try:
                # Attempt operation
                result = operation()
                
                # Success
                return RecoveryResult(
                    success=True,
                    strategy_used=RecoveryStrategy.RETRY_WITH_DELAY,  # Default
                    retries_attempted=retries,
                    total_time_seconds=time.time() - start_time,
                    recovered_value=result
                )
                
            except Exception as e:
                last_error = e
                error_type = self.classify_error(e)
                
                logger.warning(
                    f"{operation_name} failed (attempt {retries + 1}/{self.config.max_retries + 1}): "
                    f"{error_type.value} - {str(e)}"
                )
                
                # Check if this error type is retryable
                if error_type not in self.config.retryable_errors and error_type != ErrorType.UNKNOWN:
                    # Try to get handler-specific retry decision
                    handler = self._error_handlers.get(error_type)
                    if handler:
                        try:
                            should_retry, context = handler(e, context, retries)
                            if not should_retry:
                                logger.info(f"Handler determined {error_type.value} is not recoverable")
                                break
                        except Exception as handler_error:
                            logger.error(f"Error handler failed: {handler_error}")
                            break
                
                # Check if we've exhausted retries
                if retries >= self.config.max_retries:
                    logger.error(f"{operation_name} exhausted all retry attempts")
                    break
                
                # Calculate delay with exponential backoff
                delay = min(
                    self.config.base_delay * (self.config.exponential_base ** retries),
                    self.config.max_delay
                )
                
                # Add jitter if configured
                if self.config.jitter:
                    import random
                    jitter = random.uniform(0, delay * 0.2)
                    delay += jitter
                
                logger.info(f"Retrying {operation_name} in {delay:.2f}s (attempt {retries + 2})")
                time.sleep(delay)
                
                retries += 1
        
        # All retries exhausted
        return RecoveryResult(
            success=False,
            strategy_used=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            retries_attempted=retries,
            total_time_seconds=time.time() - start_time,
            error_message=str(last_error) if last_error else "Unknown error"
        )
    
    def _handle_rate_limit(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle API rate limit errors with exponential backoff."""
        # Extract retry-after if available
        retry_after = getattr(error, 'retry_after', None)
        if retry_after:
            context['next_retry_delay'] = float(retry_after)
        
        # Always retry rate limits with backoff
        return (True, context)
    
    def _handle_network_timeout(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle network timeouts with increased timeout values."""
        # Increase timeout for next attempt
        current_timeout = context.get('timeout', 30)
        context['timeout'] = min(current_timeout * 1.5, 300)
        
        return (True, context)
    
    def _handle_api_error(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle general API errors."""
        # Retry transient API errors
        error_str = str(error).lower()
        transient_keywords = ['temporary', 'transient', 'unavailable', 'service']
        
        if any(keyword in error_str for keyword in transient_keywords):
            return (True, context)
        
        # For other API errors, retry a few times then give up
        return (retry_count < 2, context)
    
    def _handle_file_not_found(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle file not found by checking alternative paths."""
        # Try alternative paths if provided
        alt_paths = context.get('alternative_paths', [])
        if alt_paths and retry_count < len(alt_paths):
            context['current_path'] = alt_paths[retry_count]
            return (True, context)
        
        # No alternatives, don't retry
        return (False, context)
    
    def _handle_permission_denied(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle permission errors - typically cannot auto-recover."""
        # Suggest running with elevated privileges
        context['suggested_action'] = "Request user to run with elevated privileges or check file permissions"
        
        # Don't automatically retry permission errors
        return (False, context)
    
    def _handle_syntax_error(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle syntax errors by attempting auto-fix."""
        # If code fixer is available in context, use it
        code_fixer = context.get('code_fixer')
        if code_fixer and hasattr(code_fixer, 'fix_syntax'):
            original_code = context.get('code', '')
            fixed_code = code_fixer.fix_syntax(original_code, str(error))
            
            if fixed_code != original_code:
                context['code'] = fixed_code
                return (True, context)
        
        # Cannot auto-fix, need human intervention
        return (False, context)
    
    def _handle_logic_error(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle logic errors by triggering replanning."""
        # Signal that replanning is needed
        context['needs_replan'] = True
        context['error_context'] = str(error)
        
        # Don't retry the same approach - needs new plan
        return (False, context)
    
    def _handle_resource_exhausted(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle resource exhaustion with cleanup and retry."""
        # Attempt cleanup if cleanup function provided
        cleanup_fn = context.get('cleanup_function')
        if cleanup_fn:
            try:
                cleanup_fn()
                return (True, context)
            except Exception as cleanup_error:
                logger.error(f"Cleanup failed: {cleanup_error}")
        
        # Wait longer before retrying resource issues
        context['extended_delay'] = True
        
        # Retry only once for resource issues
        return (retry_count == 0, context)
    
    def _handle_validation_error(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        retry_count: int
    ) -> tuple:
        """Handle validation errors by fixing parameters."""
        # If parameter fixer available, use it
        param_fixer = context.get('parameter_fixer')
        if param_fixer and hasattr(param_fixer, 'fix_parameters'):
            original_params = context.get('parameters', {})
            fixed_params = param_fixer.fix_parameters(original_params, str(error))
            
            if fixed_params != original_params:
                context['parameters'] = fixed_params
                return (True, context)
        
        # Cannot auto-fix validation
        return (False, context)


# Convenience functions for common patterns

def with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """
    Decorator to add retry logic to any function.
    
    Usage:
        @with_retry(max_retries=3, base_delay=1.0)
        def my_function():
            ...
    """
    config = RecoveryConfig(
        max_retries=max_retries,
        base_delay=base_delay
    )
    
    def decorator(operation: Callable):
        recovery = HierarchicalRecovery(config)
        
        def wrapper(*args, **kwargs):
            result = recovery.execute_with_recovery(
                operation=lambda: operation(*args, **kwargs),
                operation_name=operation.__name__
            )
            
            if not result.success:
                raise Exception(f"Operation failed after recovery: {result.error_message}")
            
            return result.recovered_value
        
        return wrapper
    
    return decorator


__all__ = [
    'HierarchicalRecovery',
    'ErrorType',
    'RecoveryStrategy',
    'RecoveryConfig',
    'RecoveryResult',
    'with_retry'
]
