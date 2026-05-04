"""
JARVIS Health Check - System health monitoring and diagnostics.

Provides on-demand and continuous health checks for:
- Core component availability
- Tool functionality
- Memory system status
- External service connectivity
"""

import threading
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = 'healthy'
    DEGRADED = 'degraded'
    UNHEALTHY = 'unhealthy'
    UNKNOWN = 'unknown'


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus
    message: str
    latency_ms: Optional[float] = None
    last_check: Optional[datetime] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'status': self.status.value,
            'message': self.message,
            'latency_ms': self.latency_ms,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'details': self.details
        }


@dataclass
class HealthReport:
    """Overall system health report."""
    timestamp: datetime
    overall_status: HealthStatus
    components: List[ComponentHealth]
    summary: str
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'overall_status': self.overall_status.value,
            'components': [c.to_dict() for c in self.components],
            'summary': self.summary,
            'recommendations': self.recommendations
        }


class HealthChecker:
    """
    System health checking service.
    
    Features:
    - Component-level health checks
    - Latency measurement
    - Automatic periodic checks
    - Health event callbacks
    """
    
    def __init__(self):
        self._checks: Dict[str, Callable[[], ComponentHealth]] = {}
        self._last_report: Optional[HealthReport] = None
        self._running = False
        self._check_thread: Optional[threading.Thread] = None
        self._check_interval = 30.0  # seconds
        self._callbacks: List[Callable[[HealthReport], None]] = []
        
        # Register default checks
        self._register_default_checks()
    
    def _register_default_checks(self):
        """Register built-in health checks."""
        self.register_check('memory', self._check_memory)
        self.register_check('tools', self._check_tools)
        self.register_check('filesystem', self._check_filesystem)
    
    def register_check(self, name: str, check_func: Callable[[], ComponentHealth]):
        """Register a health check function."""
        self._checks[name] = check_func
    
    def unregister_check(self, name: str):
        """Remove a health check."""
        if name in self._checks:
            del self._checks[name]
    
    def add_callback(self, callback: Callable[[HealthReport], None]):
        """Add callback for health report updates."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[HealthReport], None]):
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def check_all(self) -> HealthReport:
        """Run all health checks and return report."""
        start_time = datetime.now()
        components = []
        
        for name, check_func in self._checks.items():
            try:
                component_health = check_func()
                component_health.last_check = datetime.now()
                components.append(component_health)
            except Exception as e:
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(e)}",
                    last_check=datetime.now()
                ))
        
        # Determine overall status
        statuses = [c.status for c in components]
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            overall = HealthStatus.HEALTHY
        else:
            overall = HealthStatus.UNKNOWN
        
        # Generate summary and recommendations
        summary, recommendations = self._generate_insights(components)
        
        report = HealthReport(
            timestamp=start_time,
            overall_status=overall,
            components=components,
            summary=summary,
            recommendations=recommendations
        )
        
        self._last_report = report
        self._notify_callbacks(report)
        
        return report
    
    def _check_memory(self) -> ComponentHealth:
        """Check memory system health."""
        try:
            from memory import get_memory_manager
            
            start = time.time()
            manager = get_memory_manager()
            
            # Try basic operations
            working = manager.working
            episodic = manager.episodic
            semantic = manager.semantic
            
            latency = (time.time() - start) * 1000
            
            return ComponentHealth(
                name='memory',
                status=HealthStatus.HEALTHY,
                message='All memory systems operational',
                latency_ms=latency,
                details={
                    'working_messages': len(getattr(working, 'messages', [])),
                    'episodic_sessions': len(getattr(episodic, 'sessions', [])),
                    'semantic_facts': len(getattr(semantic, 'facts', []))
                }
            )
        except Exception as e:
            return ComponentHealth(
                name='memory',
                status=HealthStatus.DEGRADED,
                message=f"Memory system issue: {str(e)}"
            )
    
    def _check_tools(self) -> ComponentHealth:
        """Check tool registry health."""
        try:
            from jarvis.tools.registry import get_registry
            
            start = time.time()
            registry = get_registry()
            tools = registry.get_tool_names()
            latency = (time.time() - start) * 1000
            
            if len(tools) == 0:
                return ComponentHealth(
                    name='tools',
                    status=HealthStatus.DEGRADED,
                    message='No tools registered',
                    latency_ms=latency
                )
            
            return ComponentHealth(
                name='tools',
                status=HealthStatus.HEALTHY,
                message=f'{len(tools)} tools available',
                latency_ms=latency,
                details={'tool_count': len(tools)}
            )
        except Exception as e:
            return ComponentHealth(
                name='tools',
                status=HealthStatus.UNHEALTHY,
                message=f"Tool system error: {str(e)}"
            )
    
    def _check_filesystem(self) -> ComponentHealth:
        """Check filesystem access."""
        try:
            import os
            import tempfile
            
            start = time.time()
            
            # Test write access
            with tempfile.NamedTemporaryFile(delete=True) as f:
                test_file = f.name
            
            latency = (time.time() - start) * 1000
            
            return ComponentHealth(
                name='filesystem',
                status=HealthStatus.HEALTHY,
                message='Filesystem access OK',
                latency_ms=latency
            )
        except Exception as e:
            return ComponentHealth(
                name='filesystem',
                status=HealthStatus.UNHEALTHY,
                message=f"Filesystem error: {str(e)}"
            )
    
    def _generate_insights(
        self, 
        components: List[ComponentHealth]
    ) -> tuple:
        """Generate summary and recommendations from component health."""
        issues = [c for c in components if c.status != HealthStatus.HEALTHY]
        
        if not issues:
            summary = "All systems operational"
            recommendations = []
        else:
            issue_summary = ", ".join(f"{c.name}: {c.status.value}" for c in issues)
            summary = f"Issues detected: {issue_summary}"
            
            recommendations = []
            for comp in issues:
                if comp.name == 'memory':
                    recommendations.append("Consider restarting memory services")
                elif comp.name == 'tools':
                    recommendations.append("Check tool registration and imports")
                elif comp.name == 'filesystem':
                    recommendations.append("Verify disk space and permissions")
        
        return summary, recommendations
    
    def _notify_callbacks(self, report: HealthReport):
        """Notify callbacks of new health report."""
        for callback in self._callbacks:
            try:
                callback(report)
            except Exception as e:
                print(f"Error in health callback: {e}")
    
    def start_periodic_checks(self, interval: float = 30.0):
        """Start periodic health checking."""
        self._check_interval = interval
        self._running = True
        
        def check_loop():
            while self._running:
                self.check_all()
                time.sleep(self._check_interval)
        
        self._check_thread = threading.Thread(target=check_loop, daemon=True)
        self._check_thread.start()
    
    def stop_periodic_checks(self):
        """Stop periodic health checking."""
        self._running = False
        if self._check_thread:
            self._check_thread.join(timeout=5.0)
            self._check_thread = None
    
    def get_last_report(self) -> Optional[HealthReport]:
        """Get the most recent health report."""
        return self._last_report
    
    def is_healthy(self) -> bool:
        """Check if system is currently healthy."""
        if self._last_report:
            return self._last_report.overall_status == HealthStatus.HEALTHY
        # If no report yet, run checks
        report = self.check_all()
        return report.overall_status == HealthStatus.HEALTHY


# Singleton instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get the singleton health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


def reset_health_checker():
    """Reset the singleton instance (for testing)."""
    global _health_checker
    if _health_checker:
        _health_checker.stop_periodic_checks()
    _health_checker = None


def check_health() -> HealthReport:
    """Convenience function to run health checks."""
    return get_health_checker().check_all()


def start_health_monitoring(interval: float = 30.0):
    """Convenience function to start periodic health checks."""
    get_health_checker().start_periodic_checks(interval)


def stop_health_monitoring():
    """Convenience function to stop periodic health checks."""
    get_health_checker().stop_periodic_checks()
