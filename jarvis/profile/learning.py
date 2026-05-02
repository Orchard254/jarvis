"""
JARVIS Learning System - Learns user preferences and behavior patterns.

Learns from:
- Explicit feedback (thumbs up/down)
- Implicit signals (tool usage patterns, corrections)
- Time-based patterns (routines, schedules)
- Context associations
"""

import json
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import threading


@dataclass
class FeedbackRecord:
    """User feedback on an action."""
    timestamp: datetime
    action_type: str  # 'tool_execution', 'suggestion', 'routine'
    action_id: str
    positive: bool
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'action_type': self.action_type,
            'action_id': self.action_id,
            'positive': self.positive,
            'context': self.context
        }


@dataclass
class LearnedPattern:
    """A learned behavior pattern."""
    pattern_id: str
    pattern_type: str  # 'preference', 'routine', 'association'
    description: str
    confidence: float  # 0.0 to 1.0
    occurrences: int = 1
    last_seen: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    action: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'pattern_id': self.pattern_id,
            'pattern_type': self.pattern_type,
            'description': self.description,
            'confidence': self.confidence,
            'occurrences': self.occurrences,
            'last_seen': self.last_seen.isoformat(),
            'context': self.context,
            'action': self.action
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LearnedPattern':
        last_seen = datetime.now()
        if data.get('last_seen'):
            last_seen = datetime.fromisoformat(data['last_seen'])
        
        return cls(
            pattern_id=data['pattern_id'],
            pattern_type=data['pattern_type'],
            description=data['description'],
            confidence=data['confidence'],
            occurrences=data.get('occurrences', 1),
            last_seen=last_seen,
            context=data.get('context', {}),
            action=data.get('action', {})
        )


