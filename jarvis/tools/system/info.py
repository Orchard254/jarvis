"""
tools/system/info.py — System information tools

Tools for: battery, system info, health, processes, uptime
Uses psutil and PowerShell for system queries.
"""

import logging
import subprocess
from datetime import datetime, timedelta
from typing import Any

import psutil

from ..base import BaseTool, ToolResult

log = logging.getLogger("info_tools")


class BatteryStatusTool(BaseTool):
    """Get battery status and level."""
    
    name = "battery_status"
    description = "Get the current battery level and charging status. Returns percentage and whether it's charging or discharging."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            battery = psutil.sensors_battery()
            
            if battery is None:
                # No battery (desktop PC)
                return ToolResult.ok("No battery detected (desktop computer)")
            
            percent = battery.percent
            plugged = battery.power_plugged
            
            status = "charging" if plugged else "discharging"
            if plugged and percent >= 100:
                status = "fully charged"
            
            output = f"Battery: {percent}%, {status}"
            return ToolResult.ok(output)
            
        except Exception as e:
            log.error(f"Failed to get battery status: {e}")
            return ToolResult.fail(error=f"Failed to get battery status: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "low"


class SystemInfoTool(BaseTool):
    """Get system information (CPU, RAM, disk)."""
    
    name = "system_info"
    description = "Get system information. Specify type: 'cpu', 'ram', 'disk', 'battery', or 'all' for complete info."
    parameters = {
        "type": {
            "type": "string",
            "enum": ["cpu", "ram", "disk", "battery", "all"],
            "description": "Type of info to retrieve (default: all)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        info_type = kwargs.get("type", "all")
        valid_types = ["cpu", "ram", "disk", "battery", "all"]
        if info_type not in valid_types:
            return False, f"type must be one of: {', '.join(valid_types)}"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            info_type = kwargs.get("type", "all")
            results = []
            
            if info_type in ["cpu", "all"]:
                cpu_percent = psutil.cpu_percent(interval=0.5)
                cpu_freq = psutil.cpu_freq()
                cpu_count = psutil.cpu_count(logical=True)
                results.append(f"CPU: {cpu_percent}% usage, {cpu_count} cores" + 
                             (f", {cpu_freq.current:.0f}MHz" if cpu_freq else ""))
            
            if info_type in ["ram", "all"]:
                mem = psutil.virtual_memory()
                results.append(f"RAM: {mem.percent}% used ({mem.available / 1024**3:.1f}GB free of {mem.total / 1024**3:.1f}GB)")
            
            if info_type in ["disk", "all"]:
                disk = psutil.disk_usage("C:")
                results.append(f"Disk C: {disk.percent}% used ({disk.free / 1024**3:.1f}GB free of {disk.total / 1024**3:.1f}GB)")
            
            if info_type in ["battery", "all"]:
                battery = psutil.sensors_battery()
                if battery:
                    status = "charging" if battery.power_plugged else "discharging"
                    results.append(f"Battery: {battery.percent}% ({status})")
                else:
                    results.append("Battery: N/A (desktop)")
            
            return ToolResult.ok(" | ".join(results))
            
        except Exception as e:
            log.error(f"Failed to get system info: {e}")
            return ToolResult.fail(error=f"Failed to get system info: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class SystemHealthTool(BaseTool):
    """Get full system health report."""
    
    name = "system_health"
    description = "Get a comprehensive system health report including CPU, RAM, disk, temperature (if available), and top processes."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            lines = []
            
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.5)
            cpu_per_core = psutil.cpu_percent(percpu=True)
            lines.append(f"CPU Usage: {cpu_percent}% overall")
            if len(cpu_per_core) <= 8:  # Only show per-core if manageable
                lines.append(f"  Per core: {', '.join(f'{c}%' for c in cpu_per_core)}")
            
            # RAM
            mem = psutil.virtual_memory()
            lines.append(f"Memory: {mem.percent}% used ({mem.available / 1024**3:.1f}GB free)")
            
            # Disk
            disk = psutil.disk_usage("C:")
            lines.append(f"Disk C: {disk.percent}% used")
            
            # Top processes by CPU
            lines.append("\nTop Processes (CPU):")
            procs = sorted(psutil.process_iter(["pid", "name", "cpu_percent"]), 
                          key=lambda x: x.info["cpu_percent"] or 0, reverse=True)[:5]
            for p in procs:
                lines.append(f"  {p.info['name']}: {p.info['cpu_percent']:.1f}%")
            
            # Network
            net_io = psutil.net_io_counters()
            lines.append(f"\nNetwork: ↑{net_io.bytes_sent / 1024 / 1024:.1f}MB ↓{net_io.bytes_recv / 1024 / 1024:.1f}MB")
            
            return ToolResult.ok("\n".join(lines))
            
        except Exception as e:
            log.error(f"Failed to get system health: {e}")
            return ToolResult.fail(error=f"Failed to get system health: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.0
    
    def risk_level(self) -> str:
        return "low"


class GetTopProcessesTool(BaseTool):
    """Get top processes by resource usage."""
    
    name = "get_top_processes"
    description = "Get the top processes by CPU or memory usage. Returns process name, PID, and usage percentage."
    parameters = {
        "limit": {
            "type": "integer",
            "description": "Number of processes to return (default: 5, max: 20)",
        },
        "by": {
            "type": "string",
            "enum": ["cpu", "memory", "both"],
            "description": "Sort by CPU, memory, or both (default: cpu)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        limit = kwargs.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            return False, "limit must be a positive integer"
        if limit > 20:
            return False, "limit cannot exceed 20"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            limit = min(kwargs.get("limit", 5), 20)
            sort_by = kwargs.get("by", "cpu")
            
            results = []
            
            if sort_by in ["cpu", "both"]:
                procs = sorted(
                    psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                    key=lambda x: x.info["cpu_percent"] or 0,
                    reverse=True,
                )[:limit]
                
                results.append("=== By CPU ===")
                for p in procs:
                    results.append(f"{p.info['name']}: CPU {p.info['cpu_percent']:.1f}%, Mem {p.info['memory_percent']:.1f}%")
            
            if sort_by in ["memory", "both"]:
                procs = sorted(
                    psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                    key=lambda x: x.info["memory_percent"] or 0,
                    reverse=True,
                )[:limit]
                
                results.append("\n=== By Memory ===")
                for p in procs:
                    results.append(f"{p.info['name']}: CPU {p.info['cpu_percent']:.1f}%, Mem {p.info['memory_percent']:.1f}%")
            
            return ToolResult.ok("\n".join(results))
            
        except Exception as e:
            log.error(f"Failed to get top processes: {e}")
            return ToolResult.fail(error=f"Failed to get top processes: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class GetUptimeTool(BaseTool):
    """Get system uptime."""
    
    name = "get_uptime"
    description = "Get how long the system has been running since last boot."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            now = datetime.now()
            uptime = now - boot_time
            
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            parts = []
            if days > 0:
                parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
            
            uptime_str = ", ".join(parts)
            boot_str = boot_time.strftime("%Y-%m-%d %H:%M:%S")
            
            return ToolResult.ok(f"Uptime: {uptime_str}\nLast boot: {boot_str}")
            
        except Exception as e:
            log.error(f"Failed to get uptime: {e}")
            return ToolResult.fail(error=f"Failed to get uptime: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
INFO_TOOLS = [
    BatteryStatusTool,
    SystemInfoTool,
    SystemHealthTool,
    GetTopProcessesTool,
    GetUptimeTool,
]
