"""
JARVIS Reliability Tracking - Tool reliability monitoring and statistics.

Tracks tool execution reliability with:
- Success/failure rates
- Latency percentiles
- Failure pattern detection
- Automatic degradation scoring
"""

import threading
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import json
from pathlib import Path


@dataclass
class ExecutionRecord:
    """Single tool execution record."""
    tool_name: str
    timestamp: datetime
    success: bool
    latency_ms: float
    error: Optional[str] = None
    parameters_hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'tool_name': self.tool_name,
            'timestamp': self.timestamp.isoformat(),
            'success': self.success,
            'latency_ms': self.latency_ms,
            'error': self.error,
            'parameters_hash': self.parameters_hash
        }


@dataclass
class ToolReliability:
    """Reliability metrics for a single tool."""
    tool_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    consecutive_failures: int = 0
    max_consecutive_failures: int = 0
    
    # Latency tracking
    latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    
    # Recent history (for pattern detection)
    recent_history: deque = field(default_factory=lambda: deque(maxlen=50))
    
    # Time tracking
    first_execution: Optional[datetime] = None
    last_execution: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.total_executions == 0:
            return 1.0  # Default to healthy for new tools
        return self.successful_executions / self.total_executions
    
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate (0.0 to 1.0)."""
        return 1.0 - self.success_rate
    
    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)
    
    @property
    def p95_latency_ms(self) -> float:
        """Calculate 95th percentile latency."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]
    
    @property
    def reliability_score(self) -> float:
        """
        Calculate overall reliability score (0.0 to 1.0).
        
        Factors:
        - Success rate (60% weight)
        - Consecutive failures penalty (25% weight)
        - Latency stability (15% weight)
        """
        # Success rate component
        success_component = self.success_rate * 0.6
        
        # Consecutive failures penalty
        if self.consecutive_failures >= 5:
            failure_penalty = 0.25
        elif self.consecutive_failures >= 3:
            failure_penalty = 0.15
        elif self.consecutive_failures >= 1:
            failure_penalty = 0.05
        else:
            failure_penalty = 0.0
        
        # Latency stability (coefficient of variation)
        if len(self.latencies) >= 10:
            mean_lat = self.avg_latency_ms
            if mean_lat > 0:
                variance = sum((x - mean_lat) ** 2 for x in self.latencies) / len(self.latencies)
                std_dev = variance ** 0.5
                cv = std_dev / mean_lat
                latency_component = max(0, 0.15 * (1 - min(cv, 1.0)))
            else:
                latency_component = 0.15
        else:
            latency_component = 0.15  # Default for insufficient data
        
        return max(0.0, min(1.0, success_component - failure_penalty + latency_component))
    
    @property
    def is_degraded(self) -> bool:
        """Check if tool is in degraded state."""
        return self.reliability_score < 0.5 or self.consecutive_failures >= 3
    
    @property
    def is_unhealthy(self) -> bool:
        """Check if tool is unhealthy."""
        return self.reliability_score < 0.3 or self.consecutive_failures >= 5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'tool_name': self.tool_name,
            'total_executions': self.total_executions,
            'successful_executions': self.successful_executions,
            'failed_executions': self.failed_executions,
            'success_rate': self.success_rate,
            'failure_rate': self.failure_rate,
            'consecutive_failures': self.consecutive_failures,
            'avg_latency_ms': self.avg_latency_ms,
            'p95_latency_ms': self.p95_latency_ms,
            'reliability_score': self.reliability_score,
            'is_degraded': self.is_degraded,
            'is_unhealthy': self.is_unhealthy,
            'first_execution': self.first_execution.isoformat() if self.first_execution else None,
            'last_execution': self.last_execution.isoformat() if self.last_execution else None,
            'last_failure': self.last_failure.isoformat() if self.last_failure else None
        }


