"""
JARVIS Procedural Memory - Learns and stores procedural patterns for repeated tasks.

Procedural memory stores "how to" knowledge - learned patterns of actions that
can be replayed for efficiency. Examples: morning routine, focus mode setup, etc.
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


class ProceduralPattern:
    """Represents a learned procedural pattern."""
    
    def __init__(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        success_count: int = 0,
        failure_count: int = 0,
        last_used: Optional[datetime] = None,
        created_at: Optional[datetime] = None
    ):
        self.name = name
        self.steps = steps  # List of tool calls or actions
        self.context = context or {}  # When/where this pattern applies
        self.success_count = success_count
        self.failure_count = failure_count
        self.last_used = last_used or datetime.now()
        self.created_at = created_at or datetime.now()
    
    @property
    def confidence(self) -> float:
        """Calculate pattern reliability (0.0 to 1.0)."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total
    
    @property
    def pattern_hash(self) -> str:
        """Generate hash for pattern comparison."""
        content = json.dumps(self.steps, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'name': self.name,
            'steps': self.steps,
            'context': self.context,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProceduralPattern':
        """Deserialize from dictionary."""
        last_used = None
        created_at = None
        
        if data.get('last_used'):
            last_used = datetime.fromisoformat(data['last_used'])
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        return cls(
            name=data['name'],
            steps=data['steps'],
            context=data.get('context', {}),
            success_count=data.get('success_count', 0),
            failure_count=data.get('failure_count', 0),
            last_used=last_used,
            created_at=created_at
        )
    
    def record_success(self):
        """Record successful pattern execution."""
        self.success_count += 1
        self.last_used = datetime.now()
    
    def record_failure(self):
        """Record failed pattern execution."""
        self.failure_count += 1
        self.last_used = datetime.now()


class ProceduralMemory:
    """
    Procedural memory system for learning and replaying action patterns.
    
    Features:
    - Pattern storage and retrieval
    - Success/failure tracking
    - Context-based pattern matching
    - Automatic pattern strengthening/weakening
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path(__file__).parent.parent / 'data' / 'procedural.json'
        self.patterns: Dict[str, ProceduralPattern] = {}
        self._load()
    
    def _load(self):
        """Load patterns from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for name, pattern_data in data.items():
                        self.patterns[name] = ProceduralPattern.from_dict(pattern_data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load procedural memory: {e}")
    
    def _save(self):
        """Save patterns to storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {name: pattern.to_dict() for name, pattern in self.patterns.items()}
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save procedural memory: {e}")
    
    def learn_pattern(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> ProceduralPattern:
        """
        Learn a new procedural pattern.
        
        Args:
            name: Pattern identifier (e.g., "morning_routine")
            steps: List of action/tool call dictionaries
            context: Optional context when this pattern applies
            
        Returns:
            The created ProceduralPattern
        """
        pattern = ProceduralPattern(
            name=name,
            steps=steps,
            context=context or {}
        )
        self.patterns[name] = pattern
        self._save()
        return pattern
    
    def get_pattern(self, name: str) -> Optional[ProceduralPattern]:
        """Retrieve a pattern by name."""
        return self.patterns.get(name)
    
    def find_patterns_by_context(self, context: Dict[str, Any]) -> List[ProceduralPattern]:
        """
        Find patterns that match the given context.
        
        Matches patterns where context keys/values overlap.
        Returns patterns sorted by confidence.
        """
        matches = []
        
        for pattern in self.patterns.values():
            score = 0
            for key, value in context.items():
                if key in pattern.context:
                    if pattern.context[key] == value:
                        score += 2
                    else:
                        score -= 1
            
            if score > 0:
                matches.append((score, pattern))
        
        matches.sort(key=lambda x: (x[0], x[1].confidence), reverse=True)
        return [pattern for _, pattern in matches]
    
    def update_pattern(
        self,
        name: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update an existing pattern."""
        pattern = self.patterns.get(name)
        if not pattern:
            return False
        
        if steps is not None:
            pattern.steps = steps
        if context is not None:
            pattern.context.update(context)
        
        self._save()
        return True
    
    def delete_pattern(self, name: str) -> bool:
        """Delete a pattern."""
        if name in self.patterns:
            del self.patterns[name]
            self._save()
            return True
        return False
    
    def list_patterns(self) -> List[str]:
        """List all pattern names."""
        return list(self.patterns.keys())
    
    def get_high_confidence_patterns(self, threshold: float = 0.7) -> List[ProceduralPattern]:
        """Get patterns with confidence above threshold."""
        return [p for p in self.patterns.values() if p.confidence >= threshold]
    
    def get_recently_used(self, limit: int = 5) -> List[ProceduralPattern]:
        """Get most recently used patterns."""
        sorted_patterns = sorted(
            self.patterns.values(),
            key=lambda p: p.last_used or datetime.min,
            reverse=True
        )
        return sorted_patterns[:limit]
    
    def clear_low_confidence_patterns(self, threshold: float = 0.3):
        """Remove patterns with low confidence (forgetting)."""
        to_remove = [
            name for name, pattern in self.patterns.items()
            if pattern.confidence < threshold and pattern.failure_count > 2
        ]
        for name in to_remove:
            del self.patterns[name]
        if to_remove:
            self._save()
        return len(to_remove)


# Singleton instance
_procedural_memory: Optional[ProceduralMemory] = None


def get_procedural_memory(storage_path: Optional[Path] = None) -> ProceduralMemory:
    """Get the singleton procedural memory instance."""
    global _procedural_memory
    if _procedural_memory is None:
        _procedural_memory = ProceduralMemory(storage_path)
    return _procedural_memory


def reset_procedural_memory():
    """Reset the singleton instance (for testing)."""
    global _procedural_memory
    _procedural_memory = None