class LearningEngine:
    """
    User preference and behavior learning engine.
    
    Features:
    - Feedback collection and analysis
    - Pattern detection
    - Preference inference
    - Confidence-based learning
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path(__file__).parent.parent / 'data' / 'learning.json'
        self._feedback_history: List[FeedbackRecord] = []
        self._patterns: Dict[str, LearnedPattern] = {}
        self._tool_preferences: Dict[str, float] = defaultdict(lambda: 0.5)  # tool -> preference score
        self._time_patterns: Dict[str, List[int]] = defaultdict(list)  # hour -> action counts
        self._lock = threading.Lock()
        
        self._load()
    
    def _load(self):
        """Load learning data from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    
                    # Load patterns
                    for pid, pdata in data.get('patterns', {}).items():
                        self._patterns[pid] = LearnedPattern.from_dict(pdata)
                    
                    # Load tool preferences
                    tool_prefs = data.get('tool_preferences', {})
                    for tool, score in tool_prefs.items():
                        self._tool_preferences[tool] = score
                    
                    # Load time patterns
                    time_pats = data.get('time_patterns', {})
                    for hour, counts in time_pats.items():
                        self._time_patterns[int(hour)] = counts
                    
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load learning data: {e}")
    
    def _save(self):
        """Save learning data to storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'patterns': {pid: p.to_dict() for pid, p in self._patterns.items()},
                'tool_preferences': dict(self._tool_preferences),
                'time_patterns': {str(h): c for h, c in self._time_patterns.items()}
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save learning data: {e}")
    
    def record_feedback(
        self,
        action_type: str,
        action_id: str,
        positive: bool,
        context: Optional[Dict[str, Any]] = None
    ):
        """Record user feedback on an action."""
        with self._lock:
            record = FeedbackRecord(
                timestamp=datetime.now(),
                action_type=action_type,
                action_id=action_id,
                positive=positive,
                context=context or {}
            )
            self._feedback_history.append(record)
            
            # Update relevant patterns
            self._update_patterns_from_feedback(record)
            
            # Trim history if too long
            if len(self._feedback_history) > 1000:
                self._feedback_history = self._feedback_history[-500:]
            
            # Periodic save
            if len(self._feedback_history) % 10 == 0:
                self._save()
    
    def _update_patterns_from_feedback(self, record: FeedbackRecord):
        """Update patterns based on feedback."""
        # Update tool preference if applicable
        if record.action_type == 'tool_execution':
            tool_name = record.action_id
            current_score = self._tool_preferences[tool_name]
            
            # Adjust score based on feedback
            delta = 0.1 if record.positive else -0.1
            new_score = max(0.0, min(1.0, current_score + delta))
            self._tool_preferences[tool_name] = new_score
            
            # Create/update pattern if confidence is high enough
            if new_score >= 0.7 or new_score <= 0.3:
                pattern_id = f"pref_{tool_name}"
                if pattern_id in self._patterns:
                    pattern = self._patterns[pattern_id]
                    pattern.confidence = abs(new_score - 0.5) * 2
                    pattern.occurrences += 1
                    pattern.last_seen = datetime.now()
                else:
                    self._patterns[pattern_id] = LearnedPattern(
                        pattern_id=pattern_id,
                        pattern_type='preference',
                        description=f"User {'prefers' if new_score >= 0.7 else 'avoids'} {tool_name}",
                        confidence=abs(new_score - 0.5) * 2,
                        context={'tool': tool_name, 'score': new_score},
                        action={'tool_name': tool_name}
                    )
    
    def record_action(self, hour: int, action_type: str, action_id: str):
        """Record an action for time-based pattern learning."""
        with self._lock:
            self._time_patterns[hour].append(hash(action_type + action_id) % 1000)
            
            # Trim old data
            if len(self._time_patterns[hour]) > 100:
                self._time_patterns[hour] = self._time_patterns[hour][-50:]
            
            # Detect patterns periodically
            if len(self._time_patterns[hour]) % 10 == 0:
                self._detect_time_patterns(hour)
    
    def _detect_time_patterns(self, hour: int):
        """Detect time-based patterns for a given hour."""
        actions = self._time_patterns[hour]
        if len(actions) < 5:
            return
        
        # Find most common actions
        action_counts = defaultdict(int)
        for a in actions:
            action_counts[a] += 1
        
        # Create pattern for frequent actions
        for action_hash, count in action_counts.items():
            if count >= len(actions) * 0.3:  # 30% frequency threshold
                pattern_id = f"time_{hour}_{action_hash}"
                if pattern_id not in self._patterns:
                    self._patterns[pattern_id] = LearnedPattern(
                        pattern_id=pattern_id,
                        pattern_type='routine',
                        description=f"Common action at hour {hour}",
                        confidence=count / len(actions),
                        occurrences=count,
                        context={'hour': hour, 'action_hash': action_hash}
                    )
    
    def get_tool_preference(self, tool_name: str) -> float:
        """Get learned preference score for a tool (0.0 to 1.0)."""
        return self._tool_preferences.get(tool_name, 0.5)
    
    def is_preferred_tool(self, tool_name: str, threshold: float = 0.6) -> bool:
        """Check if a tool is preferred by the user."""
        return self._tool_preferences.get(tool_name, 0.5) >= threshold
    
    def get_suggested_actions_for_hour(self, hour: int) -> List[Dict[str, Any]]:
        """Get suggested actions for a specific hour based on past patterns."""
        suggestions = []
        
        for pattern in self._patterns.values():
            if pattern.pattern_type == 'routine':
                pattern_hour = pattern.context.get('hour')
                if pattern_hour == hour and pattern.confidence >= 0.5:
                    suggestions.append({
                        'pattern_id': pattern.pattern_id,
                        'description': pattern.description,
                        'confidence': pattern.confidence,
                        'action': pattern.action
                    })
        
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)
        return suggestions[:5]  # Top 5 suggestions
    
    def get_learned_patterns(
        self, 
        pattern_type: Optional[str] = None,
        min_confidence: float = 0.5
    ) -> List[LearnedPattern]:
        """Get learned patterns, optionally filtered by type and confidence."""
        patterns = list(self._patterns.values())
        
        if pattern_type:
            patterns = [p for p in patterns if p.pattern_type == pattern_type]
        
        patterns = [p for p in patterns if p.confidence >= min_confidence]
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        
        return patterns
    
    def reinforce_pattern(self, pattern_id: str, positive: bool):
        """Reinforce or weaken a learned pattern."""
        with self._lock:
            if pattern_id not in self._patterns:
                return
            
            pattern = self._patterns[pattern_id]
            pattern.occurrences += 1
            pattern.last_seen = datetime.now()
            
            # Adjust confidence
            delta = 0.05 if positive else -0.1
            pattern.confidence = max(0.0, min(1.0, pattern.confidence + delta))
            
            # Remove low-confidence patterns
            if pattern.confidence < 0.2:
                del self._patterns[pattern_id]
            
            self._save()
    
    def forget_pattern(self, pattern_id: str) -> bool:
        """Manually remove a learned pattern."""
        with self._lock:
            if pattern_id in self._patterns:
                del self._patterns[pattern_id]
                self._save()
                return True
            return False
    
    def clear_learning_data(self):
        """Clear all learning data."""
        with self._lock:
            self._feedback_history.clear()
            self._patterns.clear()
            self._tool_preferences.clear()
            self._time_patterns.clear()
            self._save()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get learning statistics."""
        return {
            'total_feedback': len(self._feedback_history),
            'positive_feedback': sum(1 for f in self._feedback_history if f.positive),
            'negative_feedback': sum(1 for f in self._feedback_history if not f.positive),
            'learned_patterns': len(self._patterns),
            'high_confidence_patterns': sum(1 for p in self._patterns.values() if p.confidence >= 0.7),
            'tracked_tools': len(self._tool_preferences),
            'preferred_tools': sum(1 for s in self._tool_preferences.values() if s >= 0.6)
        }


# Singleton instance
_learning_engine: Optional[LearningEngine] = None


def get_learning_engine(storage_path: Optional[Path] = None) -> LearningEngine:
    """Get the singleton learning engine instance."""
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine(storage_path)
    return _learning_engine


def reset_learning_engine():
    """Reset the singleton instance (for testing)."""
    global _learning_engine
    _learning_engine = None


def record_feedback(action_type: str, action_id: str, positive: bool, context: Optional[Dict[str, Any]] = None):
    """Convenience function to record feedback."""
    get_learning_engine().record_feedback(action_type, action_id, positive, context)


def get_tool_preference(tool_name: str) -> float:
    """Get learned preference for a tool."""
    return get_learning_engine().get_tool_preference(tool_name)