class ReliabilityTracker:
    """
    Tool reliability tracking service.
    
    Features:
    - Per-tool execution tracking
    - Success/failure rate calculation
    - Latency percentiles
    - Degradation detection
    - Persistent storage
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path(__file__).parent.parent / 'data' / 'reliability.json'
        self._tools: Dict[str, ToolReliability] = {}
        self._lock = threading.Lock()
        self._execution_history: deque = deque(maxlen=1000)
        
        self._load()
    
    def _load(self):
        """Load reliability data from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for tool_name, tool_data in data.items():
                        self._tools[tool_name] = self._dict_to_reliability(tool_data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load reliability data: {e}")
    
    def _save(self):
        """Save reliability data to storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {name: rel.to_dict() for name, rel in self._tools.items()}
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save reliability data: {e}")
    
    def _dict_to_reliability(self, data: Dict[str, Any]) -> ToolReliability:
        """Convert dictionary to ToolReliability."""
        rel = ToolReliability(tool_name=data['tool_name'])
        rel.total_executions = data.get('total_executions', 0)
        rel.successful_executions = data.get('successful_executions', 0)
        rel.failed_executions = data.get('failed_executions', 0)
        rel.consecutive_failures = data.get('consecutive_failures', 0)
        rel.max_consecutive_failures = data.get('max_consecutive_failures', 0)
        
        if data.get('first_execution'):
            rel.first_execution = datetime.fromisoformat(data['first_execution'])
        if data.get('last_execution'):
            rel.last_execution = datetime.fromisoformat(data['last_execution'])
        if data.get('last_failure'):
            rel.last_failure = datetime.fromisoformat(data['last_failure'])
        
        return rel
    
    def record_execution(
        self,
        tool_name: str,
        success: bool,
        latency_ms: float,
        error: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ):
        """Record a tool execution."""
        import hashlib
        
        with self._lock:
            # Get or create tool reliability tracker
            if tool_name not in self._tools:
                self._tools[tool_name] = ToolReliability(tool_name=tool_name)
            
            rel = self._tools[tool_name]
            now = datetime.now()
            
            # Update counters
            rel.total_executions += 1
            rel.last_execution = now
            
            if rel.first_execution is None:
                rel.first_execution = now
            
            if success:
                rel.successful_executions += 1
                rel.consecutive_failures = 0
            else:
                rel.failed_executions += 1
                rel.consecutive_failures += 1
                rel.last_failure = now
                
                if rel.consecutive_failures > rel.max_consecutive_failures:
                    rel.max_consecutive_failures = rel.consecutive_failures
            
            # Track latency
            rel.latencies.append(latency_ms)
            
            # Create execution record
            params_hash = None
            if parameters:
                params_hash = hashlib.md5(
                    json.dumps(parameters, sort_keys=True).encode()
                ).hexdigest()[:8]
            
            record = ExecutionRecord(
                tool_name=tool_name,
                timestamp=now,
                success=success,
                latency_ms=latency_ms,
                error=error,
                parameters_hash=params_hash
            )
            
            rel.recent_history.append(record)
            self._execution_history.append(record)
            
            # Periodic save
            if rel.total_executions % 10 == 0:
                self._save()
    
    def get_reliability(self, tool_name: str) -> Optional[ToolReliability]:
        """Get reliability metrics for a tool."""
        return self._tools.get(tool_name)
    
    def get_all_reliabilities(self) -> Dict[str, ToolReliability]:
        """Get all tool reliabilities."""
        return dict(self._tools)
    
    def get_degraded_tools(self) -> List[ToolReliability]:
        """Get list of degraded tools."""
        return [rel for rel in self._tools.values() if rel.is_degraded]
    
    def get_unhealthy_tools(self) -> List[ToolReliability]:
        """Get list of unhealthy tools."""
        return [rel for rel in self._tools.values() if rel.is_unhealthy]
    
    def get_reliable_tools(self, threshold: float = 0.8) -> List[ToolReliability]:
        """Get tools with reliability above threshold."""
        return [rel for rel in self._tools.values() if rel.reliability_score >= threshold]
    
    def get_recent_failures(
        self, 
        tool_name: Optional[str] = None,
        limit: int = 10
    ) -> List[ExecutionRecord]:
        """Get recent failure records."""
        if tool_name:
            rel = self._tools.get(tool_name)
            if rel:
                failures = [r for r in rel.recent_history if not r.success]
                return failures[-limit:]
        
        # Global recent failures
        failures = [r for r in self._execution_history if not r.success]
        return failures[-limit:]
    
    def reset_tool(self, tool_name: str):
        """Reset reliability tracking for a tool."""
        with self._lock:
            if tool_name in self._tools:
                del self._tools[tool_name]
                self._save()
    
    def reset_all(self):
        """Reset all reliability tracking."""
        with self._lock:
            self._tools.clear()
            self._execution_history.clear()
            self._save()
    
    def get_statistics_summary(self) -> Dict[str, Any]:
        """Get overall reliability statistics summary."""
        if not self._tools:
            return {
                'total_tools': 0,
                'healthy_tools': 0,
                'degraded_tools': 0,
                'unhealthy_tools': 0,
                'avg_success_rate': 1.0,
                'total_executions': 0
            }
        
        reliabilities = list(self._tools.values())
        total_executions = sum(r.total_executions for r in reliabilities)
        successful_executions = sum(r.successful_executions for r in reliabilities)
        
        return {
            'total_tools': len(reliabilities),
            'healthy_tools': len([r for r in reliabilities if not r.is_degraded]),
            'degraded_tools': len([r for r in reliabilities if r.is_degraded and not r.is_unhealthy]),
            'unhealthy_tools': len([r for r in reliabilities if r.is_unhealthy]),
            'avg_success_rate': successful_executions / total_executions if total_executions > 0 else 1.0,
            'total_executions': total_executions,
            'avg_reliability_score': sum(r.reliability_score for r in reliabilities) / len(reliabilities)
        }


# Singleton instance
_reliability_tracker: Optional[ReliabilityTracker] = None


def get_reliability_tracker(storage_path: Optional[Path] = None) -> ReliabilityTracker:
    """Get the singleton reliability tracker instance."""
    global _reliability_tracker
    if _reliability_tracker is None:
        _reliability_tracker = ReliabilityTracker(storage_path)
    return _reliability_tracker


def reset_reliability_tracker():
    """Reset the singleton instance (for testing)."""
    global _reliability_tracker
    _reliability_tracker = None


def record_tool_execution(
    tool_name: str,
    success: bool,
    latency_ms: float,
    error: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None
):
    """Convenience function to record tool execution."""
    get_reliability_tracker().record_execution(
        tool_name, success, latency_ms, error, parameters
    )


def get_tool_reliability(tool_name: str) -> Optional[ToolReliability]:
    """Get reliability metrics for a tool."""
    return get_reliability_tracker().get_reliability(tool_name)


def is_tool_healthy(tool_name: str) -> bool:
    """Check if a tool is healthy."""
    rel = get_tool_reliability(tool_name)
    if rel is None:
        return True  # Unknown tools are assumed healthy
    return not rel.is_unhealthy
