"""
Async Executor Pool for JARVIS.
Manages concurrent task execution using thread pools with monitoring hooks.
Integrated with streaming, progress reporting, and observability.
"""
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import Any, Callable, Optional, Dict, List
import logging

from core.task_registry import registry, TaskStatus, Task
from core.streaming_manager import streaming_manager, StreamingResponse
from core.progress_reporter import progress_manager, ProgressReporter
from core.observability import observability

logger = logging.getLogger(__name__)


class TaskLifecycleEvent:
    """Represents an event in the task lifecycle."""
    STARTED = "started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STREAM_CHUNK = "stream_chunk"
    PROGRESS_UPDATE = "progress_update"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutorPool:
    """
    Enhanced ExecutorPool with integrated UX and observability features.
    
    Features:
    - Event emission at task lifecycle stages
    - Streaming response integration
    - Progress reporting hooks
    - Observability metrics collection
    """
    
    def __init__(self, max_workers: int = 10, enable_observability: bool = True):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._task_futures: Dict[str, Future] = {}
        self._task_metadata: Dict[str, Dict[str, Any]] = {}
        self._event_listeners: List[Callable[[str, str, Any], None]] = []
        self._lock = threading.Lock()
        self._shutdown = False
        self._enable_observability = enable_observability
        logger.info(f"ExecutorPool initialized with {max_workers} workers")
    
    def add_event_listener(self, listener: Callable[[str, str, Any], None]):
        """
        Add a listener for task lifecycle events.
        
        Listener signature: listener(event_type: str, task_id: str, data: Any)
        """
        self._event_listeners.append(listener)
    
    def _emit_event(self, event_type: str, task_id: str, data: Any = None):
        """Emit an event to all registered listeners."""
        for listener in self._event_listeners:
            try:
                listener(event_type, task_id, data)
            except Exception as e:
                logger.warning(f"Event listener error: {e}")
    
    def submit(self, func: Callable, task_id: str, 
               *args, enable_streaming: bool = True,
               enable_progress: bool = True,
               estimated_steps: int = 0,
               **kwargs) -> Future:
        """
        Submit a function for async execution with enhanced tracking.
        
        Args:
            func: Function to execute
            task_id: Unique task identifier
            *args: Positional arguments for func
            enable_streaming: Whether to create a streaming response
            enable_progress: Whether to track progress
            estimated_steps: Estimated number of steps for ETA calculation
            **kwargs: Keyword arguments for func
            
        Returns:
            Future object for the submitted task
        """
        
        # Initialize observability
        if self._enable_observability:
            correlation_id = observability.start_task(task_id, func.__name__)
        else:
            correlation_id = None
        
        # Initialize streaming
        stream = None
        if enable_streaming:
            stream = streaming_manager.create_stream(
                task_id, 
                enable_thoughts=False
            )
            stream.send_status("initializing", 0, "Task submitted")
        
        # Initialize progress reporter
        reporter = None
        if enable_progress:
            reporter = progress_manager.create_reporter(
                task_id, 
                estimated_steps=estimated_steps
            )
        
        # Store metadata
        with self._lock:
            self._task_metadata[task_id] = {
                "func_name": func.__name__,
                "start_time": None,
                "stream": stream,
                "reporter": reporter,
                "correlation_id": correlation_id,
                "steps": []
            }
        
        def wrapped_execute():
            start_time = time.time()
            
            with self._lock:
                self._task_metadata[task_id]["start_time"] = start_time
            
            # Emit started event
            self._emit_event(TaskLifecycleEvent.STARTED, task_id, {
                "func_name": func.__name__,
                "timestamp": start_time
            })
            
            try:
                # Update status
                registry.update_status(task_id, TaskStatus.RUNNING, progress=10)
                
                if stream:
                    stream.send_status("running", 10, "Starting execution")
                
                if reporter:
                    reporter.record_step_start(func.__name__)
                
                # Execute the function
                result = func(*args, **kwargs)
                
                # Success
                end_time = time.time()
                duration = end_time - start_time
                
                if reporter:
                    reporter.record_step_complete(func.__name__, "completed")
                
                registry.update_status(task_id, TaskStatus.SUCCESS, 
                                      result=result, progress=100)
                
                if stream:
                    stream.send_status("completed", 100, "Task completed successfully")
                    stream.complete(result)
                
                if self._enable_observability:
                    observability.complete_task(task_id, success=True, result=result)
                
                # Emit completed event
                self._emit_event(TaskLifecycleEvent.COMPLETED, task_id, {
                    "duration": duration,
                    "result": result
                })
                
                logger.info(f"Task {task_id} completed successfully in {duration:.2f}s")
                return result
                
            except Exception as e:
                error_msg = str(e)
                end_time = time.time()
                
                if reporter:
                    reporter.record_step_complete(func.__name__, "failed", error_msg)
                
                registry.update_status(task_id, TaskStatus.FAILED, 
                                      error=error_msg)
                
                if stream:
                    stream.send_error(error_msg, type(e).__name__)
                    stream.complete()
                
                if self._enable_observability:
                    observability.record_error(task_id, error_msg, type(e).__name__)
                
                # Emit failed event
                self._emit_event(TaskLifecycleEvent.FAILED, task_id, {
                    "error": error_msg,
                    "error_type": type(e).__name__
                })
                
                logger.error(f"Task {task_id} failed: {error_msg}")
                raise
        
        future = self._executor.submit(wrapped_execute)
        
        with self._lock:
            self._task_futures[task_id] = future
        
        registry.update_status(task_id, TaskStatus.PENDING, progress=5)
        
        if stream:
            stream.send_status("pending", 5, "Task queued")
        
        logger.debug(f"Task {task_id} submitted to executor pool")
        return future
    
    def record_step(self, task_id: str, step_name: str, 
                    duration: float, success: bool = True,
                    details: Optional[str] = None):
        """
        Record a step completion for a running task.
        
        This method can be called from within a task function to report
        intermediate progress.
        """
        with self._lock:
            metadata = self._task_metadata.get(task_id)
        
        if not metadata:
            return
        
        # Update progress reporter
        if metadata["reporter"]:
            metadata["reporter"].record_step_complete(step_name, 
                                                       "completed" if success else "failed",
                                                       details)
        
        # Update observability
        if self._enable_observability:
            observability.record_step(task_id, step_name, duration, success)
        
        # Emit event
        self._emit_event(TaskLifecycleEvent.STEP_COMPLETED, task_id, {
            "step": step_name,
            "duration": duration,
            "success": success,
            "details": details
        })
        
        # Update stream
        if metadata["stream"]:
            progress_data = metadata["reporter"].get_progress_data() if metadata["reporter"] else {}
            metadata["stream"].send_status(
                "running",
                progress_data.get("progress_percent", 50),
                f"Completed: {step_name}"
            )
    
    def get_future(self, task_id: str) -> Optional[Future]:
        """Get the Future object for a task"""
        with self._lock:
            return self._task_futures.get(task_id)
    
    def get_task_metadata(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a task including stream and reporter."""
        with self._lock:
            return self._task_metadata.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Attempt to cancel a running task"""
        with self._lock:
            future = self._task_futures.get(task_id)
            if future and not future.done():
                cancelled = future.cancel()
                if cancelled:
                    registry.update_status(task_id, TaskStatus.CANCELLED)
                    
                    # Emit cancelled event
                    self._emit_event(TaskLifecycleEvent.CANCELLED, task_id)
                    
                    # Update stream
                    metadata = self._task_metadata.get(task_id)
                    if metadata and metadata["stream"]:
                        metadata["stream"].send_status("cancelled", 0, "Task cancelled by user")
                        metadata["stream"].complete()
                    
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
    
    def get_progress_summary(self, task_id: str) -> Optional[str]:
        """Get human-readable progress summary for a task."""
        reporter = progress_manager.get_reporter(task_id)
        if reporter:
            return reporter.generate_summary()
        return None
    
    def shutdown(self, wait: bool = True):
        """Shutdown the executor pool"""
        self._shutdown = True
        
        # Close all active streams
        for task_id, metadata in self._task_metadata.items():
            if metadata and metadata["stream"]:
                metadata["stream"].complete()
        
        logger.info("Shutting down ExecutorPool...")
        self._executor.shutdown(wait=wait)
    
    def get_active_count(self) -> int:
        """Get number of currently running tasks"""
        with self._lock:
            return sum(1 for f in self._task_futures.values() if not f.done())
    
    def get_all_progress(self) -> Dict[str, str]:
        """Get progress summaries for all active tasks."""
        return progress_manager.get_all_summaries()


# Global instance
pool = ExecutorPool(max_workers=10)
