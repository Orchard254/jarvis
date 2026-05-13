# Phase 4 Implementation: User Experience & Observability

## Overview

Phase 4 focuses on making the agent's behavior **transparent**, **responsive**, and **measurable**. This implementation introduces comprehensive streaming, progress reporting, contextual help, and observability features.

## Files Created/Modified

### New Files

| File | Purpose |
|------|---------|
| `core/streaming_manager.py` | Chunked output with SSE support |
| `core/progress_reporter.py` | Natural language progress summaries |
| `core/contextual_help.py` | Context-aware suggestions |
| `core/observability.py` | Metrics, tracing, and structured logging |
| `PHASE4_IMPLEMENTATION.md` | This documentation |

### Modified Files

| File | Changes |
|------|---------|
| `core/executor_pool.py` | Integrated Phase 4 hooks |

---

## Key Features

### 1. Progressive Response Streaming (`streaming_manager.py`)

**Token-level streaming** reduces perceived latency by showing text as it generates.

```python
from core.streaming_manager import streaming_manager

# Create a stream
stream = streaming_manager.create_stream(task_id="task_123", expose_thoughts=False)

# Send different content types
stream.send_text("Hello")  # Regular text
stream.send_text(" world", is_token=True)  # Token-by-token

stream.send_tool_call("read_file", {"path": "config.json"})
stream.send_status("processing", {"step": 3})
stream.send_thought("Analyzing the data structure...")  # If expose_thoughts=True
stream.send_error("File not found", error_type="file_not_found")

# Complete the stream
stream.complete(final_summary="Task completed successfully")
```

**Content Types Supported:**
- `TEXT` - Regular text output (with optional token-level granularity)
- `TOOL_CALL` - Tool invocations with arguments
- `STATUS_UPDATE` - Progress status changes
- `THOUGHT` - Intermediate reasoning steps (optional)
- `ERROR` - Error notifications
- `COMPLETE` - Stream completion marker

**Output Formats:**
- Server-Sent Events (SSE): `data: {"chunk_id": "...", ...}\n\n`
- JSON Lines: `{"chunk_id": "...", ...}\n`

---

### 2. Natural Language Progress Reports (`progress_reporter.py`)

Automatic summarization converts technical logs into plain English.

```python
from core.progress_reporter import progress_registry

# Create reporter
reporter = progress_registry.create_reporter(
    task_id="task_123",
    task_description="Analyzing project files"
)
reporter.start()

# Track steps
step = reporter.add_step("read_file", details={"filename": "main.py"})
# ... do work ...
reporter.complete_step(step.step_id)

# Record milestones
reporter.add_milestone("files_read", "All source files loaded")

# Get human-readable summary
summary = reporter.generate_summary()
# "Working on: Analyzing project files. I've completed 5 steps, now analyzing main.py. Achieved: files_read. Estimated time remaining: 2 minutes."

# Get ETA
eta = reporter.get_eta()  # Returns (seconds, formatted_string)
```

**Features:**
- Automatic step duration tracking
- Rolling average ETA calculation
- Milestone markers for long-running tasks
- Stuck state detection
- Template-based activity descriptions

---

### 3. Contextual Help System (`contextual_help.py`)

Proactive suggestions based on current task state.

```python
from core.contextual_help import contextual_help

# Analyze an error
suggestion = contextual_help.analyze_error(
    "FileNotFoundError: [Errno 2] No such file: 'data.csv'"
)
# Returns suggestion with message and recovery options

# Detect stuck state
task_state = {
    "current_step": "downloading",
    "elapsed_seconds": 300,
    "seconds_since_last_update": 150
}
stuck_hint = contextual_help.detect_stuck_state(task_state)

# Get capability hints
capability_hint = contextual_help.get_capability_hint(
    ["file", "read", "parse"]
)
# "I can also search for files, watch directories for changes, or convert between formats."

# Get milestone-based guidance
milestone_hint = contextual_help.get_milestone_hint("files_read")
# "I've finished reading the files. Would you like me to summarize?"
```

**Help Triggers:**
- `USER_REQUEST` - Explicit help request
- `ERROR_DETECTED` - Recognized error patterns
- `STUCK_STATE` - No progress detected
- `REPEATED_FAILURE` - Same step failing multiple times
- `CAPABILITY_DISCOVERY` - Relevant feature suggestions
- `MILESTONE_REACHED` - Next-step guidance

