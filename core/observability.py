"""
Observability Module for JARVIS.
Provides centralized metrics collection, distributed tracing, and structured logging.
"""
import time
import json
import uuid
import threading
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import statistics
import logging


class MetricType(Enum):
    """Types of metrics that can be collected."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricPoint:
    """Represents a single metric data point."""
    name: str
    value: float
    timestamp: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "type": self.metric_type.value,
            "labels": self.labels
        }


@dataclass
class TraceSpan:
    """Represents a span in distributed tracing."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "running"  # running, ok, error
    
    @property
    def duration(self) -> Optional[float]:
        """Get span duration in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation (OpenTelemetry compatible)."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (self.duration or 0) * 1000,
            "tags": self.tags,
            "logs": self.logs,
            "status": self.status
        }


class MetricsCollector:
    """
    Centralized metrics collection with support for various metric types.
    
    Features:
    - Counters for success rates and request counts
    - Gauges for current values (e.g., active tasks)
    - Histograms for latency distributions
    - Summaries for token usage and efficiency
    """
    
    def __init__(self):
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._summaries: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "sum": 0, "values": []}
        )
        self._lock = threading.Lock()
        self._export_callbacks: List[Callable] = []
    
    def increment_counter(self, name: str, value: float = 1, 
                          labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value
    
    def set_gauge(self, name: str, value: float,
                  labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
    
    def record_histogram(self, name: str, value: float,
                         labels: Optional[Dict[str, str]] = None):
        """Record a value in a histogram."""
        with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(value)
    
    def record_summary(self, name: str, value: float,
                       labels: Optional[Dict[str, str]] = None):
        """Record a value in a summary."""
        with self._lock:
            key = self._make_key(name, labels)
            self._summaries[key]["count"] += 1
            self._summaries[key]["sum"] += value
            self._summaries[key]["values"].append(value)
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create a unique key for labeled metrics."""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_counter(self, name: str, 
                    labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)
    
    def get_gauge(self, name: str,
                  labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        key = self._make_key(name, labels)
        return self._gauges.get(key)
    
    def get_histogram_stats(self, name: str,
                            labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Get statistical summary of histogram data."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        
        if not values:
            return {"count": 0}
        
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
            "p95": sorted(values)[int(len(values) * 0.95)] if len(values) >= 20 else max(values),
            "p99": sorted(values)[int(len(values) * 0.99)] if len(values) >= 100 else max(values)
        }
    
    def get_summary_stats(self, name: str,
                          labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Get summary statistics."""
        key = self._make_key(name, labels)
        data = self._summaries.get(key, {"count": 0, "sum": 0, "values": []})
        
        if data["count"] == 0:
            return {"count": 0}
        
        return {
            "count": data["count"],
            "sum": data["sum"],
            "avg": data["sum"] / data["count"],
            "rate": data["count"] / max(1, time.time() - getattr(self, '_start_time', time.time()))
        }
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics in a structured format."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: self.get_histogram_stats(k.replace("{", "").split("}")[0] if "{" in k else k)
                    for k in self._histograms.keys()
                },
                "summaries": {
                    k: self.get_summary_stats(k.replace("{", "").split("}")[0] if "{" in k else k)
                    for k in self._summaries.keys()
                }
            }
    
    def register_export_callback(self, callback: Callable):
        """Register a callback to be called when metrics are exported."""
        self._export_callbacks.append(callback)
    
    def export(self) -> str:
        """Export metrics in Prometheus-compatible format."""
        lines = []
        
        # Export counters
        for key, value in self._counters.items():
            name = key.split("{")[0]
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{key} {value}")
        
        # Export gauges
        for key, value in self._gauges.items():
            name = key.split("{")[0]
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{key} {value}")
        
        # Export histogram stats
        for key in self._histograms.keys():
            name = key.split("{")[0] if "{" in key else key
            stats = self.get_histogram_stats(name)
            lines.append(f"# TYPE {name} histogram")
            lines.append(f'{name}_count{{}} {stats.get("count", 0)}')
            lines.append(f'{name}_sum{{}} {stats.get("sum", 0)}')
        
        result = "\n".join(lines)
        
        # Call export callbacks
        for callback in self._export_callbacks:
            try:
                callback(result)
            except Exception:
                pass
        
        return result
    
    def reset(self):
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._summaries.clear()


class Tracer:
    """
    Distributed tracing with OpenTelemetry-compatible structure.
    
    Features:
    - Unique trace IDs for request tracking
    - Span hierarchy with parent-child relationships
    - Tag and log attachment
    - Async boundary support
    """
    
    def __init__(self, service_name: str = "jarvis"):
        self.service_name = service_name
        self._active_spans: Dict[str, TraceSpan] = {}
        self._completed_traces: Dict[str, List[TraceSpan]] = defaultdict(list)
        self._lock = threading.Lock()
        self._sampling_rate = 1.0  # Sample all traces by default
    
    def start_trace(self, operation_name: str, 
                    tags: Optional[Dict[str, Any]] = None) -> TraceSpan:
        """Start a new trace."""
        trace_id = str(uuid.uuid4().hex)
        span_id = str(uuid.uuid4().hex[:16])
        
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            operation_name=operation_name,
            start_time=time.time(),
            tags={**tags, "service.name": self.service_name} if tags else {"service.name": self.service_name}
        )
        
        with self._lock:
            self._active_spans[span_id] = span
        
        return span
    
    def start_span(self, trace_id: str, operation_name: str,
                   parent_span_id: Optional[str] = None,
                   tags: Optional[Dict[str, Any]] = None) -> TraceSpan:
        """Start a new span within an existing trace."""
        span_id = str(uuid.uuid4().hex[:16])
        
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            start_time=time.time(),
            tags={**tags, "service.name": self.service_name} if tags else {"service.name": self.service_name}
        )
        
        with self._lock:
            self._active_spans[span_id] = span
        
        return span
    
    def end_span(self, span: TraceSpan, status: str = "ok",
                 tags: Optional[Dict[str, Any]] = None):
        """End a span."""
        span.end_time = time.time()
        span.status = status
        
        if tags:
            span.tags.update(tags)
        
        with self._lock:
            if span.span_id in self._active_spans:
                del self._active_spans[span.span_id]
                self._completed_traces[span.trace_id].append(span)
    
    def add_log(self, span: TraceSpan, event: str, 
                data: Optional[Dict[str, Any]] = None):
        """Add a log entry to a span."""
        log_entry = {
            "timestamp": time.time(),
            "event": event,
            "data": data or {}
        }
        span.logs.append(log_entry)
    
    def get_trace_context(self, span: TraceSpan) -> Dict[str, str]:
        """Get trace context for propagation (e.g., in HTTP headers)."""
        return {
            "traceparent": f"00-{span.trace_id}-{span.span_id}-01",
            "X-Trace-ID": span.trace_id,
            "X-Span-ID": span.span_id
        }
    
    def extract_context(self, headers: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Extract trace context from incoming request headers."""
        traceparent = headers.get("traceparent", "")
        
        if traceparent and len(traceparent.split("-")) == 4:
            _, trace_id, parent_span_id, _ = traceparent.split("-")
            return {
                "trace_id": trace_id,
                "parent_span_id": parent_span_id
            }
        
        # Fallback to individual headers
        trace_id = headers.get("X-Trace-ID")
        span_id = headers.get("X-Span-ID")
        
        if trace_id:
            return {
                "trace_id": trace_id,
                "parent_span_id": span_id
            }
        
        return None
    
    def get_completed_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get all spans for a completed trace."""
        spans = self._completed_traces.get(trace_id, [])
        return [span.to_dict() for span in spans]
    
    def cleanup_old_traces(self, max_age_seconds: float = 3600):
        """Remove completed traces older than max_age_seconds."""
        current_time = time.time()
        to_remove = []
        
        for trace_id, spans in self._completed_traces.items():
            if spans and all(
                s.end_time and (current_time - s.end_time) > max_age_seconds 
                for s in spans
            ):
                to_remove.append(trace_id)
        
        for trace_id in to_remove:
            del self._completed_traces[trace_id]
        
        return len(to_remove)


class StructuredLogger:
    """
    Structured logging with correlation IDs and consistent schema.
    
    Features:
    - JSON-formatted logs for easy parsing
    - Correlation ID injection for request tracing
    - Consistent schema across all log entries
    - Integration with ELK/Datadog
    """
    
    def __init__(self, logger_name: str = "jarvis", 
                 tracer: Optional[Tracer] = None):
        self.logger = logging.getLogger(logger_name)
        self.tracer = tracer
        self._default_fields = {
            "service": "jarvis",
            "version": "1.0.0"
        }
    
    def _format_log(self, level: str, message: str, 
                    extra: Optional[Dict[str, Any]] = None,
                    correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Format log entry with consistent schema."""
        entry = {
            "timestamp": time.time(),
            "level": level,
            "message": message,
            **self._default_fields
        }
        
        if correlation_id:
            entry["correlation_id"] = correlation_id
        
        if extra:
            entry.update(extra)
        
        return entry
    
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None,
             correlation_id: Optional[str] = None):
        """Log info level message."""
        entry = self._format_log("INFO", message, extra, correlation_id)
        self.logger.info(json.dumps(entry))
    
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None,
                correlation_id: Optional[str] = None):
        """Log warning level message."""
        entry = self._format_log("WARNING", message, extra, correlation_id)
        self.logger.warning(json.dumps(entry))
    
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None,
              correlation_id: Optional[str] = None):
        """Log error level message."""
        entry = self._format_log("ERROR", message, extra, correlation_id)
        self.logger.error(json.dumps(entry))
    
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None,
              correlation_id: Optional[str] = None):
        """Log debug level message."""
        entry = self._format_log("DEBUG", message, extra, correlation_id)
        self.logger.debug(json.dumps(entry))
    
    def log_event(self, event_type: str, event_data: Dict[str, Any],
                  correlation_id: Optional[str] = None):
        """Log a structured event."""
        entry = self._format_log(
            "INFO", 
            f"Event: {event_type}",
            {"event_type": event_type, "event_data": event_data},
            correlation_id
        )
        self.logger.info(json.dumps(entry))


