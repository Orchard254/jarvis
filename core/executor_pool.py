"""
Async Executor Pool for JARVIS.
Manages concurrent task execution using thread pools with monitoring hooks.
"""
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import Any, Callable, Optional, Dict
import logging

from core.task_registry import registry, TaskStatus, Task

logger = logging.getLogger(__name__)

class ExecutorPool:
    def __init__(self, max_workers: int = 10):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._task_futures: Dict[str, Future] = {}
        self._lock = threading.Lock()
        self._shutdown = False
        logger.info(f"ExecutorPool initialized with {max_workers} workers")

    def submit(self, func: Callable, task_id: str, 
               *args, **kwargs) -> Future:
        """Submit a function for async execution with task tracking"""
        
        def wrapped_execute():
            try:
                registry.update_status(task_id, TaskStatus.RUNNING, progress=10)
                result = func(*args, **kwargs)
                registry.update_status(task_id, TaskStatus.SUCCESS, 
                                      result=result, progress=100)
                logger.info(f"Task {task_id} completed successfully")
                return result
            except Exception as e:
                error_msg = str(e)
                registry.update_status(task_id, TaskStatus.FAILED, 
                                      error=error_msg)
                logger.error(f"Task {task_id} failed: {error_msg}")
                raise

        future = self._executor.submit(wrapped_execute)
        
        with self._lock:
            self._task_futures[task_id] = future
        
        registry.update_status(task_id, TaskStatus.PENDING, progress=5)
        logger.debug(f"Task {task_id} submitted to executor pool")
        return future

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

# Global instance
pool = ExecutorPool(max_workers=10)
