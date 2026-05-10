"""
Async Executor Pool for JARVIS with Phase 2 & 4 enhancements.
Manages concurrent task execution using thread pools with monitoring hooks.
Implements smart retry with backoff, circuit breakers, and checkpointing.
Integrated with streaming, progress reporting, and observability systems.
"""
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import Any, Callable, Optional, Dict, Tuple
import logging
import json
import os

from core.task_registry import registry, TaskStatus, Task
from core.recovery import recovery_manager
from core.streaming_manager import streaming_manager, StreamingResponse
from core.progress_reporter import progress_registry, ProgressReporter
from core.observability import observability

logger = logging.getLogger(__name__)

# Checkpoint directory for long-running tasks
CHECKPOINT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "checkpoints")
os.makedirs(CHECKPOINT_DIR, exist_ok=True)


class ExecutorPool:
    def __init__(self, max_workers: int = 10):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._task_futures: Dict[str, Future] = {}
        self._lock = threading.Lock()
        self._shutdown = False
        self._checkpoint_interval = 30  # Save checkpoint every 30 seconds
        logger.info(f"ExecutorPool initialized with {max_workers} workers")

    def submit(self, func: Callable, task_id: str, 
               *args, use_retry: bool = True, use_checkpoint: bool = False,
               enable_streaming: bool = True, track_progress: bool = True,
               **kwargs) -> Future:
        """Submit a function for async execution with task tracking and optional retry/checkpoint"""
        
        # Initialize Phase 4 components
        stream = None
        reporter = None
        obs_span = None
        
        if enable_streaming:
            stream = streaming_manager.create_stream(task_id=task_id, expose_thoughts=False)
        
        if track_progress:
            reporter = progress_registry.create_reporter(
                task_id, 
                task_description=getattr(func, '__name__', 'unknown')
            )
            reporter.start()
        
        # Start observability tracing
        obs_span = observability.start_task(
            task_id, 
            task_type=getattr(func, '__name__', 'unknown'),
            metadata={"args_count": len(args), "kwargs_count": len(kwargs)}
        )
        
        def wrapped_execute():
            attempt = 0
            max_attempts = 5 if use_retry else 1
            last_error = None
            
            while attempt < max_attempts:
                try:
                    registry.update_status(task_id, TaskStatus.RUNNING, progress=10)
                    
                    # Emit progress event
                    if reporter:
                        reporter.add_step(getattr(func, '__name__', 'step'), details={"attempt": attempt + 1})
                    
                    # Emit streaming status
                    if stream:
                        stream.send_status("running", {"attempt": attempt + 1})
                    
                    # Load checkpoint if available
                    if use_checkpoint:
                        checkpoint_data = self._load_checkpoint(task_id)
                        if checkpoint_data:
                            logger.info(f"Loaded checkpoint for task {task_id}: {checkpoint_data}")
                            kwargs['_checkpoint'] = checkpoint_data
                    
                    step_start = time.time()
                    result = func(*args, **kwargs)
                    step_duration = time.time() - step_start
                    
                    # Record success with recovery manager
                    if hasattr(func, '__name__'):
                        recovery_manager.record_success(func.__name__)
                    
                    # Record observability metrics
                    observability.record_step(task_id, getattr(func, '__name__', 'step'), 
                                             duration=step_duration, success=True)
                    
                    registry.update_status(task_id, TaskStatus.SUCCESS, 
                                          result=result, progress=100)
                    
                    # Complete progress tracking
                    if reporter:
                        reporter.complete_step(reporter._steps[-1].step_id if reporter._steps else "step_1")
                        reporter.add_milestone("task_complete", "Task finished successfully")
                    
                    # Complete streaming
                    if stream:
                        stream.send_status("completed", {"result": str(result)[:100] if result else None})
                        stream.complete()
                    
                    # Clear checkpoint on success
                    if use_checkpoint:
                        self._clear_checkpoint(task_id)
                    
                    logger.info(f"Task {task_id} completed successfully")
                    return result
                    
                except Exception as e:
                    error_msg = str(e)
                    last_error = e
                    attempt += 1
                    
                    # Record failure in observability
                    observability.record_step(task_id, getattr(func, '__name__', 'step'),
                                             success=False)
                    
                    # Record failure for contextual help
                    from core.contextual_help import contextual_help
                    contextual_help.record_failure(getattr(func, '__name__', 'unknown'))
                    
                    # Use recovery manager to decide retry
                    if use_retry and attempt < max_attempts:
                        tool_name = getattr(func, '__name__', 'unknown')
                        should_retry, delay = recovery_manager.should_retry(tool_name, error_msg)
                        
                        if should_retry:
                            logger.info(f"Task {task_id} failed (attempt {attempt}), retrying in {delay:.2f}s")
                            
                            # Emit error via streaming
                            if stream:
                                stream.send_error(error_msg, error_type="retryable", recoverable=True)
                                stream.send_status("retrying", {"delay": delay, "attempt": attempt})
                            
                            time.sleep(delay)
                            
                            # Save checkpoint before retry
                            if use_checkpoint:
                                self._save_checkpoint(task_id, {"attempt": attempt, "last_error": error_msg})
                            continue
                    
                    # Max retries exceeded or retry not allowed
                    registry.update_status(task_id, TaskStatus.FAILED, 
                                          error=error_msg)
                    logger.error(f"Task {task_id} failed after {attempt} attempts: {error_msg}")
                    
                    # Emit final error via streaming
                    if stream:
                        stream.send_error(error_msg, error_type="fatal", recoverable=False)
                        stream.complete(final_summary=f"Failed after {attempt} attempts")
                    
                    # Update progress reporter
                    if reporter:
                        if reporter._steps:
                            reporter.complete_step(reporter._steps[-1].step_id, status="failed")
                    
                    # Complete observability span
                    observability.complete_task(task_id, success=False, result_summary=error_msg)
                    
                    # Save final checkpoint for manual recovery
                    if use_checkpoint:
                        self._save_checkpoint(task_id, {
                            "failed": True,
                            "attempts": attempt,
                            "last_error": error_msg
                        })
                    
                    raise
            
            # Should not reach here, but just in case
            registry.update_status(task_id, TaskStatus.FAILED, error=str(last_error))
            observability.complete_task(task_id, success=False, result_summary=str(last_error))
            raise last_error

        future = self._executor.submit(wrapped_execute)
        
        with self._lock:
            self._task_futures[task_id] = future
        
        registry.update_status(task_id, TaskStatus.PENDING, progress=5)
        logger.debug(f"Task {task_id} submitted to executor pool")
        return future

    def submit_with_retry(self, func: Callable, task_id: str, 
                         *args, max_retries: int = 3, **kwargs) -> Future:
        """Submit a task with explicit retry configuration"""
        # Override default retry behavior
        return self.submit(func, task_id, *args, use_retry=True, **kwargs)

    def submit_with_checkpoint(self, func: Callable, task_id: str,
                              *args, checkpoint_interval: int = 30, **kwargs) -> Future:
        """Submit a long-running task with periodic checkpointing"""
        self._checkpoint_interval = checkpoint_interval
        return self.submit(func, task_id, *args, use_checkpoint=True, **kwargs)

    def _save_checkpoint(self, task_id: str, data: dict):
        """Save task checkpoint to disk"""
        checkpoint_file = os.path.join(CHECKPOINT_DIR, f"{task_id}.json")
        checkpoint_data = {
            "task_id": task_id,
            "timestamp": time.time(),
            "data": data
        }
        try:
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            logger.debug(f"Saved checkpoint for task {task_id}")
        except Exception as e:
            logger.warning(f"Failed to save checkpoint for {task_id}: {e}")

    def _load_checkpoint(self, task_id: str) -> Optional[dict]:
        """Load task checkpoint from disk"""
        checkpoint_file = os.path.join(CHECKPOINT_DIR, f"{task_id}.json")
        try:
            if os.path.exists(checkpoint_file):
                with open(checkpoint_file, 'r') as f:
                    checkpoint_data = json.load(f)
                
                # Check if checkpoint is recent (within 24 hours)
                age_hours = (time.time() - checkpoint_data.get("timestamp", 0)) / 3600
                if age_hours < 24:
                    return checkpoint_data.get("data", {})
                else:
                    # Stale checkpoint, clear it
                    self._clear_checkpoint(task_id)
        except Exception as e:
            logger.warning(f"Failed to load checkpoint for {task_id}: {e}")
        return None

    def _clear_checkpoint(self, task_id: str):
        """Clear task checkpoint"""
        checkpoint_file = os.path.join(CHECKPOINT_DIR, f"{task_id}.json")
        try:
            if os.path.exists(checkpoint_file):
                os.remove(checkpoint_file)
                logger.debug(f"Cleared checkpoint for task {task_id}")
        except Exception as e:
            logger.warning(f"Failed to clear checkpoint for {task_id}: {e}")

    def get_future(self, task_id: str) -> Optional[Future]:
        """Get the Future object for a task"""
        with self._lock:
            return self._task_futures.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Attempt to cancel a running task"""
        with self._lock:
            future = self._task_futures.get(task_id)
            if future and not future.done():
                cancelled = future.cancel()
                if cancelled:
                    registry.update_status(task_id, TaskStatus.CANCELLED)
                    logger.info(f"Task {task_id} cancelled")
                return cancelled
        return False

    def get_task_status(self, task_id: str) -> Optional[str]:
        """Get current status of a task"""
        with self._lock:
            future = self._task_futures.get(task_id)
        
        if not future:
            return None
        
        if future.done():
            if future.cancelled():
                return "cancelled"
            try:
                future.result()  # Will raise if failed
                return "success"
            except Exception:
                return "failed"
        else:
            return "running"

    def shutdown(self, wait: bool = True):
        """Shutdown the executor pool"""
        self._shutdown = True
        logger.info("Shutting down ExecutorPool...")
        self._executor.shutdown(wait=wait)

    def get_active_count(self) -> int:
        """Get number of currently running tasks"""
        with self._lock:
            return sum(1 for f in self._task_futures.values() if not f.done())

    def get_recovery_status(self, task_id: str) -> dict:
        """Get recovery-related status for a task"""
        return {
            "task_id": task_id,
            "has_checkpoint": self._load_checkpoint(task_id) is not None,
            "circuit_breaker": recovery_manager.get_circuit_breaker_status(),
            "failure_summary": recovery_manager.get_failure_summary()
        }

# Global instance
pool = ExecutorPool(max_workers=10)
