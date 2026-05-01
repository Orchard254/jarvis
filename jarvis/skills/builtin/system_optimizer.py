"""
System Optimizer Skill - Analyzes and optimizes system performance

Monitors system health, cleans up resources, and suggests improvements.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import subprocess
import os

from ..base import BaseSkill


class SystemOptimizerSkill(BaseSkill):
    """
    Skill for system optimization and maintenance.
    
    Features:
    - Performance analysis
    - Resource cleanup suggestions
    - Process management
    - Startup optimization
    - Disk cleanup recommendations
    """
    
    def __init__(self):
        super().__init__(
            name="system_optimizer",
            description="Analyze and optimize system performance",
            version="1.0.0"
        )
        
        self.optimization_history: List[Dict[str, Any]] = []
        self.baseline_metrics: Optional[Dict[str, Any]] = None
    
    def get_system_prompt(self) -> str:
        return """You are JARVIS in System Optimizer mode. Your role is to help maintain optimal system performance.

CURRENT SYSTEM STATE:
- CPU Usage: {cpu}%
- Memory Usage: {memory}%
- Disk Usage: {disk}%
- Running Processes: {processes}
- Uptime: {uptime}
- Battery: {battery}

OPTIMIZATION GUIDELINES:
1. Prioritize non-intrusive optimizations first
2. Always explain what will be done before doing it
3. Allow user to approve major changes
4. Track before/after metrics to show improvement
5. Schedule heavy operations during idle time
6. Never kill critical system processes
7. Maintain a log of all optimizations performed