**Error Patterns Recognized:**
- File not found / permission denied
- Network timeouts / rate limits
- Parse errors / memory pressure
- API errors / ambiguous requests

---

### 4. Comprehensive Observability (`observability.py`)

Centralized metrics, distributed tracing, and structured logging.

```python
from core.observability import observability

# Start task tracking
span = observability.start_task(
    task_id="task_123",
    task_type="file_analysis",
    metadata={"user": "alice", "priority": "high"}
)

# Record steps with timing
observability.record_step(
    task_id="task_123",
    step_name="read_file",
    duration=0.5,
    success=True
)

# Track token usage
observability.record_token_usage(
    task_id="task_123",
    tokens=1500,
    token_type="completion"
)

# Complete task
observability.complete_task(
    task_id="task_123",
    success=True,
    result_summary="Analyzed 10 files"
)

# Get dashboard data
dashboard = observability.get_dashboard_data()
```

**Metrics Collected:**
- Task success/failure rates
- Step duration histograms (mean, p95, p99)
- Token usage by type
- Active task count

**Distributed Tracing:**
- OpenTelemetry-compatible span structure
- Trace ID propagation across async boundaries
- Event annotations within spans
- Error attribution

**Structured Logging:**
```python
from core.observability import StructuredLogger

logger = StructuredLogger()
logger.set_correlation_id("task_123")
logger.info("Processing started", file_count=10, user="alice")
```

JSON output (when `LOG_FORMAT=json`):
```json
{
  "timestamp": 1699900000.0,
  "level": "INFO",
  "message": "Processing started",
  "correlation_id": "task_123",
  "file_count": 10,
  "user": "alice"
}
```

---

## Executor Pool Integration

The `ExecutorPool` has been updated to automatically integrate Phase 4 features:

```python
from core.executor_pool import pool

# Submit with Phase 4 features enabled by default
future = pool.submit(
    my_function,
    task_id="task_123",
    arg1, arg2,
    enable_streaming=True,      # Stream output
    track_progress=True,        # Track progress
    use_retry=True,             # Smart retry
    use_checkpoint=True         # Periodic checkpoints
)
```

**Automatic Integration:**
1. Creates streaming response on task start
2. Initializes progress reporter
3. Starts observability trace span
4. Emits events at each lifecycle stage
5. Records metrics on completion
6. Provides contextual help on failures

---

## Usage Examples

### Example 1: Real-time Task Monitoring

```python
from core.streaming_manager import streaming_manager
from core.progress_reporter import progress_registry
from core.observability import observability

def process_files(file_list):
    task_id = "process_files_001"
    
    # Initialize components
    stream = streaming_manager.create_stream(task_id)
    reporter = progress_registry.create_reporter(task_id, "Processing files")
    reporter.start()
    
    for i, file in enumerate(file_list):
        step = reporter.add_step("process_file", details={"file": file})
        
        stream.send_status("processing", {"file": file, "index": i})
        stream.send_text(f"Processing {file}...\n")
        
        try:
            result = heavy_processing(file)
            reporter.complete_step(step.step_id)
            stream.send_text(f"✓ Completed {file}\n")
        except Exception as e:
            reporter.complete_step(step.step_id, status="failed")
            stream.send_error(str(e))
            raise
    
    reporter.add_milestone("all_processed", "All files completed")
    stream.complete(f"Processed {len(file_list)} files")
    observability.complete_task(task_id, success=True)
```

### Example 2: Dashboard Integration

```python
# Get real-time metrics
metrics = observability.metrics.get_all_metrics()
print(f"Tasks completed: {metrics['counters'].get('tasks.completed', 0)}")

# Get histogram stats for latency
latency_stats = observability.metrics.get_histogram_stats("task.duration_seconds")
print(f"Average task duration: {latency_stats['mean']:.2f}s")
print(f"P95 latency: {latency_stats['p95']:.2f}s")

# Get active traces
active_traces = len(observability.tracer._active_spans)
print(f"Active traces: {active_traces}")

# Export for external dashboard
dashboard_data = observability.get_dashboard_data()
send_to_datadog(dashboard_data)
```

### Example 3: Error Recovery with Contextual Help

