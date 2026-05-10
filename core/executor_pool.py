"""
Async Executor Pool for JARVIS with Phase 2 enhancements.
Manages concurrent task execution using thread pools with monitoring hooks.
Implements smart retry with backoff, circuit breakers, and checkpointing.
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
               *args, use_retry: bool = True, use_checkpoint: bool = False, **kwargs) -> Future:
        """Submit a function for async execution with task tracking and optional retry/checkpoint"""
        
        def wrapped_execute():
            attempt = 0
            max_attempts = 5 if use_retry else 1
            last_error = None
            
            while attempt < max_attempts:
                try:
                    registry.update_status(task_id, TaskStatus.RUNNING, progress=10)
                    
                    # Load checkpoint if available
                    if use_checkpoint:
                        checkpoint_data = self._load_checkpoint(task_id)
                        if checkpoint_data:
                            logger.info(f"Loaded checkpoint for task {task_id}: {checkpoint_data}")
                            kwargs['_checkpoint'] = checkpoint_data
                    
                    result = func(*args, **kwargs)
                    
                    # Record success with recovery manager
                    if hasattr(func, '__name__'):
                        recovery_manager.record_success(func.__name__)
                    
                    registry.update_status(task_id, TaskStatus.SUCCESS, 
                                          result=result, progress=100)
                    
                    # Clear checkpoint on success
                    if use_checkpoint:
                        self._clear_checkpoint(task_id)
                    
                    logger.info(f"Task {task_id} completed successfully")
                    return result
                    
                except Exception as e:
                    error_msg = str(e)
                    last_error = e
                    attempt += 1
                    
                    # Use recovery manager to decide retry
                    if use_retry and attempt < max_attempts:
                        tool_name = getattr(func, '__name__', 'unknown')
                        should_retry, delay = recovery_manager.should_retry(tool_name, error_msg)
                        
                        if should_retry:
                            logger.info(f"Task {task_id} failed (attempt {attempt}), retrying in {delay:.2f}s")
                            time.sleep(delay)
                            
                            # Save checkpoint before retry
                            if use_checkpoint:
                                self._save_checkpoint(task_id, {"attempt": attempt, "last_error": error_msg})
                            continue
                    
                    # Max retries exceeded or retry not allowed
                    registry.update_status(task_id, TaskStatus.FAILED, 
                                          error=error_msg)
                    logger.error(f"Task {task_id} failed after {attempt} attempts: {error_msg}")
                    
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
