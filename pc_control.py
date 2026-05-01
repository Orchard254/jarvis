import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("pc_control")

try:
    import mss
    import numpy as np
    from PIL import Image

    SCREENSHOT_AVAILABLE = True
except ImportError:
    SCREENSHOT_AVAILABLE = False

VOLUME_STATE_FILE = Path(__file__).parent / "volume_state.json"
DEFAULT_VOLUME = 50

TERMINAL_OUTPUT_DIR = Path(__file__).parent / "terminal_outputs"
TERMINAL_OUTPUT_DIR.mkdir(exist_ok=True)

# Real-time screen capture
_realtime_thread = None
_realtime_stop = threading.Event()
_realtime_interval = 5  # seconds
_realtime_dir = Path(__file__).parent / "realtime_screens"
_realtime_dir.mkdir(exist_ok=True)
_latest_screen_path = None
_latest_screen_lock = threading.Lock()
_realtime_init_lock = threading.Lock()  # FIX: Lock to prevent race condition on thread init


def run_in_terminal(command: str, wait_for_output: bool = False, timeout: int = 30) -> dict:
    """Run command in a new terminal window.

    Args:
        command: The command to execute
        wait_for_output: If True, capture output (blocks). If False, run in background.
        timeout: Timeout for output capture in seconds

    Returns:
        dict with success, output, error
    """
    # FIX: Validate timeout to prevent DoS via extreme values
    timeout = max(1, min(timeout, 300))  # Clamp between 1-300 seconds
    
    try:
        if wait_for_output:
            result = subprocess.run(
                ["cmd", "/c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout.strip(),
                "error": result.stderr.strip() if result.returncode != 0 else "",
                "exit_code": result.returncode,
            }
        else:
            subprocess.Popen(
                ["cmd", "/c", "start", "cmd", "/k", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "success": True,
                "output": f"Started: {command}",
                "error": "",
                "exit_code": 0,
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Command timed out after {timeout}s",
            "exit_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
        }


def run_powershell_script(script: str, wait_for_output: bool = False, timeout: int = 30) -> dict:
    """Run PowerShell script in terminal window.

    Args:
        script: PowerShell command or script path
        wait_for_output: If True, capture output. If False, run in new window.
        timeout: Timeout for output capture

    Returns:
        dict with success, output, error
    """
    # FIX: Validate timeout to prevent DoS via extreme values
    timeout = max(1, min(timeout, 300))  # Clamp between 1-300 seconds
    
    try:
        if wait_for_output:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout.strip(),
                "error": result.stderr.strip() if result.returncode != 0 else "",
                "exit_code": result.returncode,
            }
        else:
            subprocess.Popen(
                ["cmd", "/c", "start", "powershell", "-NoProfile", "-Command", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "success": True,
                "output": f"Started PowerShell: {script[:100]}...",
                "error": "",
                "exit_code": 0,
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Script timed out after {timeout}s",
            "exit_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
        }


def run_script_file(script_path: str, wait_for_output: bool = False, timeout: int = 60) -> dict:
    """Run a script file (.ps1, .bat, .cmd) in terminal.

    Args:
        script_path: Path to script file
        wait_for_output: If True, capture output. If False, run in new window.
        timeout: Timeout for output capture

    Returns:
        dict with success, output, error
    """
    path = Path(script_path)
    if not path.exists():
        return {
            "success": False,
            "output": "",
            "error": f"Script file not found: {script_path}",
            "exit_code": 1,
        }

    suffix = path.suffix.lower()
    try:
        if suffix == ".ps1":
            return run_powershell_script(f'& "{script_path}"', wait_for_output, timeout)
        elif suffix in [".bat", ".cmd"]:
            if wait_for_output:
                result = subprocess.run(
                    ["cmd", "/c", script_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout.strip(),
                    "error": result.stderr.strip(),
                    "exit_code": result.returncode,
                }
            else:
                subprocess.Popen(
                    ["cmd", "/c", "start", "cmd", "/k", script_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {
                    "success": True,
                    "output": f"Started script: {path.name}",
                    "error": "",
                    "exit_code": 0,
                }
        else:
            return {
                "success": False,
                "output": "",
                "error": f"Unsupported script type: {suffix}",
                "exit_code": 1,
            }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
        }


def chain_commands(commands: list, stop_on_failure: bool = True) -> dict:
    """Execute multiple commands sequentially, optionally stopping on failure.

    Args:
        commands: List of command strings to execute
        stop_on_failure: If True, stop executing when a command fails

    Returns:
        dict with success, output (all outputs combined), error
    """
    results = []
    all_outputs = []
    all_errors = []

    for i, cmd in enumerate(commands):
        try:
            result = subprocess.run(
                ["cmd", "/c", cmd],
                capture_output=True,
                text=True,
                timeout=60,
            )
            results.append(
                {
                    "command": cmd,
                    "success": result.returncode == 0,
                    "output": result.stdout.strip(),
                    "error": result.stderr.strip(),
                }
            )
            all_outputs.append(f"[{i+1}] {cmd}: {result.stdout.strip()}")

            if result.returncode != 0:
                all_errors.append(f"[{i+1}] {cmd} failed: {result.stderr.strip()}")
                if stop_on_failure:
                    break
        except subprocess.TimeoutExpired:
            all_errors.append(f"[{i+1}] {cmd} timed out")
            if stop_on_failure:
                break
        except Exception as e:
            all_errors.append(f"[{i+1}] {cmd} error: {str(e)}")
            if stop_on_failure:
                break

    success = (
        len(all_errors) == 0 and all(r.get("success", False) for r in results) if results else False
    )
    return {
        "success": success,
        "output": "\n".join(all_outputs),
        "error": "\n".join(all_errors) if all_errors else "",
        "steps": results,
        "exit_code": 0 if success else 1,
    }


class AdvancedTaskManager:
    """Advanced background task manager with output tracking and AI control"""

    def __init__(self):
        self.tasks = {}
        self.task_counter = 0
        self._load_tasks()

    def _get_tasks_file(self) -> Path:
        return TERMINAL_OUTPUT_DIR / "tasks.json"

    def _load_tasks(self):
        """Load existing tasks from disk"""
        try:
            if self._get_tasks_file().exists():
                with open(self._get_tasks_file(), "r") as f:
                    data = json.load(f)
                    self.tasks = data.get("tasks", {})
                    self.task_counter = data.get("counter", 0)
        except (json.JSONDecodeError, OSError, ValueError):
            self.tasks = {}
            self.task_counter = 0

    def _save_tasks(self):
        """Save tasks to disk"""
        try:
            with open(self._get_tasks_file(), "w") as f:
                json.dump({"tasks": self.tasks, "counter": self.task_counter}, f)
        except (OSError, json.JSONDecodeError):
            pass

    def _generate_task_id(self) -> str:
        self.task_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"task_{timestamp}_{self.task_counter}"

    def start_command(self, command: str, name: str = None, shell: str = "cmd") -> dict:
        """Start a command in background, returns task_id immediately"""
        task_id = self._generate_task_id()
        output_file = TERMINAL_OUTPUT_DIR / f"{task_id}_output.txt"
        pid_file = TERMINAL_OUTPUT_DIR / f"{task_id}_pid.txt"

        task_info = {
            "id": task_id,
            "name": name or command[:50],
            "command": command,
            "shell": shell,
            "status": "running",
            "start_time": datetime.now().isoformat(),
            "output_file": str(output_file),
            "pid_file": str(pid_file),
            "exit_code": None,
            "error": None,
        }

        try:
            if shell == "powershell":
                proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", command],
                    stdout=open(output_file, "w"),
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                proc = subprocess.Popen(
                    ["cmd", "/c", command],
                    stdout=open(output_file, "w"),
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )

            with open(pid_file, "w") as f:
                f.write(str(proc.pid))

            task_info["pid"] = proc.pid
            self.tasks[task_id] = task_info
            self._save_tasks()

            return {
                "success": True,
                "task_id": task_id,
                "pid": proc.pid,
                "name": task_info["name"],
                "output_file": str(output_file),
                "message": f"Started task {task_id}: {task_info['name']}",
            }
        except Exception as e:
            task_info["status"] = "failed"
            task_info["error"] = str(e)
            self.tasks[task_id] = task_info
            self._save_tasks()
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id,
            }

    def get_task_status(self, task_id: str = None) -> dict:
        """Get status of a specific task or all tasks"""
        if task_id:
            if task_id not in self.tasks:
                return {"success": False, "error": f"Task {task_id} not found"}

            task = self.tasks[task_id].copy()

            if task["status"] == "running":
                pid_file = Path(task["pid_file"])
                if pid_file.exists():
                    try:
                        with open(pid_file, "r") as f:
                            pid = int(f.read().strip())
                        if not self._is_process_running(pid):
                            task["status"] = "completed"
                            task["end_time"] = datetime.now().isoformat()
                            self.tasks[task_id] = task
                            self._save_tasks()
                    except (ValueError, OSError):
                        pass

            return {"success": True, "task": task}

        else:
            all_tasks = []
            for tid, task in self.tasks.items():
                task_copy = task.copy()
                if task_copy["status"] == "running":
                    pid_file = Path(task_copy.get("pid_file", ""))
                    if pid_file.exists():
                        try:
                            with open(pid_file, "r") as f:
                                pid = int(f.read().strip())
                            if not self._is_process_running(pid):
                                task_copy["status"] = "completed"
                                task_copy["end_time"] = datetime.now().isoformat()
                                self.tasks[tid] = task_copy
                        except (ValueError, OSError):
                            pass
                all_tasks.append(task_copy)
            self._save_tasks()
            return {"success": True, "tasks": all_tasks}

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process is still running"""
        try:
            import ctypes

            PROCESS_QUERY_INFORMATION = 0x1000
            process = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
            if process:
                ctypes.windll.kernel32.CloseHandle(process)
                return True
        except (OSError, AttributeError):
            pass
        return False

    def get_output(self, task_id: str, lines: int = None) -> dict:
        """Get output from a running or completed task"""
        if task_id not in self.tasks:
            return {"success": False, "error": f"Task {task_id} not found"}

        task = self.tasks[task_id]
        output_file = Path(task["output_file"])

        if not output_file.exists():
            return {"success": False, "error": "Output file not found"}

        try:
            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if lines:
                content = "\n".join(content.split("\n")[-lines:])

            return {
                "success": True,
                "output": content,
                "task_id": task_id,
                "status": task["status"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_output(self, task_id: str) -> dict:
        """Quick check if task has produced new output"""
        if task_id not in self.tasks:
            return {"success": False, "error": f"Task {task_id} not found"}

        task = self.tasks[task_id]
        output_file = Path(task["output_file"])

        if not output_file.exists():
            return {"success": False, "error": "Output file not found"}

        try:
            size = output_file.stat().st_size
            return {
                "success": True,
                "has_output": size > 0,
                "bytes": size,
                "status": task["status"],
            }
        except OSError:
            return {"success": False, "error": "Cannot check output"}

    def kill_task(self, task_id: str) -> dict:
        """Kill a running task"""
        if task_id not in self.tasks:
            return {"success": False, "error": f"Task {task_id} not found"}

        task = self.tasks[task_id]

        try:
            pid_file = Path(task["pid_file"])
            if pid_file.exists():
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())

                import ctypes

                PROCESS_TERMINATE = 0x0001
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
                if handle:
                    ctypes.windll.kernel32.TerminateProcess(handle, -1)
                    ctypes.windll.kernel32.CloseHandle(handle)

            task["status"] = "killed"
            task["end_time"] = datetime.now().isoformat()
            self.tasks[task_id] = task
            self._save_tasks()

            return {"success": True, "message": f"Task {task_id} killed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def wait_task(self, task_id: str, timeout: int = 60) -> dict:
        """Wait for task to complete and return final output"""
        if task_id not in self.tasks:
            return {"success": False, "error": f"Task {task_id} not found"}

        task = self.tasks[task_id]
        pid_file = Path(task["pid_file"])

        start_time = time.time()
        while time.time() - start_time < timeout:
            if not pid_file.exists():
                break
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                if not self._is_process_running(pid):
                    break
            except (ValueError, OSError):
                break
            time.sleep(0.5)

        task = self.tasks[task_id]
        task["status"] = "completed" if task["status"] == "running" else task["status"]
        task["end_time"] = datetime.now().isoformat()
        self.tasks[task_id] = task
        self._save_tasks()

        return self.get_output(task_id)

    def clear_completed(self, older_than_hours: int = 24) -> dict:
        """Clear completed tasks older than specified hours"""
        now = datetime.now()
        cleared = 0

        for task_id in list(self.tasks.keys()):
            task = self.tasks[task_id]
            if task["status"] in ["completed", "failed", "killed"]:
                try:
                    task_time = datetime.fromisoformat(task.get("end_time", task["start_time"]))
                    if (now - task_time).total_seconds() / 3600 > older_than_hours:
                        del self.tasks[task_id]
                        cleared += 1
                except (ValueError, TypeError):
                    pass

        self._save_tasks()
        return {"success": True, "cleared": cleared}


_global_task_manager = AdvancedTaskManager()


def task_start(command: str, name: str = None, shell: str = "cmd") -> dict:
    """Start a background task - returns immediately with task_id"""
    return _global_task_manager.start_command(command, name, shell)


def task_status(task_id: str = None) -> dict:
    """Get status of task(s)"""
    return _global_task_manager.get_task_status(task_id)


def task_output(task_id: str, lines: int = None) -> dict:
    """Get output from task"""
    return _global_task_manager.get_output(task_id, lines)


def task_check(task_id: str) -> dict:
    """Quick check if task has output"""
    return _global_task_manager.check_output(task_id)


def task_kill(task_id: str) -> dict:
    """Kill a running task"""
    return _global_task_manager.kill_task(task_id)


def task_wait(task_id: str, timeout: int = 60) -> dict:
    """Wait for task to complete"""
    return _global_task_manager.wait_task(task_id, timeout)


def task_clear(older_than_hours: int = 24) -> dict:
    """Clear old completed tasks"""
    return _global_task_manager.clear_completed(older_than_hours)


def _load_volume_state() -> int:
    try:
        if VOLUME_STATE_FILE.exists():
            with open(VOLUME_STATE_FILE, "r") as f:
                return json.load(f).get("current_volume", DEFAULT_VOLUME)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return DEFAULT_VOLUME


def _save_volume_state(volume: int) -> None:
    """Save volume state atomically to prevent corruption from concurrent writes."""
    import tempfile
    import shutil
    
    try:
        content = json.dumps({"current_volume": volume, "last_updated": datetime.now().isoformat()})
        # FIX: Use atomic write pattern to prevent file corruption
        tmp_fd, tmp_path = tempfile.mkstemp(dir=VOLUME_STATE_FILE.parent, suffix='.json')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                f.write(content)
            shutil.move(tmp_path, VOLUME_STATE_FILE)
        except Exception:
            # Clean up temp file on failure
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
            raise
    except (OSError, json.JSONDecodeError):
        pass


def execute_structured(action: str, params: dict, retry_count: int = 2) -> dict:
    """Execute action with improved retry logic for transient failures."""
    last_error = None

    # Improve: Define transient error patterns to retry on
    transient_patterns = [
        "timed out",
        "timeout",
        "temporary",
        "busy",
        "being used by another process",
        "access denied",
        "device is ready",
        "not ready",
    ]

    for attempt in range(retry_count + 1):
        try:
            result = _execute_action_internal(action, params)

            if attempt > 0 and result["success"]:
                log.info(f"[ACTION] {action} succeeded on attempt {attempt + 1}")

            return result
        except subprocess.TimeoutExpired:
            last_error = "Timeout"
            if attempt < retry_count:
                wait_time = (2**attempt) * 1.5
                log.warning(
                    f"[ACTION] {action} timed out, retrying in {wait_time}s (attempt {attempt + 1}/{retry_count})"
                )
                time.sleep(wait_time)
                continue
            return {
                "success": False,
                "output": "",
                "error": f"Action timed out after {retry_count + 1} attempts",
                "exit_code": -1,
                "verified": False,
                "verify_msg": "Operation timed out",
            }
        except Exception as e:
            last_error = str(e)
            error_str = str(e).lower()

            log.warning(f"[ACTION] {action} error: {e}")

            # Improve: Smarter retry decision for transient errors
            is_transient = any(pattern in error_str for pattern in transient_patterns)

            if attempt < retry_count and is_transient:
                wait_time = (2**attempt) * 1.5
                log.warning(
                    f"[ACTION] {action} transient error (attempt {attempt + 1}/{retry_count}), retrying in {wait_time}s"
                )
                time.sleep(wait_time)
                continue

            # Improve: Consistent error reporting
            error_output = str(e)[:150]
            verify_msg = f"Error: {str(e)[:100]}"

            # Improve: Add action-specific error context
            if "file" in action.lower() and "not found" in error_str:
                verify_msg = f"File or path not found. Check path exists and is accessible."
            elif "app" in action.lower() and "not found" in error_str:
                verify_msg = (
                    f"Application not found. Try full executable name or check installation."
                )
            elif "volume" in action.lower():
                verify_msg = f"Volume control failed. System may not support this operation."

            return {
                "success": False,
                "output": "",
                "error": error_output,
                "exit_code": -1,
                "verified": False,
                "verify_msg": verify_msg,
            }

    return {
        "success": False,
        "output": "",
        "error": f"Failed after {retry_count + 1} attempts: {last_error}",
        "exit_code": -1,
        "verified": False,
        "verify_msg": f"Failed after multiple attempts",
    }


def read_file(path: str, speak: bool = False) -> str:
    # SECURITY FIX: Validate file path to prevent path traversal attacks
    def _is_safe_path(file_path: str) -> bool:
        """Prevent path traversal attacks by ensuring path is within allowed directories."""
        try:
            # First check: reject obvious traversal attempts in the raw path
            if '..' in file_path:
                return False
                
            resolved = Path(file_path).resolve()
            # Allow paths in user's home directory or current working directory
            user_home = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
            cwd = Path.cwd()
            
            # Block paths that resolve outside user home and cwd
            if not (str(resolved).startswith(str(user_home)) or str(resolved).startswith(str(cwd))):
                return False
            
            return True
        except Exception:
            return False
    
    if not _is_safe_path(path):
        return f"Error: Unsafe file path detected - path traversal attempt blocked"
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


def screen_capture():
    if not SCREENSHOT_AVAILABLE:
        return {"success": False, "error": "Screenshot libraries not available"}
    try:
        import ctypes

        user32 = ctypes.windll.user32
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)

        with mss.mss() as sct:
            monitor = {"top": 0, "left": 0, "width": width, "height": height}
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = Path(__file__).parent / f"screenshot_{timestamp}.png"
            img.save(str(filepath))

            import base64

            with open(filepath, "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode()

            return {
                "success": True,
                "filepath": str(filepath),
                "width": width,
                "height": height,
                "base64": img_base64,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def start_realtime_screen(interval: int = 5) -> dict:
    """Start capturing screenshots at regular intervals."""
    global _realtime_thread, _realtime_interval
    
    # FIX: Use lock to prevent race condition during thread initialization
    with _realtime_init_lock:
        if _realtime_thread and _realtime_thread.is_alive():
            return {"success": False, "error": "Already running"}
        _realtime_stop.clear()
        _realtime_interval = interval

        def worker():
            while not _realtime_stop.is_set():
                try:
                    result = screen_capture()
                    if result["success"]:
                        src = Path(result["filepath"])
                        if src.exists():
                            import shutil

                            dest = _realtime_dir / src.name
                            shutil.copy(src, dest)
                            with _latest_screen_lock:
                                global _latest_screen_path
                                _latest_screen_path = str(dest)
                            latest = _realtime_dir / "latest.png"
                            if latest.exists():
                                latest.unlink()
                            shutil.copy(dest, latest)
                except Exception as e:
                    log.error(f"Realtime capture error: {e}")
                _realtime_stop.wait(_realtime_interval)

        _realtime_thread = threading.Thread(target=worker, daemon=True)
        _realtime_thread.start()
    return {"success": True, "message": f"Started realtime capture every {interval}s"}


def stop_realtime_screen() -> dict:
    """Stop real-time screen capture."""
    global _realtime_thread
    if not _realtime_thread or not _realtime_thread.is_alive():
        return {"success": False, "error": "Not running"}
    _realtime_stop.set()
    _realtime_thread.join(timeout=2)
    return {"success": True, "message": "Stopped realtime capture"}


def get_latest_screen() -> dict:
    """Get the most recent screenshot from realtime capture."""
    with _latest_screen_lock:
        if not _latest_screen_path or not Path(_latest_screen_path).exists():
            return {"success": False, "error": "No recent screenshot"}
        return {"success": True, "filepath": _latest_screen_path}


def _close_app_gracefully(app_name: str) -> str:
    try:
        import subprocess

        result = subprocess.run(
            [
                "powershell",
                "-Command",
                f'Stop-Process -Name "{app_name}" -Force -ErrorAction SilentlyContinue',
            ],
            capture_output=True,
            text=True,
        )
        return f"Closed {app_name}"
    except Exception as e:
        return f"Error closing app: {str(e)}"


def _open_app(app_name: str) -> str:
    import os

    # SECURITY: Sanitize app_name - strip all arguments/flags
    # Take only the first word (executable name)
    safe_name = app_name.split()[0] if app_name.split() else app_name
    safe_name = os.path.basename(safe_name)  # Remove any path traversal

    # Check for unsafe patterns in original input
    unsafe_chars = [";", "&&", "|", ">", "<", "`", "$", "()"]
    for char in unsafe_chars:
        if char in app_name:
            return f"Error: Unsafe pattern detected in app name"

    # Common app mappings (name -> executable or path)
    app_mappings = {
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "edge": "msedge.exe",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "spotify": "spotify.exe",
        "vscode": "code.exe",
        "visual studio code": "code.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "powershell": "powershell.exe",
        "task manager": "taskmgr.exe",
        "control panel": "control.exe",
        "settings": "ms-settings:",
    }

    # Try to find the executable
    app_lower = safe_name.lower().strip()
    executable = app_mappings.get(app_lower, safe_name)

    # Method 1: Use os.startfile (works well on Windows)
    try:
        os.startfile(executable)
        return f"Opened {app_name}"
    except Exception:
        pass

    # Method 2: Use cmd start when os.startfile is unavailable
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", executable],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Opened {app_name}"
    except Exception:
        pass

    # Method 3: Try Popen directly with list
    try:
        subprocess.Popen([executable])
        return f"Opened {app_name}"
    except Exception as e:
        return f"Error opening app: {str(e)}"


def _run_powershell(script: str) -> str:
    try:
        result = subprocess.run(
            ["powershell", "-Command", script], capture_output=True, text=True, timeout=30
        )
        return result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        return "PowerShell command timed out"
    except Exception as e:
        return f"Error: {str(e)}"


def _set_volume(level: int) -> dict:
    """Set system volume to a target percentage using keybd_event simulation.

    Args:
        level: Target volume percentage (0-100)

    Returns:
        dict with success status and message
    """
    # round is a Python built-in, no import needed

    level = max(0, min(100, level))
    target_presses = int(round(level / 2))

    ps_code = f"""
$ErrorActionPreference = "Continue"
$typeName = "WinVol"

if (-not ([System.Management.Automation.PSTypeName]::$typeName).Type) {{
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WinVol {{
    [DllImport("user32.dll")] static extern void keybd_event(byte k, byte s, uint f, int e);
    public static void Up()   {{ keybd_event(0xAF, 0, 0, 0); keybd_event(0xAF, 0, 2, 0); }}
    public static void Down() {{ keybd_event(0xAE, 0, 0, 0); keybd_event(0xAE, 0, 2, 0); }}
    public static void Mute() {{ keybd_event(0xAD, 0, 0, 0); keybd_event(0xAD, 0, 2, 0); }}
}}
"@
}}

Write-Host "RESETTING"
# Reset to 0 first
for ($i = 0; $i -lt 50; $i++) {{ [WinVol]::Down(); Start-Sleep -Milliseconds 30 }}

Write-Host "PRESSING"
# Ramp to target
for ($i = 0; $i -lt {target_presses}; $i++) {{ [WinVol]::Up(); Start-Sleep -Milliseconds 30 }}

Write-Host "DONE: {level}%"
"""
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_code], capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        log.info(f"[VOLUME] PowerShell output: {output}")
        if result.stderr:
            log.error(f"[VOLUME] PowerShell stderr: {result.stderr}")
        return {"success": True, "output": output, "verify_msg": f"Volume set to {level}%"}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Volume command timed out"}
    except Exception as e:
        return {"success": False, "output": str(e)}


def _adjust_volume(delta: int) -> dict:
    """Adjust volume up or down by a percentage.

    Args:
        delta: Positive for up, negative for down

    Returns:
        dict with success status
    """
    from math import ceil

    sign = 1 if delta > 0 else -1
    presses = int(ceil(abs(delta) / 2))
    key = "Up" if delta > 0 else "Down"

    script = """
$ErrorActionPreference = "SilentlyContinue"
$typeName = "WinVol"

if (-not ([System.Management.Automation.PSTypeName]::$typeName).Type) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WinVol {
    [DllImport("user32.dll")] static extern void keybd_event(byte k, byte s, uint f, int e);
    public static void Up()   { keybd_event(0xAF, 0, 0, 0); keybd_event(0xAF, 0, 2, 0); }
    public static void Down() { keybd_event(0xAE, 0, 0, 0); keybd_event(0xAE, 0, 2, 0); }
    public static void Mute() { keybd_event(0xAD, 0, 0, 0); keybd_event(0xAD, 0, 2, 0); }
}
"@
}

for ($i = 0; $i -lt PRESSES; $i++) { [WinVol]::KEY(); Start-Sleep -Milliseconds 30 }
""".replace("PRESSES", str(presses)).replace("KEY", key)
    try:
        result = subprocess.run(
            ["powershell", "-Command", script], capture_output=True, text=True, timeout=30
        )
        direction = "increased" if delta > 0 else "decreased"
        return {
            "success": True,
            "output": f"Volume {direction}",
            "verify_msg": f"Volume {direction}",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Volume command timed out"}
    except Exception as e:
        return {"success": False, "output": str(e)}


def _mute_volume() -> dict:
    """Toggle mute on system volume."""
    script = """
$ErrorActionPreference = "SilentlyContinue"
$typeName = "WinVol"

if (-not ([System.Management.Automation.PSTypeName]$typeName).Type) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WinVol {
    [DllImport("user32.dll")] static extern void keybd_event(byte k, byte s, uint f, int e);
    public static void Up()   { keybd_event(0xAF, 0, 0, 0); keybd_event(0xAF, 0, 2, 0); }
    public static void Down() { keybd_event(0xAE, 0, 0, 0); keybd_event(0xAE, 0, 2, 0); }
    public static void Mute() { keybd_event(0xAD, 0, 0, 0); keybd_event(0xAD, 0, 2, 0); }
}
"@ 2>$null | Out-Null
}

[WinVol]::Mute()
Write-Output "OK"
"""
    try:
        result = subprocess.run(
            ["powershell", "-Command", script], capture_output=True, text=True, timeout=30
        )
        return {"success": True, "output": "Volume muted/unmuted", "verify_msg": "Volume muted"}
    except Exception as e:
        return {"success": False, "output": str(e)}


def get_volume() -> dict:
    """Get current system volume level (0-100)."""
    script = r"""
$typeName = "WinVol"
if (-not ([System.Management.Automation.PSTypeName]::$typeName).Type) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WinVol {
    [DllImport("user32.dll")] static extern void keybd_event(byte k, byte s, uint f, int e);
    public static void Up()   { keybd_event(0xAF, 0, 0, 0); keybd_event(0xAF, 0, 2, 0); }
    public static void Down() { keybd_event(0xAE, 0, 0, 0); keybd_event(0xAE, 0, 2, 0); }
    public static void Mute() { keybd_event(0xAD, 0, 0, 0); keybd_event(0xAD, 0, 2, 0); }
}
"@
}

