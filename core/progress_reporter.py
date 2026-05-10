"""
Progress Reporter for JARVIS Phase 4.
Generates natural language progress summaries from raw step data.
Calculates ETA based on rolling averages of step duration.
"""
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import statistics

logger = logging.getLogger(__name__)


@dataclass
class StepRecord:
    """Represents a single execution step."""
    step_id: str
    step_name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "pending"  # pending, running, completed, failed
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate step duration in seconds."""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def is_complete(self) -> bool:
        """Check if step is complete."""
        return self.status in ("completed", "failed")


@dataclass
class Milestone:
    """Represents a significant achievement in task execution."""
    name: str
    description: str
    achieved_at: float
    step_count: int


class ProgressReporter:
    """
    Generates human-readable progress reports and ETA predictions.
    Converts technical step logs into plain English narratives.
    """
    
    def __init__(self, task_id: str, task_description: str = ""):
        self.task_id = task_id
        self.task_description = task_description
        self._steps: List[StepRecord] = []
        self._milestones: List[Milestone] = []
        self._start_time: Optional[float] = None
        self._last_update_time: Optional[float] = None
        self._duration_history: deque = deque(maxlen=10)  # Rolling window of last 10 steps
        self._step_templates = {
            "read_file": "Reading {filename}...",
            "write_file": "Writing to {filename}...",
            "search": "Searching for '{query}'...",
            "analyze": "Analyzing {target}...",
            "execute": "Executing {command}...",
            "compile": "Compiling {target}...",
            "test": "Running tests for {module}...",
            "download": "Downloading {url}...",
            "upload": "Uploading {destination}...",
            "process": "Processing {item}...",
            "validate": "Validating {target}...",
            "transform": "Transforming {source}...",
            "generate": "Generating {output}...",
        }
        logger.info(f"ProgressReporter initialized for task {task_id}")
    
    def start(self):
        """Mark the task as started."""
        self._start_time = time.time()
        self._last_update_time = self._start_time
        logger.debug(f"Task {self.task_id} started")
    
    def add_step(self, step_name: str, step_id: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None) -> StepRecord:
        """
        Add a new step to the progress tracker.
        
        Args:
            step_name: Name/identifier of the step
            step_id: Unique ID (auto-generated if not provided)
            details: Additional context about the step
        
        Returns:
            The created StepRecord
        """
        step_id = step_id or f"step_{len(self._steps) + 1}"
        step = StepRecord(
            step_id=step_id,
            step_name=step_name,
            start_time=time.time(),
            status="running",
            details=details or {}
        )
        self._steps.append(step)
        logger.debug(f"Step {step_id} ({step_name}) started")
        return step
    
    def complete_step(self, step_id: str, status: str = "completed",
                      result: Optional[Any] = None) -> Optional[StepRecord]:
        """
        Mark a step as complete.
        
        Args:
            step_id: ID of the step to complete
            status: Final status (completed, failed)
            result: Optional result data
        
        Returns:
            The updated StepRecord or None if not found
        """
        step = self._find_step(step_id)
        if not step:
            logger.warning(f"Step {step_id} not found")
            return None
        
        step.end_time = time.time()
        step.status = status
        if result:
            step.details["result"] = result
        
        # Track duration for ETA calculation
        if step.duration:
            self._duration_history.append(step.duration)
        
        self._last_update_time = time.time()
        logger.debug(f"Step {step_id} completed with status {status}")
        return step
    
    def _find_step(self, step_id: str) -> Optional[StepRecord]:
        """Find a step by ID."""
        for step in self._steps:
            if step.step_id == step_id:
                return step
        return None
    
    def add_milestone(self, name: str, description: str):
        """
        Record a significant milestone.
        
        Args:
            name: Short name for the milestone
            description: Human-readable description
        """
        milestone = Milestone(
            name=name,
            description=description,
            achieved_at=time.time(),
            step_count=len(self._steps)
        )
        self._milestones.append(milestone)
        logger.info(f"Milestone achieved: {name}")
    
    def get_progress_percentage(self) -> float:
        """
        Estimate overall progress percentage.
        Note: This is an estimate since total steps may not be known upfront.
        """
        if not self._steps:
            return 0.0
        
        completed = sum(1 for s in self._steps if s.is_complete)
        # Assume at least 1 more step if last step is still running
        estimated_total = len(self._steps) if self._steps[-1].is_complete else len(self._steps) + 1
        
        return min(100.0, (completed / estimated_total) * 100)
    
    def get_eta(self) -> Optional[Tuple[float, str]]:
        """
        Calculate Estimated Time of Arrival (completion time).
        
        Returns:
            Tuple of (seconds_remaining, formatted_string) or None if insufficient data
        """
        if len(self._duration_history) < 2:
            return None
        
        avg_duration = statistics.mean(self._duration_history)
        remaining_steps = sum(1 for s in self._steps if not s.is_complete)
        
        # If no running steps, assume at least one more step
        if remaining_steps == 0:
            remaining_steps = 1
        
        seconds_remaining = avg_duration * remaining_steps
        
        # Format the ETA string
        if seconds_remaining < 60:
            eta_str = f"{int(seconds_remaining)} seconds"
        elif seconds_remaining < 3600:
            minutes = int(seconds_remaining / 60)
            eta_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = int(seconds_remaining / 3600)
            eta_str = f"{hours} hour{'s' if hours != 1 else ''}"
        
        return (seconds_remaining, eta_str)
    
    def generate_summary(self) -> str:
        """
        Generate a natural language progress summary.
        
        Returns:
            Human-readable progress report
        """
        if not self._steps:
            return "Task initialized, waiting to start..."
        
        # Count step statuses
        completed = sum(1 for s in self._steps if s.status == "completed")
        failed = sum(1 for s in self._steps if s.status == "failed")
        running = sum(1 for s in self._steps if s.status == "running")
        pending = sum(1 for s in self._steps if s.status == "pending")
        
        # Get current activity
        running_steps = [s for s in self._steps if s.status == "running"]
        current_activity = ""
        if running_steps:
            current = running_steps[-1]
            template = self._step_templates.get(current.step_name.split("_")[0])
            if template:
                try:
                    current_activity = template.format(**current.details)
                except KeyError:
                    current_activity = f"Performing {current.step_name}..."
            else:
                current_activity = f"Currently {current.step_name.replace('_', ' ')}..."
        
        # Build the narrative
        parts = []
        
        if self.task_description:
            parts.append(f"Working on: {self.task_description}")
        
        if completed > 0:
            parts.append(f"I've completed {completed} step{'s' if completed != 1 else ''}")
        
        if running > 0 and current_activity:
            parts.append(f"now {current_activity.lower()}")
        
        # Add milestone highlights
        if self._milestones:
            recent_milestones = self._milestones[-2:]  # Last 2 milestones
            milestone_text = ", ".join([m.name for m in recent_milestones])
            parts.append(f"Achieved: {milestone_text}")
        
        # Add ETA if available
        eta_result = self.get_eta()
        if eta_result:
            parts.append(f"Estimated time remaining: {eta_result[1]}")
        
        # Combine into coherent narrative
        if len(parts) >= 2:
            summary = f"{parts[0]}. "
            middle_parts = parts[1:-1] if len(parts) > 2 else []
            if middle_parts:
                summary += ", ".join(middle_parts) + ". "
            if len(parts) > 1:
                summary += f"{parts[-1]}."
        else:
            summary = parts[0] if parts else "Task in progress..."
        
        return summary
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """
        Get detailed status information for programmatic use.
        
        Returns:
            Dictionary with comprehensive status data
        """
        elapsed = time.time() - self._start_time if self._start_time else 0
        eta_result = self.get_eta()
        
        step_summaries = []
        for step in self._steps:
            step_summaries.append({
                "step_id": step.step_id,
                "step_name": step.step_name,
                "status": step.status,
                "duration": step.duration,
                "details": step.details
            })
        
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "progress_percentage": self.get_progress_percentage(),
            "elapsed_seconds": elapsed,
            "eta_seconds": eta_result[0] if eta_result else None,
            "eta_formatted": eta_result[1] if eta_result else None,
            "total_steps": len(self._steps),
            "completed_steps": sum(1 for s in self._steps if s.status == "completed"),
            "failed_steps": sum(1 for s in self._steps if s.status == "failed"),
            "running_steps": sum(1 for s in self._steps if s.status == "running"),
            "milestones": [{"name": m.name, "description": m.description} 
                          for m in self._milestones],
            "recent_steps": step_summaries[-5:],  # Last 5 steps
            "summary": self.generate_summary()
        }
    
    def detect_stuck_state(self, threshold_seconds: float = 120) -> bool:
        """
        Detect if the task appears to be stuck.
        
        Args:
            threshold_seconds: Time without progress to consider stuck
        
        Returns:
            True if task appears stuck
        """
        if not self._last_update_time:
            return False
        
        time_since_update = time.time() - self._last_update_time
        return time_since_update > threshold_seconds
    
    def get_stuck_suggestion(self) -> Optional[str]:
        """
        Get a suggestion for recovering from a stuck state.
        
        Returns:
            Suggestion string or None if not stuck
        """
        if not self.detect_stuck_state():
            return None
        
        running_steps = [s for s in self._steps if s.status == "running"]
        if running_steps:
            current = running_steps[-1]
            return f"The task seems stuck on '{current.step_name}'. Would you like me to retry with different parameters or skip this step?"
        
        return "The task appears to be stuck. Would you like me to provide a status update or try an alternative approach?"


# Global progress reporter registry
class ProgressRegistry:
    """Centralized registry for all active progress reporters."""
    
    def __init__(self):
        self._reporters: Dict[str, ProgressReporter] = {}
        self._lock = threading.Lock() if 'threading' in globals() else None
    
    def create_reporter(self, task_id: str, 
                       task_description: str = "") -> ProgressReporter:
        """Create a new progress reporter for a task."""
        reporter = ProgressReporter(task_id, task_description)
        if self._lock:
            with self._lock:
                self._reporters[task_id] = reporter
        else:
            self._reporters[task_id] = reporter
        return reporter
    
    def get_reporter(self, task_id: str) -> Optional[ProgressReporter]:
        """Get an existing progress reporter."""
        if self._lock:
            with self._lock:
                return self._reporters.get(task_id)
        return self._reporters.get(task_id)
    
    def remove_reporter(self, task_id: str) -> bool:
        """Remove a progress reporter."""
        if self._lock:
            with self._lock:
                if task_id in self._reporters:
                    del self._reporters[task_id]
                    return True
        elif task_id in self._reporters:
            del self._reporters[task_id]
            return True
        return False
    
    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all active tasks."""
        if self._lock:
            with self._lock:
                return {tid: r.get_detailed_status() 
                       for tid, r in self._reporters.items()}
        return {tid: r.get_detailed_status() 
               for tid, r in self._reporters.items()}


import threading

# Global instance
progress_registry = ProgressRegistry()