class ObservabilityManager:
    """
    Central manager coordinating all observability components.
    
    Provides unified interface for:
    - Metrics collection
    - Distributed tracing
    - Structured logging
    """
    
    def __init__(self, service_name: str = "jarvis"):
        self.metrics = MetricsCollector()
        self.tracer = Tracer(service_name=service_name)
        self.logger = StructuredLogger(tracer=self.tracer)
        self._task_correlations: Dict[str, str] = {}
    
    def start_task(self, task_id: str, operation: str) -> str:
        """
        Start observability tracking for a task.
        
        Returns correlation ID for the task.
        """
        # Start trace
        span = self.tracer.start_trace(operation)
        
        # Store correlation
        correlation_id = span.trace_id
        self._task_correlations[task_id] = correlation_id
        
        # Log start
        self.logger.info(
            f"Task started: {operation}",
            extra={"task_id": task_id, "operation": operation},
            correlation_id=correlation_id
        )
        
        # Record metrics
        self.metrics.increment_counter("tasks_started")
        self.metrics.set_gauge("active_tasks", 
                               len(self._task_correlations))
        
        return correlation_id
    
    def record_step(self, task_id: str, step_name: str, 
                    duration: float, success: bool = True):
        """Record a task step completion."""
        correlation_id = self._task_correlations.get(task_id)
        
        # Record metrics
        self.metrics.record_histogram("step_duration_seconds", duration)
        self.metrics.increment_counter(
            "steps_completed" if success else "steps_failed",
            labels={"step": step_name}
        )
        
        # Log
        self.logger.info(
            f"Step completed: {step_name}",
            extra={
                "task_id": task_id,
                "step": step_name,
                "duration": duration,
                "success": success
            },
            correlation_id=correlation_id
        )
    
    def complete_task(self, task_id: str, success: bool = True,
                      result: Optional[Any] = None):
        """Mark a task as complete."""
        correlation_id = self._task_correlations.pop(task_id, None)
        
        # Record metrics
        self.metrics.increment_counter(
            "tasks_completed" if success else "tasks_failed"
        )
        self.metrics.set_gauge("active_tasks", len(self._task_correlations))
        
        # Log
        self.logger.info(
            f"Task completed: {'success' if success else 'failed'}",
            extra={
                "task_id": task_id,
                "success": success,
                "result": str(result)[:100] if result else None
            },
            correlation_id=correlation_id
        )
    
    def record_error(self, task_id: str, error: str, 
                     error_type: str = "Error"):
        """Record an error occurrence."""
        correlation_id = self._task_correlations.get(task_id)
        
        # Record metrics
        self.metrics.increment_counter("errors_total", 
                                       labels={"type": error_type})
        
        # Log
        self.logger.error(
            f"Error: {error}",
            extra={
                "task_id": task_id,
                "error_type": error_type,
                "error": error
            },
            correlation_id=correlation_id
        )
    
    def record_token_usage(self, task_id: str, tokens: int, 
                           token_type: str = "total"):
        """Record token usage for LLM calls."""
        correlation_id = self._task_correlations.get(task_id)
        
        self.metrics.record_summary(
            "tokens_used",
            tokens,
            labels={"type": token_type}
        )
        
        self.logger.debug(
            f"Token usage: {tokens} ({token_type})",
            extra={"task_id": task_id, "tokens": tokens, "token_type": token_type},
            correlation_id=correlation_id
        )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status."""
        metrics = self.metrics.get_all_metrics()
        
        return {
            "status": "healthy",
            "active_tasks": len(self._task_correlations),
            "metrics_summary": {
                "total_tasks_started": metrics["counters"].get("tasks_started", 0),
                "total_tasks_completed": metrics["counters"].get("tasks_completed", 0),
                "total_errors": metrics["counters"].get("errors_total", 0)
            },
            "success_rate": self._calculate_success_rate(metrics),
            "avg_latency": self._calculate_avg_latency(metrics)
        }
    
    def _calculate_success_rate(self, metrics: Dict[str, Any]) -> float:
        """Calculate overall task success rate."""
        completed = metrics["counters"].get("tasks_completed", 0)
        failed = metrics["counters"].get("tasks_failed", 0)
        total = completed + failed
        
        if total == 0:
            return 1.0
        
        return completed / total
    
    def _calculate_avg_latency(self, metrics: Dict[str, Any]) -> float:
        """Calculate average step latency."""
        hist_stats = metrics["histograms"].get("step_duration_seconds", {})
        return hist_stats.get("mean", 0)


# Global instance
observability = ObservabilityManager()
