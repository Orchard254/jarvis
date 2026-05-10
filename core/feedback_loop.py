"""
Phase 3: User Feedback Loop & Implicit Signal Processing

Captures explicit ratings and implicit signals (retries, edits, abandonment)
to improve agent performance over time.
"""
import time
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum
import os

logger = logging.getLogger(__name__)

class FeedbackType(Enum):
    EXPLICIT_RATING = "explicit_rating"
    IMPLICIT_RETRY = "implicit_retry"
    IMPLICIT_EDIT = "implicit_edit"
    IMPLICIT_ABANDON = "implicit_abandon"
    IMPLICIT_SUCCESS = "implicit_success"

@dataclass
class FeedbackEvent:
    task_id: str
    skill_name: str
    feedback_type: FeedbackType
    value: float  # -1.0 to 1.0 score
    timestamp: float = field(default_factory=time.time)
    user_comment: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d['feedback_type'] = self.feedback_type.value
        return d

class FeedbackStore:
    """In-memory store with file persistence for feedback events."""
    
    def __init__(self, storage_path: str = "output/feedback_log.jsonl"):
        self.storage_path = storage_path
        self.events: List[FeedbackEvent] = []
        self._ensure_storage_dir()
        self._load_existing()
        
    def _ensure_storage_dir(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
    def _load_existing(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            data['feedback_type'] = FeedbackType(data['feedback_type'])
                            self.events.append(FeedbackEvent(**data))
                logger.info(f"Loaded {len(self.events)} existing feedback events")
            except Exception as e:
                logger.error(f"Failed to load feedback log: {e}")

    def add_event(self, event: FeedbackEvent):
        self.events.append(event)
        self._persist_event(event)
        logger.debug(f"Recorded feedback: {event.feedback_type.value} for {event.skill_name} ({event.value})")
        
    def _persist_event(self, event: FeedbackEvent):
        try:
            with open(self.storage_path, 'a') as f:
                f.write(json.dumps(event.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to persist feedback event: {e}")

    def get_feedback_for_skill(self, skill_name: str, limit: int = 100) -> List[FeedbackEvent]:
        return [
            e for e in self.events 
            if e.skill_name == skill_name
        ][-limit:]

    def get_aggregate_score(self, skill_name: str) -> float:
        """Calculate weighted average score for a skill."""
        events = self.get_feedback_for_skill(skill_name)
        if not events:
            return 0.0
        
        # Weight recent events higher
        now = time.time()
        total_weight = 0
        weighted_sum = 0
        
        for event in events:
            age_hours = (now - event.timestamp) / 3600
            weight = 1.0 / (1.0 + age_hours)  # Decay over time
            weighted_sum += event.value * weight
            total_weight += weight
            
        return weighted_sum / total_weight if total_weight > 0 else 0.0

class FeedbackCollector:
    """Main interface for collecting and processing feedback."""
    
    def __init__(self):
        self.store = FeedbackStore()
        self.pending_tasks: Dict[str, Dict[str, Any]] = {}
        
    def start_task(self, task_id: str, skill_name: str, context: Dict[str, Any]):
        """Track a task start for implicit signal detection."""
        self.pending_tasks[task_id] = {
            'skill_name': skill_name,
            'start_time': time.time(),
            'context': context,
            'attempts': 1,
            'edited': False
        }
        
    def record_explicit_rating(self, task_id: str, rating: int, comment: Optional[str] = None):
        """Record a 1-5 star rating from the user."""
        if task_id not in self.pending_tasks:
            logger.warning(f"Task {task_id} not found for explicit rating")
            return
            
        task_info = self.pending_tasks[task_id]
        # Normalize 1-5 to -1.0 to 1.0
        normalized_value = (rating - 3) / 2.0
        
        event = FeedbackEvent(
            task_id=task_id,
            skill_name=task_info['skill_name'],
            feedback_type=FeedbackType.EXPLICIT_RATING,
            value=normalized_value,
            user_comment=comment,
            context=task_info['context']
        )
        self.store.add_event(event)
        del self.pending_tasks[task_id]
        
    def record_retry(self, task_id: str):
        """Implicit negative signal: user had to retry the action."""
        if task_id not in self.pending_tasks:
            return
            
        task_info = self.pending_tasks[task_id]
        task_info['attempts'] += 1
        
        # Stronger penalty for multiple retries
        penalty = -0.5 * task_info['attempts']
        penalty = max(penalty, -1.0)  # Cap at -1.0
        
        event = FeedbackEvent(
            task_id=task_id,
            skill_name=task_info['skill_name'],
            feedback_type=FeedbackType.IMPLICIT_RETRY,
            value=penalty,
            context={**task_info['context'], 'attempt_number': task_info['attempts']}
        )
        self.store.add_event(event)
        
    def record_edit(self, task_id: str):
        """Implicit negative signal: user had to edit the result."""
        if task_id not in self.pending_tasks:
            return
            
        task_info = self.pending_tasks[task_id]
        if task_info['edited']:
            return  # Only count once
            
        task_info['edited'] = True
        
        event = FeedbackEvent(
            task_id=task_id,
            skill_name=task_info['skill_name'],
            feedback_type=FeedbackType.IMPLICIT_EDIT,
            value=-0.7,  # Significant negative signal
            context=task_info['context']
        )
        self.store.add_event(event)
        
    def record_abandon(self, task_id: str):
        """Implicit negative signal: user gave up on the task."""
        if task_id not in self.pending_tasks:
            return
            
        task_info = self.pending_tasks[task_id]
        
        event = FeedbackEvent(
            task_id=task_id,
            skill_name=task_info['skill_name'],
            feedback_type=FeedbackType.IMPLICIT_ABANDON,
            value=-1.0,  # Maximum negative signal
            context=task_info['context']
        )
        self.store.add_event(event)
        del self.pending_tasks[task_id]
        
    def record_success(self, task_id: str):
        """Implicit positive signal: task completed without issues."""
        if task_id not in self.pending_tasks:
            return
            
        task_info = self.pending_tasks[task_id]
        
        # Bonus for speed?
        duration = time.time() - task_info['start_time']
        bonus = 0.1 if duration < 2.0 else 0.0
        
        event = FeedbackEvent(
            task_id=task_id,
            skill_name=task_info['skill_name'],
            feedback_type=FeedbackType.IMPLICIT_SUCCESS,
            value=0.5 + bonus,
            context={**task_info['context'], 'duration': duration}
        )
        self.store.add_event(event)
        del self.pending_tasks[task_id]

# Global instance
feedback_collector = FeedbackCollector()

def get_collector() -> FeedbackCollector:
    return feedback_collector
