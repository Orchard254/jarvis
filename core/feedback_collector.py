"""
Feedback Collector Module
Collects and processes user feedback for continuous improvement.
"""
import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    RATING = "rating"  # 1-5 scale
    TEXT = "text"
    CORRECTION = "correction"


@dataclass
class Feedback:
    """Represents user feedback on an agent action."""
    feedback_id: str
    task_id: str
    step_id: Optional[str]
    feedback_type: FeedbackType
    value: Any  # rating number, text, etc.
    timestamp: float
    context: Dict[str, Any]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['feedback_type'] = self.feedback_type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Feedback':
        data['feedback_type'] = FeedbackType(data['feedback_type'])
        return cls(**data)


class FeedbackCollector:
    """
    Collects and aggregates user feedback for model improvement.
    Supports multiple feedback types and storage backends.
    """

    def __init__(self, storage_path: str = "./feedback"):
        self.storage_path = storage_path
        self._pending_feedback: List[Feedback] = []
        
        os.makedirs(storage_path, exist_ok=True)
        self._feedback_file = os.path.join(storage_path, "feedback_log.jsonl")

    async def submit_thumbs_up(
        self,
        task_id: str,
        step_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Submit positive feedback (thumbs up)."""
        return await self.submit_feedback(
            task_id=task_id,
            step_id=step_id,
            feedback_type=FeedbackType.THUMBS_UP,
            value=True,
            context=context
        )

    async def submit_thumbs_down(
        self,
        task_id: str,
        step_id: Optional[str] = None,
        reason: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Submit negative feedback (thumbs down)."""
        return await self.submit_feedback(
            task_id=task_id,
            step_id=step_id,
            feedback_type=FeedbackType.THUMBS_DOWN,
            value={"reason": reason} if reason else True,
            context=context
        )

    async def submit_rating(
        self,
        task_id: str,
        rating: int,  # 1-5
        step_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Submit a 1-5 star rating."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")
        
        return await self.submit_feedback(
            task_id=task_id,
            step_id=step_id,
            feedback_type=FeedbackType.RATING,
            value=rating,
            context=context
        )

    async def submit_text_feedback(
        self,
        task_id: str,
        text: str,
        step_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Submit free-form text feedback."""
        return await self.submit_feedback(
            task_id=task_id,
            step_id=step_id,
            feedback_type=FeedbackType.TEXT,
            value=text,
            context=context
        )

    async def submit_correction(
        self,
        task_id: str,
        expected_output: str,
        actual_output: str,
        step_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Submit a correction showing what the output should have been."""
        return await self.submit_feedback(
            task_id=task_id,
            step_id=step_id,
            feedback_type=FeedbackType.CORRECTION,
            value={
                "expected": expected_output,
                "actual": actual_output
            },
            context=context
        )

    async def submit_feedback(
        self,
        task_id: str,
        feedback_type: FeedbackType,
        value: Any,
        step_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Submit general feedback.
        
        Args:
            task_id: ID of the task being reviewed
            feedback_type: Type of feedback
            value: The feedback value (depends on type)
            step_id: Optional specific step ID
            context: Additional context about the state
            
        Returns:
            feedback_id: Unique identifier for this feedback
        """
        import uuid
        
        feedback = Feedback(
            feedback_id=str(uuid.uuid4()),
            task_id=task_id,
            step_id=step_id,
            feedback_type=feedback_type,
            value=value,
            timestamp=time.time(),
            context=context or {},
            metadata={
                "created_at": datetime.now().isoformat(),
                "source": "user"
            }
        )
        
        self._pending_feedback.append(feedback)
        
        # Persist immediately
        await self._persist_feedback(feedback)
        
        logger.info(f"Collected {feedback_type.value} feedback for task {task_id[:8]}")
        return feedback.feedback_id

    async def _persist_feedback(self, feedback: Feedback) -> None:
        """Persist feedback to disk."""
        try:
            with open(self._feedback_file, 'a') as f:
                f.write(json.dumps(feedback.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to persist feedback: {e}", exc_info=True)

    async def get_feedback_for_task(self, task_id: str) -> List[Feedback]:
        """Get all feedback for a specific task."""
        feedback_list = []
        
        try:
            if not os.path.exists(self._feedback_file):
                return feedback_list
            
            with open(self._feedback_file, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if data.get('task_id') == task_id:
                            feedback_list.append(Feedback.from_dict(data))
                    except json.JSONDecodeError:
                        continue
            
            return sorted(feedback_list, key=lambda f: f.timestamp)
            
        except Exception as e:
            logger.error(f"Error reading feedback for task {task_id}: {e}", exc_info=True)
            return feedback_list

    async def get_all_feedback(
        self,
        limit: int = 100,
        feedback_type: Optional[FeedbackType] = None
    ) -> List[Feedback]:
        """Get recent feedback, optionally filtered by type."""
        feedback_list = []
        
        try:
            if not os.path.exists(self._feedback_file):
                return feedback_list
            
            with open(self._feedback_file, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        fb = Feedback.from_dict(data)
                        
                        if feedback_type and fb.feedback_type != feedback_type:
                            continue
                        
                        feedback_list.append(fb)
                    except json.JSONDecodeError:
                        continue
            
            # Sort by timestamp descending and limit
            feedback_list.sort(key=lambda f: f.timestamp, reverse=True)
            return feedback_list[:limit]
            
        except Exception as e:
            logger.error(f"Error reading all feedback: {e}", exc_info=True)
            return []

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics about collected feedback."""
        stats = {
            "total_feedback": 0,
            "thumbs_up": 0,
            "thumbs_down": 0,
            "ratings": [],
            "corrections": 0,
            "average_rating": 0.0,
            "feedback_by_day": {}
        }
        
        try:
            if not os.path.exists(self._feedback_file):
                return stats
            
            with open(self._feedback_file, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        stats["total_feedback"] += 1
                        
                        fb_type = data.get('feedback_type')
                        if fb_type == "thumbs_up":
                            stats["thumbs_up"] += 1
                        elif fb_type == "thumbs_down":
                            stats["thumbs_down"] += 1
                        elif fb_type == "rating":
                            stats["ratings"].append(data.get('value', 0))
                        elif fb_type == "correction":
                            stats["corrections"] += 1
                        
                        # Group by day
                        created_at = data.get('metadata', {}).get('created_at', '')
                        if created_at:
                            day = created_at.split('T')[0]
                            stats["feedback_by_day"][day] = stats["feedback_by_day"].get(day, 0) + 1
                            
                    except json.JSONDecodeError:
                        continue
            
            # Calculate average rating
            if stats["ratings"]:
                stats["average_rating"] = sum(stats["ratings"]) / len(stats["ratings"])
                del stats["ratings"]  # Remove raw ratings, keep only aggregate
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating feedback stats: {e}", exc_info=True)
            return stats

    async def export_feedback(self, output_path: str) -> int:
        """Export all feedback to a JSON file for analysis."""
        try:
            feedback_list = await self.get_all_feedback(limit=10000)
            
            with open(output_path, 'w') as f:
                json.dump([fb.to_dict() for fb in feedback_list], f, indent=2)
            
            logger.info(f"Exported {len(feedback_list)} feedback entries to {output_path}")
            return len(feedback_list)
            
        except Exception as e:
            logger.error(f"Failed to export feedback: {e}", exc_info=True)
            return 0


class FeedbackPrompt:
    """Utility for generating feedback prompts in CLI."""
    
    @staticmethod
    def print_feedback_request(task_id: str, result_preview: str) -> None:
        """Print a feedback request prompt to the console."""
        border = "─" * 56
        print(f"\n┌{border}┐")
        print(f"│  💬  How did I do?{' ' * 37}│")
        print(f"├{border}┤")
        print(f"│  Task: {task_id[:8]}{'':>43}│")
        
        # Preview result
        preview_lines = result_preview[:200].split('\n')
        for i, line in enumerate(preview_lines[:3]):
            truncated = line[:48] + '...' if len(line) > 50 else line
            print(f"│  {truncated:<49}│")
        
        print(f"├{border}┤")
        print(f"│  Rate this response:                           │")
        print(f"│    [5] ⭐⭐⭐⭐⭐  Excellent                      │")
        print(f"│    [4] ⭐⭐⭐⭐   Good                           │")
        print(f"│    [3] ⭐⭐⭐    Okay                           │")
        print(f"│    [2] ⭐⭐     Poor                           │")
        print(f"│    [1] ⭐      Terrible                       │")
        print(f"│                                                │")
        print(f"│  Or type:                                      │")
        print(f"│    👍 / thumbsup  - Quick positive feedback    │")
        print(f"│    👎 / thumbsdown - Quick negative feedback   │")
        print(f"│    c / correct    - Provide a correction       │")
        print(f"│    s / skip       - Skip feedback              │")
        print(f"└{border}┘")
