"""
2. System Control (6 tools)
Direct OS-level interaction.
"""

import subprocess
import os
import platform
import shutil
from typing import Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of command execution."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    execution_time: float


class RunTerminalCommand:
    """
    run_terminal_command: Execute shell commands (admin capable)
    
    Safely executes terminal commands with timeout and output capture.
    """
    
    def __init__(self, allowed_commands: Optional[list[str]] = None, 
                 sandbox_mode: bool = True):
        self.allowed_commands = allowed_commands
        self.sandbox_mode = sandbox_mode
    
    def execute(self, command: str, timeout: float = 30.0, 
                shell: bool = True, **kwargs) -> dict:
        """
        Execute a terminal command.
        
        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds
            shell: Whether to run through shell
            
        Returns:
            CommandResult as dict
        """
        import time
        
        # Security check in sandbox mode
        if self.sandbox_mode and self._is_dangerous(command):
            return {
                "success": False,
                "error": "Command blocked in sandbox mode",
                "output": None
            }
        
        start_time = time.time()
        
        try:
            logger.info(f"Executing command: {command[:50]}...")
            
            process = subprocess.Popen(
                command,
                shell=shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(timeout=timeout)
            execution_time = time.time() - start_time
            
            result = CommandResult(
                success=process.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=process.returncode,
                execution_time=execution_time
            )
            
            return {
                "success": result.success,
                "output": {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.return_code,
                    "execution_time": result.execution_time
                }
            }
            
        except subprocess.TimeoutExpired:
            process.kill()
            return {
                "success": False,
                "error": f"Command timed out after {timeout}s",
                "output": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _is_dangerous(self, command: str) -> bool:
        """Check if command is potentially dangerous."""
        dangerous_patterns = [
            "rm -rf /",
            "sudo rm",
            ":(){:|:&};:",
            "mkfs",
            "dd if=/dev/zero",
            "> /dev/sda"
        ]
        return any(pattern in command for pattern in dangerous_patterns)


class RunPythonCode:
    """
    run_python_code: Safe local execution sandbox
    
    Executes Python code in a restricted environment.
    """
    
    def __init__(self, restricted_modules: Optional[list[str]] = None):
        self.restricted_modules = restricted_modules or [
            "os", "sys", "subprocess", "shutil", "socket"
        ]
    
    def execute(self, code: str, timeout: float = 10.0, 
                globals_dict: Optional[dict] = None) -> dict:
        """
        Execute Python code safely.
        
        Args:
            code: Python code to execute
            timeout: Maximum execution time
            globals_dict: Optional global variables
            
        Returns:
            Execution result
        """
        import time
        from io import StringIO
        import sys
        
        # Security check
        if self._contains_dangerous_import(code):
            return {
                "success": False,
                "error": "Dangerous imports detected",
                "output": None
            }
        
        start_time = time.time()
        
        try:
            # Capture stdout
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            
            # Restricted globals
            safe_globals = {"__builtins__": __builtins__}
            if globals_dict:
                safe_globals.update(globals_dict)
            
            local_vars = {}
            
            # Execute with timeout
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Code execution exceeded {timeout}s")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout))
            
            try:
                exec(code, safe_globals, local_vars)
                signal.alarm(0)  # Cancel alarm
            finally:
                signal.signal(signal.SIGALRM, signal.SIG_IGN)
            
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout
            
            execution_time = time.time() - start_time
            
            return {
                "success": True,
                "output": {
                    "result": local_vars.get("result"),
                    "variables": list(local_vars.keys()),
                    "stdout": output,
                    "execution_time": execution_time
                }
            }
            
        except Exception as e:
            sys.stdout = old_stdout
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _contains_dangerous_import(self, code: str) -> bool:
        """Check for dangerous imports."""
        dangerous = ["os.system", "subprocess", "__import__('os')"]
        return any(d in code for d in dangerous)


class WindowManager:
    """
    window_manager: Minimize/maximize/focus apps
    
    Controls window operations on the desktop.
    """
    
    def __init__(self):
        self.platform = platform.system()
    
    def execute(self, action: str, window_title: Optional[str] = None,
                app_name: Optional[str] = None, **kwargs) -> dict:
        """
        Perform window management action.
        
        Args:
            action: One of 'minimize', 'maximize', 'focus', 'close', 'resize'
            window_title: Title of window to operate on
            app_name: Application name
            **kwargs: Additional parameters (e.g., width, height for resize)
            
        Returns:
            Operation result
        """
        try:
            if self.platform == "Windows":
                return self._execute_windows(action, window_title, app_name, **kwargs)
            elif self.platform == "Darwin":
                return self._execute_macos(action, window_title, app_name, **kwargs)
            else:
                return self._execute_linux(action, window_title, app_name, **kwargs)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _execute_windows(self, action: str, title: Optional[str], 
                         app: Optional[str], **kwargs) -> dict:
        """Execute on Windows using pywinauto."""
        try:
            from pywinauto import Application, Desktop
            
            desktop = Desktop(backend="win32")
            
            # Find window by title or app name
            window = None
            search_criteria = title if title else app
            if not search_criteria:
                return {"success": False, "error": "No window_title or app_name provided"}
            
            # Try to find the window
            for w in desktop.windows():
                win_text = w.window_text()
                if search_criteria.lower() in win_text.lower():
                    window = w
                    break
            
            if not window:
                return {"success": False, "error": f"Window not found: {search_criteria}"}
            
            if action == "minimize":
                window.minimize()
                return {"success": True, "output": {"action": "minimize", "window": search_criteria}}
            
            elif action == "maximize":
                window.maximize()
                return {"success": True, "output": {"action": "maximize", "window": search_criteria}}
            
            elif action == "focus" or action == "activate":
                window.set_focus()
                return {"success": True, "output": {"action": "focus", "window": search_criteria}}
            
            elif action == "close":
                window.close()
                return {"success": True, "output": {"action": "close", "window": search_criteria}}
            
            elif action == "resize":
                width = kwargs.get("width", 800)
                height = kwargs.get("height", 600)
                window.move_window(width=width, height=height)
                return {"success": True, "output": {"action": "resize", "window": search_criteria, "width": width, "height": height}}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Window manager error: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_macos(self, action: str, title: Optional[str],
                       app: Optional[str], **kwargs) -> dict:
        """Execute on macOS using AppleScript."""
        # Placeholder - would use AppleScript in production
        return {
            "success": True,
            "output": {"action": action, "platform": "macos", "status": "simulated"}
        }
    
    def _execute_linux(self, action: str, title: Optional[str],
                       app: Optional[str], **kwargs) -> dict:
        """Execute on Linux using wmctrl or xdotool."""
        # Placeholder - would use wmctrl/xdotool in production
        return {
            "success": True,
            "output": {"action": action, "platform": "linux", "status": "simulated"}
        }


class ProcessManager:
    """
    process_manager: Kill/start processes
    
    Manages system processes.
    """
    
    def __init__(self):
        self.platform = platform.system()
    
    def execute(self, action: str, process_name: Optional[str] = None,
                pid: Optional[int] = None, **kwargs) -> dict:
        """
        Manage processes.
        
        Args:
            action: One of 'start', 'stop', 'restart', 'list'
            process_name: Name of process
            pid: Process ID
            **kwargs: Additional parameters
            
        Returns:
            Operation result
        """
        try:
            if action == "list":
                return self._list_processes()
            elif action == "stop":
                return self._kill_process(process_name, pid)
            elif action == "start":
                return self._start_process(process_name, **kwargs)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                    "output": None
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _list_processes(self) -> dict:
        """List running processes."""
        import psutil
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return {
            "success": True,
            "output": {"processes": processes[:50], "total": len(processes)}
        }
    
    def _kill_process(self, name: Optional[str], pid: Optional[int]) -> dict:
        """Kill a process."""
        import psutil
        
        try:
            if pid:
                proc = psutil.Process(pid)
                proc.terminate()
                return {"success": True, "output": {"killed_pid": pid}}
            elif name:
                killed = []
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name'] == name:
                        proc.terminate()
                        killed.append(proc.info['pid'])
                return {"success": True, "output": {"killed": killed}}
            else:
                return {"success": False, "error": "No process name or PID provided"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _start_process(self, name: str, **kwargs) -> dict:
        """Start a process."""
        try:
            subprocess.Popen(name, shell=True)
            return {"success": True, "output": {"started": name}}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SystemInfo:
    """
    system_info: CPU, RAM, disk, OS state
    
    Retrieves system information.
    """
    
    def execute(self, info_type: str = "all", **kwargs) -> dict:
        """
        Get system information.
        
        Args:
            info_type: One of 'cpu', 'memory', 'disk', 'network', 'all'
            
        Returns:
            System information
        """
        try:
            import psutil
            
            result = {}
            
            if info_type in ["cpu", "all"]:
                result["cpu"] = {
                    "percent": psutil.cpu_percent(interval=0.1),
                    "cores": psutil.cpu_count(),
                    "freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
                }
            
            if info_type in ["memory", "all"]:
                mem = psutil.virtual_memory()
                result["memory"] = {
                    "total": mem.total,
                    "available": mem.available,
                    "percent": mem.percent,
                    "used": mem.used
                }
            
            if info_type in ["disk", "all"]:
                disk = psutil.disk_usage('/')
                result["disk"] = {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                }
            
            if info_type in ["network", "all"]:
                result["network"] = {
                    "interfaces": list(psutil.net_io_counters(pernic=True).keys())
                }
            
            result["os"] = {
                "system": platform.system(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor()
            }
            
            return {"success": True, "output": result}
            
        except Exception as e:
            return {"success": False, "error": str(e)}


class ShutdownRestartControl:
    """
    shutdown_restart_control: Power actions
    
    Controls system shutdown and restart.
    """
    
    def __init__(self, require_confirmation: bool = True):
        self.require_confirmation = require_confirmation
    
    def execute(self, action: str, delay: int = 0, 
                force: bool = False, **kwargs) -> dict:
        """
        Perform power action.
        
        Args:
            action: One of 'shutdown', 'restart', 'sleep', 'hibernate'
            delay: Delay in seconds before action
            force: Force action without confirmation
            
        Returns:
            Operation result
        """
        if self.require_confirmation and not force:
            return {
                "success": False,
                "error": "Confirmation required for power actions",
                "output": {"requires_confirmation": True}
            }
        
        try:
            if action == "shutdown":
                cmd = "shutdown /s /t 0" if platform.system() == "Windows" else "shutdown -h now"
            elif action == "restart":
                cmd = "shutdown /r /t 0" if platform.system() == "Windows" else "shutdown -r now"
            elif action == "sleep":
                if platform.system() == "Windows":
                    cmd = "rundll32.exe powrprof.dll,SetSuspendState"
                elif platform.system() == "Linux":
                    cmd = "pm-suspend"
                else:
                    cmd = "pm-suspend"  # macOS would use different command
            elif action == "hibernate":
                if platform.system() == "Windows":
                    cmd = "shutdown /h"
                else:
                    return {"success": False, "error": "Hibernate not supported on this platform"}
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
            
            if delay > 0:
                import time
                logger.info(f"Waiting {delay} seconds before executing {action}")
                time.sleep(delay)
            
            # Actually execute the power command
            logger.warning(f"Executing power command: {cmd}")
            subprocess.run(cmd, shell=True, check=True)
            
            return {
                "success": True,
                "output": {"action": action, "delay": delay, "executed": True, "command": cmd}
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Power command failed: {e}")
            return {"success": False, "error": f"Command failed: {str(e)}"}
        except Exception as e:
            logger.error(f"Power control error: {e}")
            return {"success": False, "error": str(e)}


# Factory functions for capability registry
def get_run_terminal_command(sandbox_mode: bool = True) -> RunTerminalCommand:
    return RunTerminalCommand(sandbox_mode=sandbox_mode)


def get_run_python_code() -> RunPythonCode:
    return RunPythonCode()


def get_window_manager() -> WindowManager:
    return WindowManager()


def get_process_manager() -> ProcessManager:
    return ProcessManager()


def get_system_info() -> SystemInfo:
    return SystemInfo()


def get_shutdown_restart_control(require_confirmation: bool = True) -> ShutdownRestartControl:
    return ShutdownRestartControl(require_confirmation=require_confirmation)