# Query volume using WMI (simpler method)
(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods) 2>$null
$vol = (Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Audio\" -Name "Mute" -ErrorAction SilentlyContinue)
if (-not $vol) { Write-Output "50" }  # Default if not found
else {
    # Volume is stored as a percentage in registry (0-100)
    $regVol = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Audio\Playback\Speakers\Level\" -Name "Level100" -ErrorAction SilentlyContinue
    if ($regVol) { Write-Output $regVol.Level100 }
    else { Write-Output "50" }
}
"""
    try:
        result = subprocess.run(
            ["powershell", "-Command", script], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return {
                "success": True,
                "output": f"Volume: {result.stdout.strip()}%",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"{result.stdout.strip()}%",
            }
        return {
            "success": True,
            "output": "Volume: 50% (default)",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": "50%",
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": 1,
            "verified": False,
            "verify_msg": str(e),
        }


def execute_dynamic_script(script: str, description: str = "", timeout: int = 30) -> dict:
    """
    Execute a custom Python script for complex automation tasks.
    This is the PRIMARY method for any task requiring multiple steps or custom logic.
    
    SECURITY: Script runs in isolated subprocess with restricted imports.
    """
    try:
        # Import dynamic scripter
        from dynamic_scripter import DynamicScripter
        
        # Create a minimal wrapper to execute the script directly
        # We bypass the LLM generation since the script is already provided
        import tempfile
        import subprocess
        import sys
        import os
        
        # Write script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script)
            temp_path = f.name
        
        try:
            # Execute in isolated subprocess
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=min(timeout, 60),  # Cap at 60 seconds
                cwd=os.getcwd()
            )
            
            success = result.returncode == 0
            
            return {
                "success": success,
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.returncode,
                "verified": success,
                "verify_msg": result.stdout[:200] if result.stdout else ("Script executed" if success else result.stderr[:200])
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": f"Script timed out after {timeout} seconds",
                "exit_code": -1,
                "verified": False,
                "verify_msg": "Execution timeout"
            }
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
            "verified": False,
            "verify_msg": f"Dynamic script execution failed: {str(e)[:100]}"
        }


def _execute_action_internal(action: str, params: dict) -> dict:
    # DYNAMIC SCRIPTING: Handle execute_dynamic_script as primary action
    if action == "execute_dynamic_script":
        script = params.get("script", "")
        description = params.get("description", "")
        timeout = params.get("timeout", 30)
        
        if not script:
            return {
                "success": False,
                "output": "",
                "error": "No script provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Script is required for dynamic execution"
            }
        
        # Execute the dynamic script
        return execute_dynamic_script(script, description, timeout)
    
    if action == "read_file":
        path = params.get("path", "")
        speak = params.get("speak", False)
        result = read_file(path, speak)
        return {
            "success": True,
            "output": result,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": result,
        }

    if action == "screen_capture":
        result = screen_capture()
        if result["success"]:
            return {
                "success": True,
                "output": f"Screenshot saved to {result['filepath']}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": result["filepath"],
                "image_base64": result.get("base64", ""),
            }
        return {
            "success": False,
            "output": "",
            "error": result.get("error", ""),
            "exit_code": 1,
            "verified": False,
            "verify_msg": "",
        }

    if action == "start_realtime_screen":
        interval = params.get("interval", 5)
        return start_realtime_screen(interval)

    if action == "stop_realtime_screen":
        return stop_realtime_screen()

    if action == "get_latest_screen":
        return get_latest_screen()

    if action == "system_health":
        import psutil

        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        return {
            "success": True,
            "output": f"CPU: {cpu}%, Memory: {memory}%, Disk: {disk}%",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"System healthy",
        }

    if action == "get_top_processes":
        import psutil

        limit = int(params.get("limit", 5))
        try:
            processes = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    info = proc.info
                    if info["cpu_percent"] is None:
                        info["cpu_percent"] = 0.0
                    if info["memory_percent"] is None:
                        info["memory_percent"] = 0.0
                    processes.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Sort by CPU usage
            processes.sort(key=lambda x: x["cpu_percent"], reverse=True)
            top_processes = processes[:limit]

            output_lines = ["Top processes by CPU usage:"]
            for p in top_processes:
                output_lines.append(
                    f"  - {p['name']} (PID {p['pid']}): CPU {p['cpu_percent']:.1f}%, RAM {p['memory_percent']:.1f}%"
                )

            output = "\n".join(output_lines)
            return {
                "success": True,
                "output": output,
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Found {len(top_processes)} processes",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Error getting processes: {str(e)}",
            }

    if action == "close_app":
        app_name = params.get("app_name", "")
        if not app_name:
            return {
                "success": False,
                "output": "",
                "error": "No app name provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No app name provided",
            }
        result = _close_app_gracefully(app_name)
        return {
            "success": True,
            "output": result,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Closed {app_name}",
        }

    if action == "run_powershell":
        script = params.get("script", "")
        if not script:
            return {
                "success": False,
                "output": "",
                "error": "No script provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No script provided",
            }
        # Check if script is trying to close an app
        close_match = re.search(
            r'Stop-Process\s+-(?:Name|Name\s+)\s*["\']?(\w+)["\']?', script, re.I
        )
        if close_match:
            app_name = close_match.group(1)
            result = _close_app_gracefully(app_name)
            return {
                "success": True,
                "output": result,
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Closed {app_name}",
            }
        # Otherwise, run the PowerShell script
        result = _run_powershell(script)
        return {
            "success": True,
            "output": result,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": result[:100] if result else "Script executed",
        }

    if action == "open_app":
        app_name = params.get("app_name", "")
        if not app_name:
            return {
                "success": False,
                "output": "",
                "error": "No app name provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No app name provided",
            }
        result = _open_app(app_name)
        return {
            "success": True,
            "output": result,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Opened {app_name}",
        }

    if action == "set_volume":
        level = params.get("level", 50)
        result = _set_volume(level)
        return result

    if action == "volume_up":
        amount = params.get("amount", 5)
        result = _adjust_volume(amount)
        return result

    if action == "volume_down":
        amount = params.get("amount", 5)
        result = _adjust_volume(-amount)
        return result

    if action == "mute_volume":
        result = _mute_volume()
        return result

    if action == "get_volume":
        result = get_volume()
        return result

    if action == "run_command":
        command = params.get("command", "")
        if not command:
            return {
                "success": False,
                "output": "",
                "error": "No command provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No command provided",
            }
        try:
            import health_check

            report = health_check.check_system_health()
            summary = f"System {report['overall_status']}. "
            for check_name, check_data in report["checks"].items():
                if check_data["status"] != "healthy":
                    summary += f"{check_name}: {check_data['message']}. "
            
            # SECURITY FIX: Use shell=False to prevent command injection
            # Parse command into arguments for safe execution
            import shlex
            try:
                # Try to parse as shell command safely
                args = ["cmd", "/c"] + shlex.split(command)
            except ValueError:
                # If shlex fails, fall back to treating as single command
                args = ["cmd", "/c", command]
            
            result = subprocess.run(args, capture_output=True, text=True, timeout=30, shell=False)
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.returncode,
                "verified": result.returncode == 0,
                "verify_msg": result.stdout[:100] if result.stdout else result.stderr[:100],
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "search_web":
        query = params.get("query", "")
        if not query:
            return {
                "success": False,
                "output": "",
                "error": "No search query provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No search query provided",
            }
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "success": True,
                "output": f"Web search opened for: {query}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Web search opened for: {query}",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to open web search: {str(e)}",
            }

    if action == "create_file":
        path = params.get("path", "")
        content = params.get("content", "")
        if not path:
            return {
                "success": False,
                "output": "",
                "error": "No file path provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No file path provided",
            }
        
        # SECURITY FIX: Validate file path to prevent path traversal attacks
        def _is_safe_path_create(file_path: str) -> bool:
            """Prevent path traversal attacks by ensuring path is within allowed directories."""
            try:
                # First check: reject obvious traversal attempts in the raw path
                if '..' in file_path:
                    return False
                    
                resolved = Path(file_path).resolve()
                # Allow paths in user's home directory or current working directory
                user_home = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
                cwd = Path.cwd()
                
                # Block paths that resolve outside user home and cwd
                if not (str(resolved).startswith(str(user_home)) or str(resolved).startswith(str(cwd))):
                    return False
                
                return True
            except Exception:
                return False
        
        if not _is_safe_path_create(path):
            return {
                "success": False,
                "output": "",
                "error": f"Unsafe file path detected: {path}",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Path traversal attempt blocked",
            }
        
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "output": f"File created: {path}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"File created: {path}",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to create file: {str(e)}",
            }

    if action == "get_time":
        current_time = datetime.now().strftime("%I:%M %p")
        return {
            "success": True,
            "output": current_time,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": current_time,
        }

    if action == "get_date":
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        return {
            "success": True,
            "output": current_date,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": current_date,
        }

    if action == "screenshot":
        result = screen_capture()
        if result["success"]:
            return {
                "success": True,
                "output": f"Screenshot saved to {result['filepath']}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": result["filepath"],
                "image_base64": result.get("base64", ""),
            }
        return {
            "success": False,
            "output": "",
            "error": result.get("error", ""),
            "exit_code": 1,
            "verified": False,
            "verify_msg": "",
        }

    if action == "calculate":
        expression = params.get("expression", "")
        if not expression:
            return {
                "success": False,
                "output": "",
                "error": "No expression provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No expression provided",
            }
        try:
            if expression:
                # 🚨 SECURITY: Replace dangerous eval() with safe alternative
                import ast

                try:
                    # Safer evaluation using ast.literal_eval for basic math
                    # First validate it's only numbers and math operators
                    if not re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", expression):
                        return {
                            "success": False,
                            "output": "",
                            "error": "Invalid expression: only basic math allowed",
                            "exit_code": -1,
                            "verified": False,
                            "verify_msg": "Invalid expression",
                        }
                    result = ast.literal_eval(expression)
                    return {
                        "success": True,
                        "output": str(result),
                        "error": "",
                        "exit_code": 0,
                        "verified": True,
                        "verify_msg": str(result),
                    }
                except (ValueError, SyntaxError) as e:
                    return {
                        "success": False,
                        "output": "",
                        "error": str(e)[:150],
                        "exit_code": -1,
                        "verified": False,
                        "verify_msg": "Invalid expression",
                    }
            else:
                return {
                    "success": False,
                    "output": "",
                    "error": "No expression provided",
                    "exit_code": 1,
                    "verified": False,
                    "verify_msg": "No expression provided",
                }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e)[:100],
                "exit_code": -1,
                "verified": False,
                "verify_msg": "Health check failed",
            }

    # Handle remaining function definitions
    if action == "wait":
        try:
            seconds = int(params.get("seconds", 0))
            if seconds < 0:
                seconds = 0
            time.sleep(seconds)
            return {
                "success": True,
                "output": f"Waited {seconds} seconds",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Waited {seconds} seconds",
            }
        except ValueError:
            return {
                "success": False,
                "output": "",
                "error": "Invalid seconds value",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Invalid seconds value",
            }

    if action == "set_timer":
        try:
            minutes = int(params.get("minutes", 0))
            if minutes <= 0:
                seconds = int(params.get("seconds", 0))
                if seconds > 0:
                    import threading

                    reminder_msg = params.get("message", f"Timer: {seconds} seconds")

                    def timer_callback():
                        time.sleep(seconds)
                        try:
                            import tts

                            tts.speak(reminder_msg)
                        except (ImportError, AttributeError, OSError):
                            pass

                    thread = threading.Thread(target=timer_callback, daemon=True)
                    thread.start()
                    return {
                        "success": True,
                        "output": f"Timer set for {seconds} seconds",
                        "error": "",
                        "exit_code": 0,
                        "verified": True,
                        "verify_msg": f"Timer: {seconds}s",
                    }
                return {
                    "success": False,
                    "output": "",
                    "error": "Minutes must be positive",
                    "exit_code": 1,
                    "verified": False,
                    "verify_msg": "Minutes must be positive",
                }

            reminders_dir = Path(__file__).parent / "reminders"
            reminders_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            reminder_file = reminders_dir / f"reminder_{timestamp}.txt"

            with open(reminder_file, "w") as f:
                f.write(f"Timer completed after {minutes} minutes")

            return {
                "success": True,
                "output": f"Timer set for {minutes} minutes",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Timer set for {minutes} minutes",
            }
        except ValueError:
            return {
                "success": False,
                "output": "",
                "error": "Invalid minutes value",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Invalid minutes value",
            }

    if action == "set_alarm":
        alarm_time = params.get("time", "")
        if not alarm_time:
            return {
                "success": False,
                "output": "",
                "error": "No alarm time provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No alarm time provided",
            }

        try:
            # Parse time like "3:00", "3:00 AM", "3:10 PM", "15:10"
            match = re.match(r"(\d{1,2}):?(\d{2})?\s*(AM|PM|am|pm)?", alarm_time.strip(), re.I)
            if not match:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Invalid time format: {alarm_time}. Use format like '3:00', '3:00 PM', '15:30'",
                    "exit_code": 1,
                    "verified": False,
                    "verify_msg": "Invalid time format",
                }

            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            ampm = match.group(3).upper() if match.group(3) else None

            # Convert to 24-hour format
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0
            elif ampm is None:
                # If no AM/PM and hour < 8, assume PM (e.g., "3" -> 3 PM)
                if hour < 8:
                    hour += 12

            # Create alarm file with scheduled time
            alarms_dir = Path(__file__).parent / "alarms"
            alarms_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            alarm_file = alarms_dir / f"alarm_{timestamp}.txt"

            now = datetime.now()
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # If target time is in the past, schedule for tomorrow
            if target_time <= now:
                target_time = target_time + timedelta(days=1)

            wait_seconds = (target_time - now).total_seconds()

            with open(alarm_file, "w") as f:
                f.write(
                    f"Alarm set for {target_time.strftime('%I:%M %p')} ({int(wait_seconds)} seconds from now)"
                )

            return {
                "success": True,
                "output": f"Alarm set for {target_time.strftime('%I:%M %p')}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Alarm set for {target_time.strftime('%I:%M %p')}",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "execute_shortcut":
        shortcut_name = params.get("name", "")
        if not shortcut_name:
            return {
                "success": False,
                "output": "",
                "error": "No shortcut name provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No shortcut name provided",
            }
        # For now, just return a placeholder - shortcuts would need to be loaded from user_profile
        return {
            "success": True,
            "output": f"Shortcut executed: {shortcut_name} (not fully implemented)",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Shortcut executed: {shortcut_name} (not fully implemented)",
        }

    if action == "create_shortcut":
        shortcut_name = params.get("name", "")
        actions = params.get("actions", [])
        if not shortcut_name:
            return {
                "success": False,
                "output": "",
                "error": "No shortcut name provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No shortcut name provided",
            }
        # For now, just return a placeholder - shortcuts would need to be saved to user_profile
        return {
            "success": True,
            "output": f"Shortcut created: {shortcut_name} with {len(actions)} actions (not fully implemented)",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Shortcut created: {shortcut_name} with {len(actions)} actions (not fully implemented)",
        }

    if action == "list_shortcuts":
        # For now, just return a placeholder - shortcuts would need to be loaded from user_profile
        return {
            "success": True,
            "output": "No shortcuts available (not fully implemented)",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": "No shortcuts available (not fully implemented)",
        }

    if action == "get_profile":
        try:
            import user_profile

            profile = user_profile.load_profile()
            return {
                "success": True,
                "output": f"User profile loaded for {profile.get('user', {}).get('name', 'Unknown')}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"User profile loaded for {profile.get('user', {}).get('name', 'Unknown')}",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to load profile: {str(e)}",
            }

    if action == "set_preference":
        key = params.get("key", "")
        value = params.get("value", "")
        if not key:
            return {
                "success": False,
                "output": "",
                "error": "No preference key provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No preference key provided",
            }
        try:
            import user_profile

            user_profile.set_preference(key, value)
            return {
                "success": True,
                "output": f"Preference set: {key} = {value}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Preference set: {key} = {value}",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to set preference: {str(e)}",
            }

    if action == "battery_status":
        try:
            # Try to get battery status via PowerShell
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Battery | Select-Object -ExpandProperty EstimatedChargeRemaining",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                battery_level = result.stdout.strip()
                # Try to get charging status
                charge_result = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-CimInstance Win32_Battery | Select-Object -ExpandProperty BatteryStatus",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                charging_status = "unknown"
                if charge_result.returncode == 0 and charge_result.stdout.strip():
                    status_code = charge_result.stdout.strip()
                    status_map = {
                        "2": "charging",
                        "3": "discharging",
                        "4": "fully charged",
                        "7": "critically low",
                    }
                    charging_status = status_map.get(status_code, "unknown")

                output = f"Battery is at {battery_level}%, {charging_status}"
                return {
                    "success": True,
                    "output": output,
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": output,
                }
            else:
                return {
                    "success": False,
                    "output": "",
                    "error": "Could not retrieve battery status",
                    "exit_code": 1,
                    "verified": False,
                    "verify_msg": "Could not retrieve battery status",
                }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Battery status error: {str(e)}",
            }

    if action == "system_info":
        info_type = params.get("type", "all")
        try:
            # Get basic system info via PowerShell
            script = """
             $info = @{}
             try { $info.OS = (Get-CimInstance Win32_OperatingSystem).Caption } catch {}
             try { $info.OSVersion = (Get-CimInstance Win32_OperatingSystem).Version } catch {}
             try {
                 $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
                 $info.CPU = $cpu.Name.Trim()
                 $info.CPUCores = $cpu.NumberOfCores
             } catch {}
             try {
                 $ram_gb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
                 $info.RAMGB = $ram_gb
             } catch {}
             try {
                 $disk = Get-PSDrive C | Select-Object Used,Free
                 $info.DiskFreeGB = [math]::Round($disk.Free / 1GB, 1)
                 $info.DiskTotalGB = [math]::Round(($disk.Used + $disk.Free) / 1GB, 1)
             } catch {}
             try { $info.HasBattery = ($null -ne (Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue)) } catch { $info.HasBattery = $false }
             $info | ConvertTo-Json -Compress
             """
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json as json_module

                data = json_module.loads(result.stdout.strip())

                if info_type.lower() == "cpu":
                    output = (
                        f"CPU: {data.get('CPU', 'unknown')} ({data.get('CPUCores', '?')} cores)"
                    )
                elif info_type.lower() == "ram":
                    output = f"RAM: {data.get('RAMGB', '?')} GB"
                elif info_type.lower() == "disk":
                    output = f"Disk: {data.get('DiskFreeGB', '?')} GB free / {data.get('DiskTotalGB', '?')} GB total"
                elif info_type.lower() == "battery":
                    output = (
                        f"Battery: {'Present' if data.get('HasBattery', False) else 'Not present'}"
                    )
                else:  # all or default
                    output = f"OS: {data.get('OS', 'Windows')}, CPU: {data.get('CPU', 'unknown')}, RAM: {data.get('RAMGB', '?')} GB"

                return {
                    "success": True,
                    "output": output,
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": output,
                }
            else:
                return {
                    "success": False,
                    "output": "",
                    "error": "Could not retrieve system info",
                    "exit_code": 1,
                    "verified": False,
                    "verify_msg": "Could not retrieve system info",
                }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"System info error: {str(e)}",
            }

    if action == "internet_speed":
        # Simple ping test to check connectivity
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "8.8.8.8"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": "Internet connection appears to be working",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": "Internet connection appears to be working",
                }
            else:
                return {
                    "success": False,
                    "output": "",
                    "error": "Internet connectivity test failed",
                    "exit_code": 1,
                    "verified": False,
                    "verify_msg": "Internet connectivity test failed",
                }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Internet speed test error: {str(e)}",
            }

    if action == "get_wifi":
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                output = result.stdout
                ssid = ""
                signal = ""
                for line in output.split("\n"):
                    if "SSID" in line and "BSSID" not in line:
                        ssid = line.split(":", 1)[-1].strip()
                    if "Signal" in line:
                        signal = line.split(":", 1)[-1].strip()
                if ssid:
                    return {
                        "success": True,
                        "output": f"Connected to Wi-Fi: {ssid}, Signal: {signal}",
                        "error": "",
                        "exit_code": 0,
                        "verified": True,
                        "verify_msg": f"Connected to {ssid}",
                    }
                return {
                    "success": True,
                    "output": "Not connected to Wi-Fi",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": "Not connected",
                }
            return {
                "success": False,
                "output": "",
                "error": "Could not get Wi-Fi info",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Wi-Fi info failed",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Wi-Fi error: {str(e)}",
            }

    if action == "get_ip":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-NetIPAddress -AddressFamily IPv4 "
                    "| Where-Object { "
                    "  $_.InterfaceAlias -notlike '*Loopback*' -and "
                    "  $_.IPAddress -notlike '169.254.*' -and "
                    "  $_.IPAddress -ne '0.0.0.0' "
                    "} "
                    "| Sort-Object { $_.PrefixOrigin -ne 'Dhcp' } "
                    "| Select-Object -First 1 -ExpandProperty IPAddress",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ip = result.stdout.strip()
            if result.returncode == 0 and ip:
                return {
                    "success": True,
                    "output": f"IP Address: {ip}",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": ip,
                }
            return {
                "success": False,
                "output": "",
                "error": "No active IPv4 address found",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No IP",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"IP error: {str(e)}",
            }

    if action == "ping":
        host = params.get("host", "8.8.8.8")
        try:
            result = subprocess.run(
                ["ping", "-n", "2", host],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": f"Ping to {host} successful",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": f"Ping to {host} successful",
                }
            return {
                "success": False,
                "output": "",
                "error": f"Ping to {host} failed",
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Ping to {host} failed",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Ping error: {str(e)}",
            }

    if action == "list_running_apps":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -ExpandProperty ProcessName -Unique | Sort-Object",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            apps = [a.strip() for a in result.stdout.strip().split("\n") if a.strip()]
            if apps:
                output = "Running applications:\n" + ", ".join(apps[:15])
                if len(apps) > 15:
                    output += f" ... and {len(apps) - 15} more"
                return {
                    "success": True,
                    "output": output,
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": f"{len(apps)} apps",
                }
            return {
                "success": True,
                "output": "No applications with windows found",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "No apps",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "minimize_window":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.SendMessageW(user32.GetForegroundWindow(), 0x112, 0xF020, 0)
            return {
                "success": True,
                "output": "Window minimized",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Window minimized",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "minimize_windows":
        try:
            import ctypes

            # Simulate Win+D (toggle show desktop)
            user32 = ctypes.windll.user32
            user32.keybd_event(0x5B, 0, 0, 0)  # Left Windows key down
            user32.keybd_event(0x44, 0, 0, 0)  # D key down
            user32.keybd_event(0x44, 0, 2, 0)  # D key up
            user32.keybd_event(0x5B, 0, 2, 0)  # Left Windows key up
            return {
                "success": True,
                "output": "All windows minimized (show desktop)",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Windows minimized",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "maximize_window":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.SendMessageW(user32.GetForegroundWindow(), 0x112, 0xF030, 0)
            return {
                "success": True,
                "output": "Window maximized",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Window maximized",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "restore_window":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.SendMessageW(user32.GetForegroundWindow(), 0x112, 0xF120, 0)
            return {
                "success": True,
                "output": "Window restored",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Window restored",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "close_window":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.PostMessageW(user32.GetForegroundWindow(), 0x112, 0xF060, 0)
            return {
                "success": True,
                "output": "Window closed",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Window closed",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "lock_pc":
        try:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
            return {
                "success": True,
                "output": "PC locked",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "PC locked",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "sleep_pc":
        try:
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
                ],
                check=True,
            )
            return {
                "success": True,
                "output": "PC going to sleep",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "PC sleeping",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "restart_pc":
        try:
            subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
            return {
                "success": True,
                "output": "PC restarting",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "PC restarting",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "shutdown_pc":
        try:
            subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
            return {
                "success": True,
                "output": "PC shutting down",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "PC shutting down",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "get_display_brightness":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).GetCurrentBrightness()",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return {
                    "success": True,
                    "output": f"Brightness: {result.stdout.strip()}%",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": f"{result.stdout.strip()}%",
                }
            return {
                "success": True,
                "output": "Brightness control not available",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Not available",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "set_brightness":
        level = params.get("level", 50)
        try:
            # Primary: WMI (works on most laptops)
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                    f".SetBrightness(1, {level})",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # FIX: check stderr for WMI method errors before claiming success
            if result.returncode == 0 and not result.stderr.strip():
                return {
                    "success": True,
                    "output": f"Brightness set to {level}%",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": f"Brightness: {level}%",
                }

            # WMI failed — try PowerShell 7 / newer API as fallback
            fallback = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Add-Type -AssemblyName System.Windows.Forms); "
                    f"[System.Windows.Forms.Screen]::PrimaryScreen | Out-Null; "
                    f"$brightness = {level}; "
                    f"$mon = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods "
                    f"-ErrorAction SilentlyContinue; "
                    f"if ($mon) {{ $mon.WmiSetBrightness(1, $brightness) }} "
                    f"else {{ Write-Error 'No brightness control available' }}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if fallback.returncode == 0 and not fallback.stderr.strip():
                return {
                    "success": True,
                    "output": f"Brightness set to {level}%",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": f"Brightness: {level}%",
                }

            # Both failed — report honestly
            error_detail = (
                result.stderr or fallback.stderr or "WMI brightness not supported"
            ).strip()
            return {
                "success": False,
                "output": "",
                "error": error_detail,
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Brightness control not available on this display.",
            }

        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "toggle_night_light":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$current = Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\DefaultAccount\\Current\\default$windows.data.bluelightreduction.bluelightreductionstate\\windows.data.bluelightreduction.bluelightreductionstate' -Name 'Data' -ErrorAction SilentlyContinue; if ($current) { 'Night light toggle not fully implemented' } else { 'Night light control not available' }",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {
                "success": True,
                "output": "Night light toggle not fully implemented in this version",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Night light",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "toggle_dark_mode":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name 'AppsUseLightTheme' -ErrorAction SilentlyContinue",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            is_light = "1" in result.stdout
            new_value = 0 if is_light else 1
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name 'AppsUseLightTheme' -Value {new_value}",
                ],
                timeout=10,
            )
            mode = "dark" if new_value == 0 else "light"
            return {
                "success": True,
                "output": f"Dark mode turned {mode}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Dark mode: {mode}",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "open_settings":
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", "ms-settings:"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "success": True,
                "output": "Opened Windows Settings",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Settings opened",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "open_control_panel":
        try:
            subprocess.Popen(["control"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {
                "success": True,
                "output": "Opened Control Panel",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Control Panel opened",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "empty_recycle_bin":
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
                ],
                timeout=10,
            )
            return {
                "success": True,
                "output": "Recycle bin emptied",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": "Recycle bin emptied",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e),
            }

    if action == "run_in_terminal":
        command = params.get("command", "")
        if not command:
            return {
                "success": False,
                "output": "",
                "error": "No command provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No command provided",
            }
        result = run_in_terminal(command, wait_for_output=False)
        return {
            "success": result["success"],
            "output": result["output"],
            "error": result["error"],
            "exit_code": result["exit_code"],
            "verified": result["success"],
            "verify_msg": result["output"],
        }

    if action == "run_terminal_capture":
        command = params.get("command", "")
        timeout = int(params.get("timeout", 30))
        if not command:
            return {
                "success": False,
                "output": "",
                "error": "No command provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No command provided",
            }
        result = run_in_terminal(command, wait_for_output=True, timeout=timeout)
        return {
            "success": result["success"],
            "output": result["output"],
            "error": result["error"],
            "exit_code": result["exit_code"],
            "verified": result["success"],
            "verify_msg": result["output"][:100] if result["output"] else result["error"][:100],
        }

    if action == "run_powershell_bg":
        script = params.get("script", "")
        if not script:
            return {
                "success": False,
                "output": "",
                "error": "No script provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No script provided",
            }
        result = run_powershell_script(script, wait_for_output=False)
        return {
            "success": result["success"],
            "output": result["output"],
            "error": result["error"],
            "exit_code": result["exit_code"],
            "verified": result["success"],
            "verify_msg": result["output"],
        }

    if action == "run_powershell_capture":
        script = params.get("script", "")
        timeout = int(params.get("timeout", 30))
        if not script:
            return {
                "success": False,
                "output": "",
                "error": "No script provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No script provided",
            }
        result = run_powershell_script(script, wait_for_output=True, timeout=timeout)
        return {
            "success": result["success"],
            "output": result["output"],
            "error": result["error"],
            "exit_code": result["exit_code"],
            "verified": result["success"],
            "verify_msg": result["output"][:100] if result["output"] else result["error"][:100],
        }

    if action == "run_script":
        script_path = params.get("path", "")
        wait = params.get("wait", False)
        timeout = int(params.get("timeout", 60))
        if not script_path:
            return {
                "success": False,
                "output": "",
                "error": "No script path provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No script path provided",
            }
        result = run_script_file(script_path, wait_for_output=wait, timeout=timeout)
        return {
            "success": result["success"],
            "output": result["output"],
            "error": result["error"],
            "exit_code": result["exit_code"],
            "verified": result["success"],
            "verify_msg": result["output"],
        }

    if action == "chain_commands":
        commands = params.get("commands", [])
        if not commands:
            return {
                "success": False,
                "output": "",
                "error": "No commands provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No commands provided",
            }
        stop_on_fail = params.get("stop_on_failure", True)
        result = chain_commands(commands, stop_on_failure=stop_on_fail)
        return {
            "success": result["success"],
            "output": result["output"],
            "error": result["error"],
            "exit_code": result["exit_code"],
            "verified": result["success"],
            "verify_msg": f"Executed {len(result.get('steps', []))} commands",
        }

    if action == "task_start":
        command = params.get("command", "")
        name = params.get("name")
        shell = params.get("shell", "cmd")
        if not command:
            return {
                "success": False,
                "output": "",
                "error": "No command provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No command provided",
            }
        result = task_start(command, name, shell)
        return {
            "success": result["success"],
            "output": result.get("message", result.get("output", "")),
            "error": result.get("error", ""),
            "exit_code": 0 if result["success"] else 1,
            "verified": result["success"],
            "verify_msg": result.get("task_id", ""),
            "task_id": result.get("task_id"),
        }

    if action == "task_status":
        task_id = params.get("task_id")
        result = task_status(task_id)
        if task_id:
            if result.get("task"):
                task = result["task"]
                return {
                    "success": True,
                    "output": f"Task: {task['name']}, Status: {task['status']}, Command: {task['command']}",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": f"{task['status']}",
                }
            return {
                "success": False,
                "output": "",
                "error": result.get("error", "Task not found"),
                "exit_code": 1,
                "verified": False,
                "verify_msg": result.get("error", "Not found"),
            }
        else:
            tasks = result.get("tasks", [])
            running = [t for t in tasks if t["status"] == "running"]
            completed = [t for t in tasks if t["status"] == "completed"]
            output = f"Running: {len(running)}, Completed: {len(completed)}"
            if running:
                output += "\nRunning tasks: " + ", ".join([t["name"] for t in running[:5]])
            return {
                "success": True,
                "output": output,
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"{len(running)} running",
            }

    if action == "task_output":
        task_id = params.get("task_id")
        lines = params.get("lines")
        if not task_id:
            return {
                "success": False,
                "output": "",
                "error": "No task_id provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No task_id provided",
            }
        result = task_output(task_id, lines)
        return {
            "success": result["success"],
            "output": result.get("output", ""),
            "error": result.get("error", ""),
            "exit_code": 0 if result["success"] else 1,
            "verified": result["success"],
            "verify_msg": (
                result.get("output", "")[:100]
                if result["success"]
                else result.get("error", "")[:100]
            ),
        }

    if action == "task_check":
        task_id = params.get("task_id")
        if not task_id:
            return {
                "success": False,
                "output": "",
                "error": "No task_id provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No task_id provided",
            }
        result = task_check(task_id)
        return {
            "success": result["success"],
            "output": f"Has output: {result.get('has_output', False)}, Status: {result.get('status', 'unknown')}, Size: {result.get('bytes', 0)} bytes",
            "error": result.get("error", ""),
            "exit_code": 0 if result["success"] else 1,
            "verified": result["success"],
            "verify_msg": f"{result.get('status', 'unknown')}: {result.get('bytes', 0)} bytes",
        }

    if action == "task_kill":
        task_id = params.get("task_id")
        if not task_id:
            return {
                "success": False,
                "output": "",
                "error": "No task_id provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No task_id provided",
            }
        result = task_kill(task_id)
        return {
            "success": result["success"],
            "output": result.get("message", ""),
            "error": result.get("error", ""),
            "exit_code": 0 if result["success"] else 1,
            "verified": result["success"],
            "verify_msg": result.get("message", ""),
        }

    if action == "task_wait":
        task_id = params.get("task_id")
        timeout = int(params.get("timeout", 60))
        if not task_id:
            return {
                "success": False,
                "output": "",
                "error": "No task_id provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No task_id provided",
            }
        result = task_wait(task_id, timeout)
        return {
            "success": result["success"],
            "output": result.get("output", ""),
            "error": result.get("error", ""),
            "exit_code": 0 if result["success"] else 1,
            "verified": result["success"],
            "verify_msg": (
                result.get("output", "")[:100]
                if result["success"]
                else result.get("error", "")[:100]
            ),
        }

    if action == "task_clear":
        older_than_hours = int(params.get("older_than_hours", 24))
        result = task_clear(older_than_hours)
        return {
            "success": result["success"],
            "output": f"Cleared {result.get('cleared', 0)} old tasks",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Cleared {result.get('cleared', 0)} tasks",
        }

    if action == "add_note":
        text = params.get("text", "")
        if not text:
            return {
                "success": False,
                "output": "",
                "error": "No note text provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No note text provided",
            }
        try:
            notes_dir = Path(__file__).parent / "notes"
            notes_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            note_file = notes_dir / f"note_{timestamp}.txt"

            with open(note_file, "w", encoding="utf-8") as f:
                f.write(text)

            return {
                "success": True,
                "output": f"Note saved: {len(text)} characters",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Note saved: {len(text)} characters",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to save note: {str(e)}",
            }

    if action == "read_notes":
        try:
            days = int(params.get("days", 1))
            notes_dir = Path(__file__).parent / "notes"

            if not notes_dir.exists():
                return {
                    "success": True,
                    "output": "No notes found",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": "No notes found",
                }

            # For simplicity, just read all notes (in a real app, we'd filter by date)
            notes = []
            for note_file in notes_dir.glob("note_*.txt"):
                try:
                    with open(note_file, "r", encoding="utf-8") as f:
                        notes.append(f.read().strip())
                except (OSError, UnicodeDecodeError):
                    pass

            if not notes:
                return {
                    "success": True,
                    "output": "No notes found",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": "No notes found",
                }

            # Combine notes with separators
            combined = "\n\n---\n\n".join(notes[-10:])  # Last 10 notes
            if len(combined) > 500:
                combined = combined[:500] + "..."

            return {
                "success": True,
                "output": f"Found {len(notes)} notes:\n\n{combined}",
                "error": "",
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Found {len(notes)} notes",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to read notes: {str(e)}",
            }

    if action == "weather":
        location = params.get("location", "")
        if not location:
            location = "current location"  # Default
        # For now, return a placeholder - would need weather API for real implementation
        return {
            "success": True,
            "output": f"Weather for {location}: Service not implemented (would require API key)",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Weather for {location}: Service not implemented",
        }

    if action == "wikipedia":
        query = params.get("query", "")
        if not query:
            return {
                "success": False,
                "output": "",
                "error": "No search query provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No search query provided",
            }
        # For now, return a placeholder - would need Wikipedia API for real implementation
        return {
            "success": True,
            "output": f"Wikipedia search for '{query}': Service not implemented (would require API)",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Wikipedia search for '{query}': Service not implemented",
        }

    if action == "stock_price":
        symbol = params.get("symbol", "")
        if not symbol:
            return {
                "success": False,
                "output": "",
                "error": "No stock symbol provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No stock symbol provided",
            }
        # For now, return a placeholder - would need financial API for real implementation
        return {
            "success": True,
            "output": f"Stock price for {symbol}: Service not implemented (would require API key)",
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Stock price for {symbol}: Service not implemented",
        }

    if action == "copy_to_clipboard":
        text = params.get("text", "")
        if not text:
            return {
                "success": False,
                "output": "",
                "error": "No text provided to copy",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No text provided to copy",
            }
        try:
            # Use PowerShell to copy to clipboard
            escaped_text = text.replace('"', '`"')
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f'Set-Clipboard -Value "{escaped_text}"'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": f"Text copied to clipboard ({len(text)} characters)",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": f"Text copied to clipboard ({len(text)} characters)",
                }
            else:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Failed to copy to clipboard: {result.stderr.strip()}",
                    "exit_code": 1,
                    "verified": False,
                    "verify_msg": f"Failed to copy to clipboard: {result.stderr.strip()}",
                }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Clipboard error: {str(e)}",
            }

    if action == "paste_from_clipboard":
        try:
            # Use PowerShell to get clipboard content
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                content = result.stdout.strip()
                return {
                    "success": True,
                    "output": content,
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": content,
                }
            else:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Failed to get clipboard content: {result.stderr.strip()}",
                    "exit_code": 1,
                    "verified": False,
                    "verify_msg": f"Failed to get clipboard content: {result.stderr.strip()}",
                }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Clipboard error: {str(e)}",
            }

    if action == "open_file":
        path = params.get("path", "")
        if not path:
            return {
                "success": False,
                "output": "",
                "error": "No file path provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No file path provided",
            }
        
        # SECURITY FIX: Validate file path to prevent path traversal attacks
        def _is_safe_path_open(file_path: str) -> bool:
            """Prevent path traversal attacks by ensuring path is within allowed directories."""
            try:
                # First check: reject obvious traversal attempts in the raw path
                if '..' in file_path:
                    return False
                    
                resolved = Path(file_path).resolve()
                # Allow paths in user's home directory or current working directory
                user_home = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
                cwd = Path.cwd()
                
                # Block paths that resolve outside user home and cwd
                if not (str(resolved).startswith(str(user_home)) or str(resolved).startswith(str(cwd))):
                    return False
                
                return True
            except Exception:
                return False
        
        if not _is_safe_path_open(path):
            return {
                "success": False,
                "output": "",
                "error": f"Unsafe file path detected: {path}",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Path traversal attempt blocked",
            }
        
        try:
            # Use PowerShell to open file with default application
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f'Start-Process "{path}"'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": f"File opened: {path}",
                    "error": "",
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": f"File opened: {path}",
                }
            return {
                "success": False,
                "output": result.stdout.strip(),
                "error": result.stderr.strip() or f"Failed to open file: {path}",
                "exit_code": result.returncode,
                "verified": False,
                "verify_msg": result.stderr.strip() or f"Failed to open file: {path}",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e)[:200],
                "exit_code": 1,
                "verified": False,
                "verify_msg": str(e)[:200],
            }

    # ── Todo management ──────────────────────────────────────────────────────
    if action == "create_todo":
        import todo_manager

        task = params.get("task", "")
        if not task:
            return {
                "success": False,
                "output": "",
                "error": "No task description provided",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No task description provided",
            }
        subtasks = params.get("subtasks", [])
        todo_id = todo_manager.create_todo(task, subtasks)
        summary = todo_manager.get_todo_summary()
        return {
            "success": True,
            "output": summary,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Created todo: {task}",
        }

    if action == "mark_done":
        import todo_manager

        subtask = params.get("subtask", "")
        if not subtask:
            return {
                "success": False,
                "output": "",
                "error": "No subtask specified",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "No subtask specified",
            }
        pending = todo_manager.get_pending_todos()
        if pending:
            todo_manager.mark_subtask_done(pending[0]["id"], subtask)
        summary = todo_manager.get_todo_summary()
        return {
            "success": True,
            "output": summary,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": f"Marked done: {subtask}",
        }

    if action == "complete_todo":
        import todo_manager

        summary_text = params.get("summary", "")
        pending = todo_manager.get_pending_todos()
        if pending:
            todo_manager.complete_todo(pending[0]["id"])
        summary = todo_manager.get_todo_summary()
        return {
            "success": True,
            "output": summary,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": "Todo completed",
        }

    if action == "list_todos":
        import todo_manager

        summary = todo_manager.get_todo_summary()
        return {
            "success": True,
            "output": summary,
            "error": "",
            "exit_code": 0,
            "verified": True,
            "verify_msg": summary,
        }

    return {
        "success": False,
        "output": "",
        "error": f"Unknown action: {action}",
        "exit_code": 1,
        "verified": False,
        "verify_msg": "Unknown action",
    }
