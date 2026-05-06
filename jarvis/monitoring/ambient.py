"""
JARVIS Ambient Monitoring - Background system state monitoring.

Continuously monitors system state for:
- Resource usage (CPU, memory, disk)
- Network connectivity
- Active applications
- System events
"""

import logging
import threading
import time
import psutil
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """Snapshot of current system state."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_up: bool
    battery_percent: Optional[float]
    is_charging: Optional[bool]
    active_window: Optional[str]
    running_app_count: int
    temperature: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent,
            'disk_percent': self.disk_percent,
            'network_up': self.network_up,
            'battery_percent': self.battery_percent,
            'is_charging': self.is_charging,
            'active_window': self.active_window,
            'running_app_count': self.running_app_count,
            'temperature': self.temperature
        }


@dataclass
class StateChange:
    """Represents a detected state change."""
    timestamp: datetime
    category: str  # 'cpu', 'memory', 'network', etc.
    old_value: Any
    new_value: Any
    severity: str = 'info'  # 'info', 'warning', 'critical'


class AmbientMonitor:
    """
    Background system monitoring service.
    
    Features:
    - Continuous resource monitoring
    - Change detection with thresholds
    - Event callbacks for significant changes
    - Historical state tracking
    """
    
    # Thresholds for change detection
    THRESHOLDS = {
        'cpu_high': 80.0,
        'cpu_critical': 95.0,
        'memory_high': 85.0,
        'memory_critical': 95.0,
        'disk_high': 90.0,
        'disk_critical': 98.0,
        'battery_low': 20.0,
        'battery_critical': 5.0,
    }
    
    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[[StateChange], None]] = []
        
        self._last_state: Optional[SystemState] = None
        self._state_history: List[SystemState] = []
        self._max_history = 100
        
        self._change_callbacks: Dict[str, List[Callable]] = {}
    
    def add_callback(self, callback: Callable[[StateChange], None]):
        """Add callback for any state change."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[StateChange], None]):
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def on_change(self, category: str, callback: Callable[[Any, Any], None]):
        """Register callback for specific category changes."""
        if category not in self._change_callbacks:
            self._change_callbacks[category] = []
        self._change_callbacks[category].append(callback)
    
    def start(self):
        """Start background monitoring."""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop(self):
        """Stop background monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
            self._monitor_thread = None
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                current_state = self._capture_state()
                
                if self._last_state:
                    changes = self._detect_changes(self._last_state, current_state)
                    for change in changes:
                        self._notify_change(change)
                
                self._last_state = current_state
                self._add_to_history(current_state)
                
            except Exception as e:
                logger.error(f"Ambient monitor error: {e}", exc_info=True)
            
            time.sleep(self.poll_interval)
    
    def _capture_state(self) -> SystemState:
        """Capture current system state."""
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        
        # Network connectivity
        network_up = psutil.net_if_stats()
        is_up = any(stats.isup for stats in network_up.values())
        
        # Battery (if available)
        battery = psutil.sensors_battery()
        battery_percent = battery.percent if battery else None
        is_charging = battery.power_plugged if battery else None
        
        # Active window (Windows-specific, simplified)
        active_window = None
        try:
            import pygetwindow as gw
            active_window = gw.getActiveWindowTitle()
        except Exception as e:
            logger.debug(f"Could not get active window (pygetwindow not available): {e}")
        
        # Running applications count
        running_app_count = len([p for p in psutil.process_iter(['name']) if p.info['name']])
        
        # Temperature (if available)
        temperature = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        temperature = entries[0].current
                        break
        except Exception as e:
            logger.debug(f"Could not read temperature sensors: {e}")
        
        return SystemState(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_percent=disk_percent,
            network_up=is_up,
            battery_percent=battery_percent,
            is_charging=is_charging,
            active_window=active_window,
            running_app_count=running_app_count,
            temperature=temperature
        )
    
    def _detect_changes(self, old: SystemState, new: SystemState) -> List[StateChange]:
        """Detect significant changes between states."""
        changes = []
        
        # CPU changes
        if abs(new.cpu_percent - old.cpu_percent) > 10:
            severity = 'critical' if new.cpu_percent > self.THRESHOLDS['cpu_critical'] else \
                      'warning' if new.cpu_percent > self.THRESHOLDS['cpu_high'] else 'info'
            changes.append(StateChange(
                timestamp=datetime.now(),
                category='cpu',
                old_value=old.cpu_percent,
                new_value=new.cpu_percent,
                severity=severity
            ))
        
        # Memory changes
        if abs(new.memory_percent - old.memory_percent) > 5:
            severity = 'critical' if new.memory_percent > self.THRESHOLDS['memory_critical'] else \
                      'warning' if new.memory_percent > self.THRESHOLDS['memory_high'] else 'info'
            changes.append(StateChange(
                timestamp=datetime.now(),
                category='memory',
                old_value=old.memory_percent,
                new_value=new.memory_percent,
                severity=severity
            ))
        
        # Network status changes
        if new.network_up != old.network_up:
            changes.append(StateChange(
                timestamp=datetime.now(),
                category='network',
                old_value=old.network_up,
                new_value=new.network_up,
                severity='warning' if not new.network_up else 'info'
            ))
        
        # Battery changes
        if old.battery_percent and new.battery_percent:
            if old.battery_percent > self.THRESHOLDS['battery_low'] >= new.battery_percent:
                changes.append(StateChange(
                    timestamp=datetime.now(),
                    category='battery',
                    old_value=old.battery_percent,
                    new_value=new.battery_percent,
                    severity='warning'
                ))
            elif old.battery_percent > self.THRESHOLDS['battery_critical'] >= new.battery_percent:
                changes.append(StateChange(
                    timestamp=datetime.now(),
                    category='battery',
                    old_value=old.battery_percent,
                    new_value=new.battery_percent,
                    severity='critical'
                ))
        
        # Active window changes
        if new.active_window != old.active_window:
            changes.append(StateChange(
                timestamp=datetime.now(),
                category='window',
                old_value=old.active_window,
                new_value=new.active_window,
                severity='info'
            ))
        
        return changes
    
    def _notify_change(self, change: StateChange):
        """Notify callbacks of a state change."""
        # General callbacks
        for callback in self._callbacks:
            try:
                callback(change)
            except Exception as e:
                logger.error(f"Error in change callback: {e}", exc_info=True)
        
        # Category-specific callbacks
        if change.category in self._change_callbacks:
            for callback in self._change_callbacks[change.category]:
                try:
                    callback(change.old_value, change.new_value)
                except Exception as e:
                    logger.error(f"Error in category callback: {e}", exc_info=True)
    
    def _add_to_history(self, state: SystemState):
        """Add state to history."""
        self._state_history.append(state)
        if len(self._state_history) > self._max_history:
            self._state_history.pop(0)
    
    def get_current_state(self) -> Optional[SystemState]:
        """Get the most recent captured state."""
        return self._last_state
    
    def get_state_history(self, limit: int = 10) -> List[SystemState]:
        """Get recent state history."""
        return self._state_history[-limit:]
    
    def get_average_cpu(self, samples: int = 10) -> float:
        """Get average CPU usage over recent samples."""
        if not self._state_history:
            return 0.0
        recent = self._state_history[-samples:]
        return sum(s.cpu_percent for s in recent) / len(recent)
    
    def get_average_memory(self, samples: int = 10) -> float:
        """Get average memory usage over recent samples."""
        if not self._state_history:
            return 0.0
        recent = self._state_history[-samples:]
        return sum(s.memory_percent for s in recent) / len(recent)


# Singleton instance
_ambient_monitor: Optional[AmbientMonitor] = None


def get_ambient_monitor(poll_interval: float = 2.0) -> AmbientMonitor:
    """Get the singleton ambient monitor instance."""
    global _ambient_monitor
    if _ambient_monitor is None:
        _ambient_monitor = AmbientMonitor(poll_interval=poll_interval)
    return _ambient_monitor


def reset_ambient_monitor():
    """Reset the singleton instance (for testing)."""
    global _ambient_monitor
    if _ambient_monitor:
        _ambient_monitor.stop()
    _ambient_monitor = None


def start_monitoring():
    """Convenience function to start ambient monitoring."""
    get_ambient_monitor().start()


def stop_monitoring():
    """Convenience function to stop ambient monitoring."""
    get_ambient_monitor().stop()


def get_system_state() -> Optional[SystemState]:
    """Get current system state."""
    return get_ambient_monitor().get_current_state()
