"""
Progress Reporter for JARVIS.
Generates natural language progress summaries and ETA calculations.
"""
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque
import statistics


@dataclass
class StepRecord:
    """Records a single step in task execution."""
    step_name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"  # running, completed, failed
    details: Optional[str] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Get step duration in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def is_complete(self) -> bool:
        """Check if step is complete."""
        return self.status in ("completed", "failed")


class ProgressReporter:
    """
    Generates human-readable progress reports from raw step data.
    
    Features:
    - Natural language summarization of technical steps
    - ETA calculation based on rolling averages
    - Milestone detection and highlighting
    - Velocity tracking
    """
    
    def __init__(self, task_id: Optional[str] = None):
        self.task_id = task_id
        self._steps: List[StepRecord] = []
        self._milestones: List[Dict[str, Any]] = []
        self._start_time: Optional[float] = None
        self._total_steps_estimated: int = 0
        self._rolling_window_size: int = 5
    
    def start(self, estimated_steps: int = 0):
        """Mark task start."""
        self._start_time = time.time()
        self._total_steps_estimated = estimated_steps
        self._steps.clear()
        self._milestones.clear()
    
    def record_step_start(self, step_name: str, details: Optional[str] = None):
        """Record the start of a new step."""
        step = StepRecord(
            step_name=step_name,
            start_time=time.time(),
            details=details
        )
        self._steps.append(step)
        return step
    
    def record_step_complete(self, step_name: str, 
                             status: str = "completed",
                             details: Optional[str] = None):
        """Mark a step as complete."""
        # Find the running step with this name
        for step in reversed(self._steps):
            if step.step_name == step_name and not step.is_complete:
                step.end_time = time.time()
                step.status = status
                if details:
                    step.details = details
                break
    
    def add_milestone(self, name: str, description: str, 
                      progress_percent: float):
        """Add a milestone marker."""
        self._milestones.append({
            "name": name,
            "description": description,
            "progress_percent": progress_percent,
            "reached_at": time.time()
        })
    
    def _get_recent_durations(self) -> List[float]:
        """Get durations of recently completed steps."""
        completed = [
            step for step in self._steps 
            if step.is_complete and step.duration is not None
        ]
        # Use rolling window
        recent = completed[-self._rolling_window_size:]
        return [step.duration for step in recent]
    
    def calculate_eta(self) -> Optional[Dict[str, Any]]:
        """
        Calculate Estimated Time of Arrival based on recent step durations.
        
        Returns:
            Dictionary with eta_seconds, eta_formatted, confidence, or None
        """
        if not self._start_time:
            return None
        
        completed_steps = [s for s in self._steps if s.is_complete]
        total_completed = len(completed_steps)
        
        if total_completed == 0:
            return None
        
        # Get average duration from recent steps
        recent_durations = self._get_recent_durations()
        if not recent_durations:
            return None
        
        avg_duration = statistics.mean(recent_durations)
        
        # Estimate remaining steps
        if self._total_steps_estimated > 0:
            remaining_steps = max(0, self._total_steps_estimated - total_completed)
        else:
            # Heuristic: assume 3x completed steps if unknown
            remaining_steps = max(0, total_completed * 2)
        
        eta_seconds = remaining_steps * avg_duration
        
        # Calculate confidence based on sample size
        if len(recent_durations) >= self._rolling_window_size:
            confidence = "high"
        elif len(recent_durations) >= 2:
            confidence = "medium"
        else:
            confidence = "low"
        
        return {
            "eta_seconds": eta_seconds,
            "eta_formatted": self._format_duration(eta_seconds),
            "remaining_steps": remaining_steps,
            "confidence": confidence,
            "avg_step_duration": avg_duration
        }
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable form."""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} hours"
    
    def generate_summary(self) -> str:
        """
        Generate a natural language progress summary.
        
        Examples:
        - "I've finished reading the files, now analyzing..."
        - "Completed 3 of 10 steps. Currently installing dependencies..."
        - "Almost done! Running final tests (90% complete)"
        """
        if not self._steps:
            return "Starting task..."
        
        completed = [s for s in self._steps if s.is_complete]
        running = [s for s in self._steps if not s.is_complete]
        total = len(self._steps)
        
        # Build summary parts
        parts = []
        
        # Progress indicator
        if self._total_steps_estimated > 0:
            percent = (len(completed) / self._total_steps_estimated) * 100
            parts.append(f"{len(completed)} of {self._total_steps_estimated} steps ({percent:.0f}% complete)")
        else:
            parts.append(f"{len(completed)} steps completed")
        
        # Current activity
        if running:
            current = running[-1]
            action_word = self._get_action_word(current.step_name)
            parts.append(f"Currently {action_word}...")
        elif completed:
            last = completed[-1]
            parts.append(f"Just finished {last.step_name}")
        
        # Add ETA if available
        eta_info = self.calculate_eta()
        if eta_info and eta_info["confidence"] != "low":
            parts.append(f"ETA: {eta_info['eta_formatted']}")
        
        # Check for milestones
        elapsed = time.time() - self._start_time if self._start_time else 0
        for milestone in self._milestones:
            if (elapsed / max(1, eta_info["eta_seconds"] + elapsed if eta_info else 1)) * 100 >= milestone["progress_percent"]:
                if not milestone.get("reported"):
                    milestone["reported"] = True
                    parts.append(f"✓ Milestone: {milestone['name']}")
        
        return ". ".join(parts) + "."
    
    def _get_action_word(self, step_name: str) -> str:
        """Convert step name to present participle verb form."""
        # Simple mapping for common steps
        mappings = {
            "reading": "reading",
            "analyze": "analyzing",
            "install": "installing",
            "build": "building",
            "test": "testing",
            "compile": "compiling",
            "download": "downloading",
            "upload": "uploading",
            "process": "processing",
            "generate": "generating",
            "validate": "validating",
            "execute": "executing",
            "run": "running",
            "wait": "waiting",
            "search": "searching",
            "create": "creating",
            "update": "updating",
            "delete": "deleting",
        }
        
        step_lower = step_name.lower()
        for key, value in mappings.items():
            if key in step_lower:
                return value
        
        # Default: add "ing" if doesn't already end with it
        if step_name.endswith("e"):
            return step_name[:-1] + "ing"
        elif step_name.endswith("ing"):
            return step_name
        else:
            return step_name + "ing"
    
    def get_velocity(self) -> Dict[str, Any]:
        """Calculate task velocity metrics."""
        recent_durations = self._get_recent_durations()
        
        if not recent_durations:
            return {"steps_per_minute": 0, "trend": "unknown"}
        
        avg_duration = statistics.mean(recent_durations)
        steps_per_minute = 60 / avg_duration if avg_duration > 0 else 0
        
        # Determine trend
        if len(recent_durations) >= 2:
            first_half = statistics.mean(recent_durations[:len(recent_durations)//2])
            second_half = statistics.mean(recent_durations[len(recent_durations)//2:])
            
            if second_half < first_half * 0.9:
                trend = "accelerating"
            elif second_half > first_half * 1.1:
                trend = "decelerating"
            else:
                trend = "stable"
        else:
            trend = "unknown"
        
        return {
            "steps_per_minute": round(steps_per_minute, 2),
            "avg_step_duration_seconds": round(avg_duration, 2),
            "trend": trend,
            "sample_size": len(recent_durations)
        }
    
    def detect_stuck_state(self, threshold_seconds: float = 120) -> bool:
        """
        Detect if the task appears to be stuck.
        
        A task is considered stuck if:
        - No step has completed in threshold_seconds
        - AND there are running steps
        """
        if not self._steps:
            return False
        
        completed = [s for s in self._steps if s.is_complete]
        if not completed:
            return False
        
        last_completion_time = max(s.end_time for s in completed)
        time_since_last_complete = time.time() - last_completion_time
        
        return time_since_last_complete > threshold_seconds
    
    def get_progress_data(self) -> Dict[str, Any]:
        """Get comprehensive progress data as dictionary."""
        completed = [s for s in self._steps if s.is_complete]
        running = [s for s in self._steps if not s.is_complete]
        
        eta_info = self.calculate_eta()
        
        return {
            "task_id": self.task_id,
            "total_steps": len(self._steps),
            "completed_steps": len(completed),
            "running_steps": len(running),
            "estimated_total": self._total_steps_estimated,
            "progress_percent": (len(completed) / max(1, self._total_steps_estimated)) * 100 if self._total_steps_estimated > 0 else 0,
            "current_step": running[-1].step_name if running else None,
            "summary": self.generate_summary(),
            "eta": eta_info,
            "velocity": self.get_velocity(),
            "is_stuck": self.detect_stuck_state(),
            "milestones": self._milestones,
            "elapsed_seconds": time.time() - self._start_time if self._start_time else 0
        }


class ProgressReporterManager:
    """
    Manages progress reporters for multiple concurrent tasks.
    """
    
    def __init__(self):
        self._reporters: Dict[str, ProgressReporter] = {}
    
    def create_reporter(self, task_id: str, 
                        estimated_steps: int = 0) -> ProgressReporter:
        """Create a progress reporter for a task."""
        reporter = ProgressReporter(task_id=task_id)
        reporter.start(estimated_steps=estimated_steps)
        self._reporters[task_id] = reporter
        return reporter
    
    def get_reporter(self, task_id: str) -> Optional[ProgressReporter]:
        """Get existing reporter for a task."""
        return self._reporters.get(task_id)
    
    def remove_reporter(self, task_id: str):
        """Remove reporter for completed/cancelled task."""
        if task_id in self._reporters:
            del self._reporters[task_id]
    
    def list_active_tasks(self) -> List[str]:
        """List all tasks with active reporters."""
        return list(self._reporters.keys())
    
    def get_all_summaries(self) -> Dict[str, str]:
        """Get progress summaries for all active tasks."""
        return {
            task_id: reporter.generate_summary()
            for task_id, reporter in self._reporters.items()
        }


# Global instance
progress_manager = ProgressReporterManager()