Focus on actionable improvements with measurable impact.""".format(
            cpu=self._get_cpu_usage(),
            memory=self._get_memory_usage(),
            disk=self._get_disk_usage(),
            processes=self._get_process_count(),
            uptime=self._get_uptime(),
            battery=self._get_battery_status()
        )
    
    def execute(self, action: str, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute optimization actions."""
        
        actions = {
            "analyze": self._analyze_performance,
            "cleanup": self._cleanup_recommendations,
            "optimize": self._run_optimization,
            "baseline": self._set_baseline,
            "compare": self._compare_to_baseline,
            "history": self._get_optimization_history
        }
        
        if action not in actions:
            return {
                "success": False,
                "output": None,
                "error": f"Unknown optimizer action: {action}",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Invalid action"
            }
        
        return actions[action](params, context)
    
    def _get_cpu_usage(self) -> str:
        """Get current CPU usage percentage."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", 
                 "(Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples.CookedValue"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"{float(result.stdout.strip()):.1f}"
        except:
            pass
        return "N/A"
    
    def _get_memory_usage(self) -> str:
        """Get current memory usage percentage."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "$os = Get-CimInstance Win32_OperatingSystem; "
                 "($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) * 100 / $os.TotalVisibleMemorySize"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"{float(result.stdout.strip()):.1f}"
        except:
            pass
        return "N/A"
    
    def _get_disk_usage(self) -> str:
        """Get system disk usage percentage."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "$disk = Get-CimInstance Win32_LogicalDisk -Filter 'DeviceID=\"C:\"'; "
                 "($disk.Size - $disk.FreeSpace) * 100 / $disk.Size"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"{float(result.stdout.strip()):.1f}"
        except:
            pass
        return "N/A"
    
    def _get_process_count(self) -> str:
        """Get number of running processes."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "(Get-Process).Count"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return "N/A"
    
    def _get_uptime(self) -> str:
        """Get system uptime."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "$boot = Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime; "
                 "$span = (New-TimeSpan -Start $boot.LastBootUpTime -End (Get-Date)); "
                 "'{0} days, {1} hours, {2} minutes' -f $span.Days, $span.Hours, $span.Minutes"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return "N/A"
    
    def _get_battery_status(self) -> str:
        """Get battery status."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "$bat = Get-CimInstance Win32_Battery; "
                 "if ($bat) {{ '{0}% - {1}' -f $bat.EstimatedChargeRemaining, $bat.BatteryStatus }} else { 'Plugged in' }"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return "N/A"
    
    def _analyze_performance(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze current system performance."""
        try:
            cpu = self._get_cpu_usage()
            memory = self._get_memory_usage()
            disk = self._get_disk_usage()
            processes = self._get_process_count()
            uptime = self._get_uptime()
            battery = self._get_battery_status()
            
            issues = []
            recommendations = []
            
            # Check for high resource usage
            try:
                if float(cpu) > 80:
                    issues.append(f"High CPU usage: {cpu}%")
                    recommendations.append("Consider closing CPU-intensive applications")
            except:
                pass
            
            try:
                if float(memory) > 85:
                    issues.append(f"High memory usage: {memory}%")
                    recommendations.append("Close unused applications or restart to free memory")
            except:
                pass
            
            try:
                if float(disk) > 90:
                    issues.append(f"Low disk space: {disk}% used")
                    recommendations.append("Run disk cleanup or move files to external storage")
            except:
                pass
            
            analysis = {
                "timestamp": datetime.now().isoformat(),
                "metrics": {
                    "cpu": cpu,
                    "memory": memory,
                    "disk": disk,
                    "processes": processes,
                    "uptime": uptime,
                    "battery": battery
                },
                "issues": issues,
                "recommendations": recommendations
            }
            
            output_parts = [
                "=== System Performance Analysis ===",
                f"CPU: {cpu}%",
                f"Memory: {memory}%",
                f"Disk: {disk}%",
                f"Processes: {processes}",
                f"Uptime: {uptime}",
                f"Battery: {battery}"
            ]
            
            if issues:
                output_parts.append("\n⚠ Issues Found:")
                for issue in issues:
                    output_parts.append(f"  - {issue}")
            
            if recommendations:
                output_parts.append("\n💡 Recommendations:")
                for rec in recommendations:
                    output_parts.append(f"  - {rec}")
            
            if not issues:
                output_parts.append("\n✓ System is running optimally!")
            
            return {
                "success": True,
                "output": "\n".join(output_parts),
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Analysis complete. {len(issues)} issues found.",
                "data": analysis
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Analysis failed: {e}"
            }
    
    def _cleanup_recommendations(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate cleanup recommendations."""
        try:
            recommendations = []
            
            # Check temp files
            temp_paths = [
                os.environ.get('TEMP', ''),
                os.environ.get('TMP', ''),
                r'C:\Windows\Temp'
            ]
            
            total_temp_size = 0
            for temp_path in temp_paths:
                if temp_path and os.path.exists(temp_path):
                    try:
                        for root, dirs, files in os.walk(temp_path):
                            for file in files:
                                try:
                                    file_path = os.path.join(root, file)
                                    total_temp_size += os.path.getsize(file_path)
                                except:
                                    pass
                    except:
                        pass
            
            if total_temp_size > 100 * 1024 * 1024:  # > 100MB
                size_mb = total_temp_size / (1024 * 1024)
                recommendations.append(f"Temporary files: {size_mb:.1f}MB can be cleaned")
            
            # Check recycle bin
            try:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "(New-Object -ComObject Shell.Application).NameSpace(10).Items() | Measure-Object -Property Size -Sum | Select-Object -ExpandProperty Sum"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    recycle_size = int(result.stdout.strip())
                    if recycle_size > 0:
                        size_gb = recycle_size / (1024 * 1024 * 1024)
                        recommendations.append(f"Recycle Bin: {size_gb:.2f}GB can be emptied")
            except:
                pass
            
            # Check for large files
            try:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "Get-ChildItem -Path $env:USERPROFILE -Recurse -File -ErrorAction SilentlyContinue | "
                     "Where-Object { $_.Length -gt 500MB } | "
                     "Measure-Object -Property Length -Sum | "
                     "Select-Object -ExpandProperty Count"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    large_file_count = int(result.stdout.strip())
                    if large_file_count > 10:
                        recommendations.append(f"Found {large_file_count} large files (>500MB) to review")
            except:
                pass
            
            if not recommendations:
                recommendations.append("System is clean - no immediate cleanup needed")
            
            output = "=== Cleanup Recommendations ===\n" + "\n".join(f"• {r}" for r in recommendations)
            
            return {
                "success": True,
                "output": output,
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"{len(recommendations)} recommendations generated"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to generate recommendations: {e}"
            }
    
    def _run_optimization(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Run optimization tasks."""
        try:
            task = params.get("task", "all")
            results = []
            
            if task in ["all", "temp"]:
                # Clean temp files
                cleaned = 0
                temp_path = os.environ.get('TEMP', '')
                if temp_path and os.path.exists(temp_path):
                    try:
                        for root, dirs, files in os.walk(temp_path):
                            for file in files:
                                try:
                                    file_path = os.path.join(root, file)
                                    size = os.path.getsize(file_path)
                                    os.remove(file_path)
                                    cleaned += size
                                except:
                                    pass
                    except:
                        pass
                
                if cleaned > 0:
                    results.append(f"Cleaned {cleaned / (1024 * 1024):.1f}MB from temp folder")
            
            if task in ["all", "recycle"]:
                # Empty recycle bin
                try:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive",
                         "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                        timeout=10
                    )
                    results.append("Emptied Recycle Bin")
                except:
                    pass
            
            if task in ["all", "memory"]:
                # Suggest memory optimization
                results.append("Memory optimization: Consider restarting for best results")
            
            output = "=== Optimization Complete ===\n" + "\n".join(f"✓ {r}" for r in results) if results else "No optimizations performed"
            
            self.optimization_history.append({
                "timestamp": datetime.now().isoformat(),
                "task": task,
                "results": results
            })
            
            return {
                "success": True,
                "output": output,
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Optimization complete: {len(results)} tasks"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Optimization failed: {e}"
            }
    
    def _set_baseline(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Set current metrics as baseline."""
        try:
            self.baseline_metrics = {
                "timestamp": datetime.now().isoformat(),
                "cpu": self._get_cpu_usage(),
                "memory": self._get_memory_usage(),
                "disk": self._get_disk_usage(),
                "processes": self._get_process_count()
            }
            
            return {
                "success": True,
                "output": "Performance baseline set. Future comparisons will use these metrics.",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Baseline established"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to set baseline: {e}"
            }
    
    def _compare_to_baseline(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Compare current metrics to baseline."""
        if not self.baseline_metrics:
            return {
                "success": False,
                "output": None,
                "error": "No baseline set. Run 'set baseline' first.",
                "exit_code": 1,
                "verified": True,
                "verify_msg": "Baseline not found"
            }
        
        try:
            current = {
                "cpu": self._get_cpu_usage(),
                "memory": self._get_memory_usage(),
                "disk": self._get_disk_usage(),
                "processes": self._get_process_count()
            }
            
            comparison = []
            for metric in ["cpu", "memory", "disk"]:
                try:
                    baseline_val = float(self.baseline_metrics[metric])
                    current_val = float(current[metric])
                    diff = current_val - baseline_val
                    direction = "↑" if diff > 0 else "↓" if diff < 0 else "→"
                    comparison.append(f"{metric.upper()}: {baseline_val:.1f}% → {current_val:.1f}% ({direction} {abs(diff):.1f}%)")
                except:
                    comparison.append(f"{metric.upper()}: Data unavailable")
            
            try:
                baseline_proc = int(self.baseline_metrics["processes"])
                current_proc = int(current["processes"])
                diff = current_proc - baseline_proc
                comparison.append(f"Processes: {baseline_proc} → {current_proc} ({'+' if diff > 0 else ''}{diff})")
            except:
                comparison.append("Processes: Data unavailable")
            
            output = "=== Performance Comparison ===\n" + "\n".join(comparison)
            
            return {
                "success": True,
                "output": output,
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Comparison complete"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Comparison failed: {e}"
            }
    
    def _get_optimization_history(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Get history of optimizations."""
        count = params.get("count", 10)
        recent = self.optimization_history[-count:]
        
        if not recent:
            return {
                "success": True,
                "output": "No optimization history yet.",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": "History empty"
            }
        
        output = "=== Recent Optimizations ===\n"
        for opt in recent:
            output += f"• {opt['timestamp']}: {opt['task']} - {', '.join(opt['results'])}\n"
        
        return {
            "success": True,
            "output": output,
            "error": None,
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Retrieved {len(recent)} entries"
        }
    
    def get_state(self) -> Dict[str, Any]:
        """Get skill state for persistence."""
        return {
            "optimization_history": self.optimization_history,
            "baseline_metrics": self.baseline_metrics
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore skill state."""
        self.optimization_history = state.get("optimization_history", [])
        self.baseline_metrics = state.get("baseline_metrics")