```python
from core.contextual_help import contextual_help

def handle_task_error(task_id, error):
    # Analyze the error
    suggestion = contextual_help.analyze_error(str(error))
    
    if suggestion:
        # Present options to user
        print(suggestion.message)
        for i, action in enumerate(suggestion.suggested_actions):
            print(f"  {i+1}. {action}")
        
        # Record for pattern detection
        contextual_help.record_failure(getattr(current_step, '__name__', 'unknown'))
    
    # Check if stuck
    task_state = get_current_task_state(task_id)
    stuck_hint = contextual_help.detect_stuck_state(task_state)
    
    if stuck_hint:
        print(stuck_hint.message)
        # Offer alternative approach
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_FORMAT` | `text` | Set to `json` for structured logging |
| `METRICS_EXPORT_INTERVAL` | `60` | Seconds between metric exports |
| `TRACE_SAMPLE_RATE` | `1.0` | Fraction of traces to keep (0.0-1.0) |

### Customization

```python
# Customize step templates for progress reports
from core.progress_reporter import ProgressReporter

reporter = ProgressReporter(task_id="custom_task")
reporter._step_templates["custom_operation"] = "Performing {operation} on {target}..."

# Add custom error patterns
from core.contextual_help import ContextualHelpEngine

help_engine = ContextualHelpEngine()
help_engine._hint_library["custom_error"] = {
    "triggers": ["CustomError", "specific message"],
    "message": "A custom error occurred.",
    "suggestions": ["Try this...", "Or that..."],
    "actions": ["custom_action"]
}

# Register metric export callback
from core.observability import observability

def export_metrics(metrics):
    send_to_prometheus(metrics)

observability.metrics.register_export_callback(export_metrics)
```

---

## Expected Impact

| Metric | Improvement | How Measured |
|--------|-------------|--------------|
| Perceived Latency | 40-60% reduction | Time to first byte vs total generation |
| User Confidence | High | Transparent progress updates |
| Support Tickets | 30% reduction | Self-service contextual help |
| Debugging Time | 50% reduction | Correlated traces and logs |
| Task Abandonment | 20% reduction | Clear ETAs and progress |

---

## Testing

```bash
# Run unit tests
python -m pytest tests/test_phase4_streaming.py -v
python -m pytest tests/test_phase4_progress.py -v
python -m pytest tests/test_phase4_observability.py -v

# Integration test
python -m pytest tests/test_integration_full.py::test_phase4_features -v
```

---

## Next Steps (Phase 5)

Ready to implement **Advanced Autonomy**:

1. **Self-reflection loops** - Agent critiques its own output
2. **Automated prompt optimization** - A/B testing prompt variations
3. **Dynamic skill synthesis** - Creating new tools on the fly
4. **Multi-agent negotiation protocols** - Collaborative task completion

---

## API Reference

### StreamingResponse Methods

| Method | Description |
|--------|-------------|
| `send_text(text, is_token=False)` | Send text content |
| `send_tool_call(name, args, call_id)` | Send tool invocation |
| `send_tool_result(name, result, call_id)` | Send tool result |
| `send_status(status, details)` | Send status update |
| `send_thought(thought, level)` | Send reasoning step |
| `send_error(message, type, recoverable)` | Send error |
| `complete(summary)` | End stream |
| `get_statistics()` | Get stream stats |

### ProgressReporter Methods

| Method | Description |
|--------|-------------|
| `start()` | Begin tracking |
| `add_step(name, id, details)` | Add new step |
| `complete_step(id, status, result)` | Complete step |
| `add_milestone(name, description)` | Record milestone |
| `get_progress_percentage()` | Get progress % |
| `get_eta()` | Get time estimate |
| `generate_summary()` | Get natural language summary |
| `detect_stuck_state()` | Check if stuck |

### ObservabilityEngine Methods

| Method | Description |
|--------|-------------|
| `start_task(id, type, metadata)` | Begin task trace |
| `complete_task(id, success, summary)` | End task trace |
| `record_step(id, name, duration, success)` | Record step |
| `record_token_usage(id, tokens, type)` | Track tokens |
| `get_task_status(id)` | Get task metrics |
| `get_dashboard_data()` | Get all metrics |

---

*Phase 4 Implementation Complete ✓*
