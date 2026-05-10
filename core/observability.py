"""
Observability Module for JARVIS Phase 4.
Centralized metrics collection, distributed tracing, and structured logging.
OpenTelemetry-compatible structure for easy integration with monitoring systems.
"""
import time
import uuid
import json
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from contextlib import contextmanager
import threading
import os

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Represents a single metric data point."""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: str = "gauge"  # gauge, counter, histogram
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "tags": self.tags,
            "type": self.metric_type
        }


@dataclass
class Span:
    """
    Represents a span in distributed tracing.
    Compatible with OpenTelemetry span structure.
    """
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "OK"  # OK, ERROR, UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (self.end_time - self.start_time) * 1000 if self.end_time else None,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events
        }
    
    @property
    def duration(self) -> Optional[float]:
        """Get span duration in seconds."""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None


class MetricsCollector:
    """
    Centralized metrics collection system.
    Supports counters, gauges, and histograms.
    """
    
    def __init__(self):
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._export_callbacks: List[Callable] = []
        logger.info("MetricsCollector initialized")
    
    def increment_counter(self, name: str, value: float = 1.0, 
                         tags: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        key = self._make_key(name, tags)
        with self._lock:
            self._counters[key] += value
        logger.debug(f"Counter incremented: {key} = {self._counters[key]}")
    
    def set_gauge(self, name: str, value: float, 
                 tags: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        key = self._make_key(name, tags)
        with self._lock:
            self._gauges[key] = value
        logger.debug(f"Gauge set: {key} = {value}")
    
    def record_histogram(self, name: str, value: float,
                        tags: Optional[Dict[str, str]] = None):
        """Record a value in a histogram."""
        key = self._make_key(name, tags)
        with self._lock:
            self._histograms[key].append(value)
            # Keep only last 1000 values to prevent memory growth
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
        logger.debug(f"Histogram recorded: {key} = {value}")
    
    def _make_key(self, name: str, tags: Optional[Dict[str, str]]) -> str:
        """Create a unique key from name and tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"
    
    def get_counter(self, name: str, tags: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        key = self._make_key(name, tags)
        with self._lock:
            return self._counters.get(key, 0.0)
    
    def get_gauge(self, name: str, tags: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        key = self._make_key(name, tags)
        with self._lock:
            return self._gauges.get(key)
    
    def get_histogram_stats(self, name: str, 
                           tags: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get statistical summary of histogram values."""
        import statistics
        key = self._make_key(name, tags)
        with self._lock:
            values = self._histograms.get(key, [])
        
        if not values:
            return {"count": 0}
        
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
            "p95": sorted(values)[int(len(values) * 0.95)] if len(values) >= 20 else max(values),
            "p99": sorted(values)[int(len(values) * 0.99)] if len(values) >= 100 else max(values)
        }
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: self.get_histogram_stats(k) 
                              for k in self._histograms.keys()}
            }
    
    def register_export_callback(self, callback: Callable):
        """Register a callback to be called when metrics are exported."""
        self._export_callbacks.append(callback)
    
    def export(self) -> Dict[str, Any]:
        """Export metrics and call registered callbacks."""
        metrics = self.get_all_metrics()
        for callback in self._export_callbacks:
            try:
                callback(metrics)
            except Exception as e:
                logger.error(f"Export callback failed: {e}")
        return metrics
    
    def reset(self):
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
        logger.info("MetricsCollector reset")


class Tracer:
    """
    Distributed tracing implementation.
    Creates and manages trace spans with OpenTelemetry-compatible structure.
    """
    
    def __init__(self, service_name: str = "jarvis-agent"):
        self.service_name = service_name
        self._active_spans: Dict[str, Span] = {}
        self._completed_spans: List[Span] = []
        self._lock = threading.Lock()
        self._export_callbacks: List[Callable] = []
        logger.info(f"Tracer initialized for service: {service_name}")
    
    def start_span(self, name: str, parent_span: Optional[Span] = None,
                   attributes: Optional[Dict[str, Any]] = None) -> Span:
        """Start a new span."""
        trace_id = parent_span.trace_id if parent_span else str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        parent_span_id = parent_span.span_id if parent_span else None
        
        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            start_time=time.time(),
            attributes=attributes or {}
        )
        
        # Add service name attribute
        span.attributes["service.name"] = self.service_name
        
        with self._lock:
            self._active_spans[span_id] = span
        
        logger.debug(f"Span started: {name} (span_id={span_id[:8]}, trace_id={trace_id[:8]})")
        return span
    
    def end_span(self, span: Span, status: str = "OK",
                error: Optional[Exception] = None):
        """End a span."""
        span.end_time = time.time()
        span.status = status
        
        if error:
            span.attributes["error.message"] = str(error)
            span.attributes["error.type"] = type(error).__name__
            span.events.append({
                "name": "exception",
                "timestamp": time.time(),
                "attributes": {
                    "exception.message": str(error),
                    "exception.type": type(error).__name__
                }
            })
        
        with self._lock:
            self._active_spans.pop(span.span_id, None)
            self._completed_spans.append(span)
            
            # Keep only last 1000 completed spans
            if len(self._completed_spans) > 1000:
                self._completed_spans = self._completed_spans[-1000:]
        
        logger.debug(f"Span ended: {span.name} (duration={span.duration*1000:.2f}ms)")
    
    @contextmanager
    def trace(self, name: str, parent_span: Optional[Span] = None,
              attributes: Optional[Dict[str, Any]] = None):
        """Context manager for automatic span lifecycle management."""
        span = self.start_span(name, parent_span, attributes)
        try:
            yield span
            self.end_span(span, status="OK")
        except Exception as e:
            self.end_span(span, status="ERROR", error=e)
            raise
    
    def add_event(self, span: Span, event_name: str,
                 attributes: Optional[Dict[str, Any]] = None):
        """Add an event to a span."""
        event = {
            "name": event_name,
            "timestamp": time.time(),
            "attributes": attributes or {}
        }
        span.events.append(event)
        logger.debug(f"Event added to span {span.name}: {event_name}")
    
    def get_active_span(self, span_id: str) -> Optional[Span]:
        """Get an active span by ID."""
        with self._lock:
            return self._active_spans.get(span_id)
    
    def get_completed_spans(self, limit: int = 100) -> List[Span]:
        """Get recently completed spans."""
        with self._lock:
            return self._completed_spans[-limit:]
    
    def get_trace(self, trace_id: str) -> List[Span]:
        """Get all spans for a specific trace."""
        with self._lock:
            return [s for s in self._completed_spans if s.trace_id == trace_id]
    
    def register_export_callback(self, callback: Callable):
        """Register a callback for span export."""
        self._export_callbacks.append(callback)
    
    def export_spans(self) -> List[Dict[str, Any]]:
        """Export completed spans."""
        with self._lock:
            spans = [s.to_dict() for s in self._completed_spans[-100:]]
        
        for callback in self._export_callbacks:
            try:
                callback(spans)
            except Exception as e:
                logger.error(f"Span export callback failed: {e}")
        
        return spans


class StructuredLogger:
    """
    Structured logging with correlation IDs.
    Produces JSON-formatted logs for easy parsing by ELK/Datadog.
    """
    
    def __init__(self, base_logger: logging.Logger = None):
        self.logger = base_logger or logging.getLogger("jarvis.structured")
        self._correlation_id: Optional[str] = None
        self._default_fields: Dict[str, Any] = {}
        
        # Check if we should output JSON
        self._json_format = os.environ.get("LOG_FORMAT", "text").lower() == "json"
        
        logger.info(f"StructuredLogger initialized (format={'json' if self._json_format else 'text'})")
    
    def set_correlation_id(self, correlation_id: str):
        """Set the correlation ID for request tracing."""
        self._correlation_id = correlation_id
    
    def set_default_field(self, key: str, value: Any):
        """Set a default field to include in all log entries."""
        self._default_fields[key] = value
    
    def _format_message(self, level: str, message: str, 
                       **kwargs) -> Dict[str, Any]:
        """Format a log entry as a structured dictionary."""
        entry = {
            "timestamp": time.time(),
            "level": level,
            "message": message,
            "correlation_id": self._correlation_id,
            **self._default_fields,
            **kwargs
        }
        # Remove None values
        return {k: v for k, v in entry.items() if v is not None}
    
    def _log(self, level: str, message: str, **kwargs):
        """Internal log method."""
        entry = self._format_message(level, message, **kwargs)
        
        if self._json_format:
            log_line = json.dumps(entry)
        else:
            # Text format with structured info
            extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
            log_line = f"[{entry['correlation_id'] or 'no-correlation'}] {message} {extra_info}"
        
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(log_line)
    
    def info(self, message: str, **kwargs):
        """Log an info message."""
        self._log("INFO", message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log a debug message."""
        self._log("DEBUG", message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log a warning message."""
        self._log("WARNING", message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log an error message."""
        self._log("ERROR", message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log a critical message."""
        self._log("CRITICAL", message, **kwargs)
    
    @contextmanager
    def correlate(self, correlation_id: str):
        """Context manager for setting correlation ID."""
        old_id = self._correlation_id
        self._correlation_id = correlation_id
        try:
            yield
        finally:
            self._correlation_id = old_id


class ObservabilityEngine:
    """
    Centralized observability engine combining metrics, tracing, and logging.
    Provides a unified interface for all observability needs.
    """
    
    def __init__(self, service_name: str = "jarvis-agent"):
        self.metrics = MetricsCollector()
        self.tracer = Tracer(service_name)
        self.logger = StructuredLogger()
        self._task_metrics: Dict[str, Dict[str, Any]] = {}
        logger.info(f"ObservabilityEngine initialized for {service_name}")
    
    def start_task(self, task_id: str, task_type: str,
                  metadata: Optional[Dict[str, Any]] = None) -> Span:
        """
        Start tracking a new task.
        
        Args:
            task_id: Unique task identifier
            task_type: Type/category of task
            metadata: Additional task metadata
        
        Returns:
            The root span for this task
        """
        span = self.tracer.start_span(
            f"task.{task_type}",
            attributes={
                "task.id": task_id,
                "task.type": task_type,
                **(metadata or {})
            }
        )
        
        self._task_metrics[task_id] = {
            "start_time": time.time(),
            "task_type": task_type,
            "span_id": span.span_id,
            "steps": 0,
            "errors": 0
        }
        
        self.metrics.increment_counter("tasks.started", tags={"task_type": task_type})
        self.logger.set_correlation_id(task_id)
        self.logger.info(f"Task started: {task_type}", task_id=task_id)
        
        return span
    
    def complete_task(self, task_id: str, success: bool = True,
                     result_summary: Optional[str] = None):
        """
        Mark a task as complete.
        
        Args:
            task_id: Task identifier
            success: Whether task succeeded
            result_summary: Brief summary of results
        """
        task_data = self._task_metrics.pop(task_id, {})
        if not task_data:
            logger.warning(f"Complete called for unknown task: {task_id}")
            return
        
        elapsed = time.time() - task_data["start_time"]
        span_id = task_data.get("span_id")
        span = self.tracer.get_active_span(span_id) if span_id else None
        
        if span:
            self.tracer.end_span(
                span,
                status="OK" if success else "ERROR",
                error=None if success else Exception(result_summary)
            )
        
        # Record metrics
        task_type = task_data.get("task_type", "unknown")
        self.metrics.increment_counter(
            "tasks.completed",
            tags={"task_type": task_type, "success": str(success)}
        )
        self.metrics.record_histogram(
            "task.duration_seconds",
            elapsed,
            tags={"task_type": task_type}
        )
        self.metrics.increment_counter(
            "task.steps_total",
            task_data.get("steps", 0),
            tags={"task_type": task_type}
        )
        
        # Log completion
        self.logger.set_correlation_id(task_id)
        self.logger.info(
            f"Task completed: {'success' if success else 'failed'}",
            task_id=task_id,
            elapsed_seconds=elapsed,
            steps=task_data.get("steps", 0),
            result=result_summary
        )
    
    def record_step(self, task_id: str, step_name: str,
                   duration: Optional[float] = None,
                   success: bool = True):
        """
        Record a step within a task.
        
        Args:
            task_id: Task identifier
            step_name: Name of the step
            duration: Step duration in seconds
            success: Whether step succeeded
        """
        if task_id in self._task_metrics:
            self._task_metrics[task_id]["steps"] += 1
            if not success:
                self._task_metrics[task_id]["errors"] += 1
        
        self.metrics.increment_counter(
            "task.steps",
            tags={"step_name": step_name, "success": str(success)}
        )
        
        if duration is not None:
            self.metrics.record_histogram(
                "task.step_duration_seconds",
                duration,
                tags={"step_name": step_name}
            )
        
        self.logger.debug(
            f"Step {'completed' if success else 'failed'}: {step_name}",
            task_id=task_id,
            step_name=step_name,
            duration_seconds=duration
        )
    
    def record_token_usage(self, task_id: str, tokens: int,
                          token_type: str = "total"):
        """
        Record token usage for a task.
        
        Args:
            task_id: Task identifier
            tokens: Number of tokens used
            token_type: Type of tokens (prompt, completion, total)
        """
        self.metrics.increment_counter(
            "tokens.used",
            tokens,
            tags={"token_type": token_type}
        )
        
        if task_id in self._task_metrics:
            current_tokens = self._task_metrics[task_id].get("tokens", 0)
            self._task_metrics[task_id]["tokens"] = current_tokens + tokens
        
        self.logger.debug(
            f"Token usage: {tokens} {token_type}",
            task_id=task_id,
            tokens=tokens,
            token_type=token_type
        )
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current status/metrics for a task."""
        task_data = self._task_metrics.get(task_id)
        if not task_data:
            return None
        
        elapsed = time.time() - task_data["start_time"]
        return {
            "task_id": task_id,
            "task_type": task_data.get("task_type"),
            "elapsed_seconds": elapsed,
            "steps": task_data.get("steps", 0),
            "errors": task_data.get("errors", 0),
            "tokens": task_data.get("tokens", 0),
            "span_id": task_data.get("span_id")
        }
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data suitable for a metrics dashboard."""
        return {
            "metrics": self.metrics.get_all_metrics(),
            "active_traces": len(self.tracer._active_spans),
            "recent_spans": [s.to_dict() for s in self.tracer.get_completed_spans(20)],
            "active_tasks": len(self._task_metrics)
        }


# Global instance
observability = ObservabilityEngine()
