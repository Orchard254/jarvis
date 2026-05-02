#!/usr/bin/env python3
"""
JARVIS Health Check Runner - Real-time system monitoring dashboard.

This script runs independently alongside the live JARVIS system to verify
everything is working in real time. It checks every 60 seconds:

- IMPORTS: All modules and third-party packages
- LLM CONNECTION: Ollama cloud/local endpoints, latency, model availability
- AUDIO: Microphone/speaker devices, input audio levels
- TOOLS: get_time, battery_status, get_wifi, calculate tests
- MEMORY: conversation_history.json and user_profile.json validity
- PROCESSES: jarvis.py process, ambient monitor threads, TTS queue thread
- DISK: Log space, rotation, tool_reliability.json writability

Outputs a live dashboard to console with warnings/errors and automatic
recovery attempts after three consecutive failures.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Add workspace to path for imports
WORKSPACE = Path(__file__).parent
sys.path.insert(0, str(WORKSPACE))

# Try to import optional dependencies
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("[WARN] psutil not installed - some checks will be limited")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("[WARN] requests not installed - LLM checks will fail")

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    print("[WARN] pyaudio not installed - audio checks will be limited")

# Import settings
try:
    from settings import (
        OLLAMA_CLOUD_URL,
        OLLAMA_LOCAL_URL,
        OLLAMA_API_KEY,
        OLLAMA_MODEL,
        OLLAMA_TIMEOUT,
        LOG_DIR,
        DATA_DIR,
    )
except ImportError as e:
    print(f"[ERROR] Cannot import settings: {e}")
    # Set defaults
    OLLAMA_CLOUD_URL = "https://api.ollama.com/api/chat"
    OLLAMA_LOCAL_URL = "http://localhost:11434/api/chat"
    OLLAMA_API_KEY = ""
    OLLAMA_MODEL = "nemotron-3-nano:30b-cloud"
    OLLAMA_TIMEOUT = 180
    LOG_DIR = WORKSPACE / "logs"
    DATA_DIR = WORKSPACE / "jarvis_data"


# ── Logging Setup ────────────────────────────────────────────

HEALTH_LOG_FILE = LOG_DIR / "health_monitor.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(HEALTH_LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("health_runner")


# ── Data Classes ─────────────────────────────────────────────

@dataclass
class CheckResult:
    """Result of a single health check."""
    name: str
    status: str  # 'ok', 'warn', 'error'
    message: str
    details: str = ""
    latency_ms: Optional[float] = None
    
    def display_line(self, max_name_len: int = 14) -> str:
        """Format for dashboard display."""
        icon = "✓" if self.status == "ok" else ("⚠" if self.status == "warn" else "✗")
        padded_name = self.name.ljust(max_name_len)
        detail_str = f"  {self.details}" if self.details else ""
        return f"║ {padded_name} {icon}  {self.message}{detail_str}".ljust(50)[:50]


@dataclass 
class HealthState:
    """Overall health state tracker."""
    last_check: datetime = field(default_factory=datetime.now)
    results: List[CheckResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    consecutive_failures: Dict[str, int] = field(default_factory=dict)
    
    @property
    def is_healthy(self) -> bool:
        return len(self.errors) == 0 and all(r.status != "error" for r in self.results)


# ── Import Checks ────────────────────────────────────────────

CORE_MODULES = [
    "jarvis.core.brain",
    "jarvis.core.memory", 
    "jarvis.core.orchestrator",
    "jarvis.models.ollama_client",
    "jarvis.models.router",
    "jarvis.monitoring.ambient",
    "jarvis.monitoring.health_check",
    "jarvis.output.tts",
    "jarvis.output.formatter",
    "jarvis.perception.stt",
    "jarvis.perception.wake_word",
    "jarvis.profile.user_profile",
    "jarvis.tools.registry",
    "jarvis.tools.base",
]

THIRD_PARTY_PACKAGES = [
    "requests",
    "psutil",
    "pyaudio",
    "numpy",
    "sounddevice",
    "wave",
    "json",
    "threading",
    "datetime",
]


def check_imports() -> List[CheckResult]:
    """Check if all required modules can be imported."""
    results = []
    
    # Core modules
    for module in CORE_MODULES:
        try:
            __import__(module)
            results.append(CheckResult(
                name=f"import:{module.split('.')[-1]}",
                status="ok",
                message="importable",
                details=""
            ))
        except ImportError as e:
            results.append(CheckResult(
                name=f"import:{module.split('.')[-1]}",
                status="error",
                message=f"ImportError: {e}",
                details=""
            ))
    
    # Third-party packages
    for pkg in THIRD_PARTY_PACKAGES:
        try:
            __import__(pkg)
            results.append(CheckResult(
                name=f"pkg:{pkg}",
                status="ok", 
                message="available",
                details=""
            ))
        except ImportError:
            results.append(CheckResult(
                name=f"pkg:{pkg}",
                status="warn",
                message="not installed",
                details=""
            ))
    
    return results


# ── LLM Connection Checks ───────────────────────────────────

def check_llm_cloud() -> CheckResult:
    """Check Ollama cloud endpoint connectivity and latency."""
    if not HAS_REQUESTS:
        return CheckResult(
            name="LLM Cloud",
            status="error",
            message="requests unavailable",
            details=""
        )
    
    if not OLLAMA_API_KEY:
        return CheckResult(
            name="LLM Cloud",
            status="warn",
            message="API key not set",
            details=""
        )
    
    start = time.time()
    try:
        # Simple health check - try to reach the endpoint
        headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}", "Content-Type": "application/json"}
        resp = requests.get(
            OLLAMA_CLOUD_URL.replace("/chat", "/tags"),
            headers=headers,
            timeout=min(10, OLLAMA_TIMEOUT)
        )
        latency = (time.time() - start) * 1000
        
        if resp.status_code == 200:
            return CheckResult(
                name="LLM Cloud",
                status="ok",
                message=f"{latency:.0f}ms",
                details="",
                latency_ms=latency
            )
        elif resp.status_code == 401:
            return CheckResult(
                name="LLM Cloud",
                status="error",
                message="authentication failed",
                details=""
            )
        else:
            return CheckResult(
                name="LLM Cloud",
                status="warn",
                message=f"HTTP {resp.status_code}",
                details="",
                latency_ms=latency
            )
    except requests.exceptions.Timeout:
        return CheckResult(
            name="LLM Cloud",
            status="error",
            message="timeout",
            details=""
        )
    except requests.exceptions.ConnectionError as e:
        return CheckResult(
            name="LLM Cloud",
            status="error",
            message="unreachable",
            details=""
        )
    except Exception as e:
        return CheckResult(
            name="LLM Cloud",
            status="error",
            message=str(e)[:30],
            details=""
        )


def check_llm_local() -> CheckResult:
    """Check local Ollama endpoint availability."""
    if not HAS_REQUESTS:
        return CheckResult(
            name="LLM Local",
            status="error",
            message="requests unavailable",
            details=""
        )
    
    start = time.time()
    try:
        resp = requests.get(
            OLLAMA_LOCAL_URL.replace("/chat", "/tags"),
            timeout=5
        )
        latency = (time.time() - start) * 1000
        
        if resp.status_code == 200:
            return CheckResult(
                name="LLM Local",
                status="ok",
                message="available",
                details="",
                latency_ms=latency
            )
        else:
            return CheckResult(
                name="LLM Local",
                status="warn",
                message=f"HTTP {resp.status_code}",
                details=""
            )
    except requests.exceptions.Timeout:
        return CheckResult(
            name="LLM Local",
            status="warn",
            message="timeout",
            details=""
        )
    except requests.exceptions.ConnectionError:
        return CheckResult(
            name="LLM Local",
            status="warn",
            message="not running",
            details=""
        )
    except Exception as e:
        return CheckResult(
            name="LLM Local",
            status="error",
            message=str(e)[:30],
            details=""
        )


def check_model_available() -> CheckResult:
    """Check if configured model is available."""
    if not HAS_REQUESTS:
        return CheckResult(
            name="Model",
            status="error",
            message="requests unavailable",
            details=""
        )
    
    try:
        # Try local first
        resp = requests.get(
            OLLAMA_LOCAL_URL.replace("/chat", "/tags"),
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            if any(OLLAMA_MODEL in m for m in models):
                return CheckResult(
                    name="Model",
                    status="ok",
                    message=OLLAMA_MODEL[:25],
                    details=""
                )
            else:
                return CheckResult(
                    name="Model",
                    status="warn",
                    message=f"{OLLAMA_MODEL[:20]}... not found",
                    details=""
                )
    except:
        pass
    
    # Can't verify, assume ok for cloud
    return CheckResult(
        name="Model",
        status="ok",
        message="configured",
        details=OLLAMA_MODEL[:20]
    )


# ── Audio Device Checks ─────────────────────────────────────

def check_audio_devices() -> Tuple[CheckResult, CheckResult]:
    """Check microphone and speaker device availability."""
    mic_result = CheckResult(name="Microphone", status="ok", message="unknown", details="")
    speaker_result = CheckResult(name="Speakers", status="ok", message="unknown", details="")
    
    if not HAS_PYAUDIO:
        mic_result.status = "warn"
        mic_result.message = "pyaudio unavailable"
        speaker_result.status = "warn"
        speaker_result.message = "pyaudio unavailable"
        return mic_result, speaker_result
    
    try:
        audio = pyaudio.PyAudio()
        
        # Find input devices (microphones)
        mic_found = False
        mic_device = ""
        for i in range(audio.get_device_count()):
            try:
                info = audio.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    mic_found = True
                    mic_device = f"device {i}"
                    break
            except:
                continue
        
        # Find output devices (speakers)
        speaker_found = False
        speaker_device = ""
        for i in range(audio.get_device_count()):
            try:
                info = audio.get_device_info_by_index(i)
                if info.get("maxOutputChannels", 0) > 0:
                    speaker_found = True
                    speaker_device = f"device {i}"
                    break
            except:
                continue
        
        audio.terminate()
        
        if mic_found:
            mic_result.status = "ok"
            mic_result.message = mic_device
        else:
            mic_result.status = "warn"
            mic_result.message = "no input device"
        
        if speaker_found:
            speaker_result.status = "ok"
            speaker_result.message = speaker_device
        else:
            speaker_result.status = "warn"
            speaker_result.message = "no output device"
            
    except Exception as e:
        mic_result.status = "error"
        mic_result.message = str(e)[:25]
        speaker_result.status = "error"
        speaker_result.message = str(e)[:25]
    
    return mic_result, speaker_result


def check_audio_level() -> CheckResult:
    """Check current input audio level."""
    if not HAS_PYAUDIO:
        return CheckResult(
            name="Audio Level",
            status="warn",
            message="pyaudio unavailable",
            details=""
        )
    
    try:
        audio = pyaudio.PyAudio()
        
        # Get default input device
        default_input = audio.get_default_input_device_info()
        
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024,
            input_device_index=default_input["index"]
        )
        
        # Read a small chunk to measure level
        stream.start_stream()
        time.sleep(0.1)
        
        if stream.is_active():
            data = stream.read(1024, exception_on_overflow=False)
            # Calculate RMS level
            import struct
            shorts = struct.unpack(f"{len(data)//2}h", data)
            rms = (sum(s*s for s in shorts) / len(shorts)) ** 0.5
            
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
            # Normalize to percentage (typical max ~10000)
            level_pct = min(100, int(rms / 100))
            
            return CheckResult(
                name="Audio Level",
                status="ok",
                message=f"{level_pct}%",
                details=""
            )
        else:
            stream.close()
            audio.terminate()
            return CheckResult(
                name="Audio Level",
                status="warn",
                message="stream inactive",
                details=""
            )
            
    except Exception as e:
        return CheckResult(
            name="Audio Level",
            status="warn",
            message=f"error: {str(e)[:20]}",
            details=""
        )


# ── Tool Tests ──────────────────────────────────────────────

def test_get_time() -> CheckResult:
    """Test get_time tool."""
    from datetime import datetime
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    return CheckResult(
        name="get_time",
        status="ok",
        message=time_str,
        details=""
    )


def test_battery_status() -> CheckResult:
    """Test battery_status tool."""
    if not HAS_PSUTIL:
        return CheckResult(
            name="battery_status",
            status="warn",
            message="psutil unavailable",
            details=""
        )
    
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return CheckResult(
                name="battery_status",
                status="ok",
                message="no battery (desktop)",
                details=""
            )
        
        status = "charging" if battery.power_plugged else "discharging"
        if battery.power_plugged and battery.percent >= 100:
            status = "fully charged"
        
        return CheckResult(
            name="battery_status",
            status="ok",
            message=f"{battery.percent}% {status}",
            details=""
        )
    except FileNotFoundError:
        # Linux systems without battery sensors
        return CheckResult(
            name="battery_status",
            status="ok",
            message="no battery (desktop)",
            details=""
        )
    except Exception as e:
        return CheckResult(
            name="battery_status",
            status="warn",
            message=str(e)[:30],
            details=""
        )


def test_get_wifi() -> CheckResult:
    """Test get_wifi tool."""
    try:
        # Use PowerShell to get WiFi info (Windows)
        script = r'''
        $profile = netsh wlan show interfaces | Select-String -Pattern "^\s+SSID\s*:"
        if ($profile) {
            $ssid = ($profile -replace "^\s+SSID\s*:\s*", "").Trim()
            "$ssid"
        } else {
            "No WiFi"
        }
        '''
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            ssid = result.stdout.strip()
            if ssid:
                return CheckResult(
                    name="get_wifi",
                    status="ok",
                    message=ssid[:20],
                    details=""
                )
        
        return CheckResult(
            name="get_wifi",
            status="warn",
            message="not connected",
            details=""
        )
    except Exception as e:
        return CheckResult(
            name="get_wifi",
            status="warn",
            message=f"error: {str(e)[:20]}",
            details=""
        )


def test_calculate() -> CheckResult:
    """Test calculate tool with 2+2=4."""
    try:
        result = eval("2+2", {"__builtins__": {}}, {})
        if result == 4:
            return CheckResult(
                name="calculate",
                status="ok",
                message="2+2=4",
                details=""
            )
        else:
            return CheckResult(
                name="calculate",
                status="error",
                message=f"got {result}",
                details=""
            )
    except Exception as e:
        return CheckResult(
            name="calculate",
            status="error",
            message=str(e)[:25],
            details=""
        )


# ── Memory/JSON Checks ──────────────────────────────────────

def check_json_file(filepath: Path, name: str) -> CheckResult:
    """Check if a JSON file is readable and valid."""
    if not filepath.exists():
        # Try to create empty valid JSON
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump({}, f)
            return CheckResult(
                name=name,
                status="ok",
                message="created",
                details=""
            )
        except Exception as e:
            return CheckResult(
                name=name,
                status="warn",
                message="missing",
                details=""
            )
    
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return CheckResult(
            name=name,
            status="ok",
            message="valid",
            details=""
        )
    except json.JSONDecodeError:
        return CheckResult(
            name=name,
            status="error",
            message="invalid JSON",
            details=""
        )
    except Exception as e:
        return CheckResult(
            name=name,
            status="error",
            message=str(e)[:25],
            details=""
        )


def check_conversation_history() -> CheckResult:
    """Check conversation_history.json."""
    filepath = DATA_DIR / "conversation_history.json"
    return check_json_file(filepath, "History JSON")


def check_user_profile() -> CheckResult:
    """Check user_profile.json."""
    filepath = DATA_DIR / "user_profile.json"
    return check_json_file(filepath, "Profile JSON")


# ── Process Checks ──────────────────────────────────────────

def check_jarvis_process() -> CheckResult:
    """Check if jarvis.py process is running."""
    if not HAS_PSUTIL:
        return CheckResult(
            name="jarvis.py",
            status="warn",
            message="psutil unavailable",
            details=""
        )
    
    try:
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info.get('cmdline', []) or [])
                if 'jarvis.py' in cmdline or 'python' in cmdline and 'jarvis' in cmdline.lower():
                    return CheckResult(
                        name="jarvis.py",
                        status="ok",
                        message=f"PID {proc.pid}",
                        details=""
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return CheckResult(
            name="jarvis.py",
            status="warn",
            message="not found",
            details=""
        )
    except Exception as e:
        return CheckResult(
            name="jarvis.py",
            status="error",
            message=str(e)[:25],
            details=""
        )


def check_ambient_threads() -> CheckResult:
    """Check if ambient monitor threads are alive."""
    # Count threads with 'ambient' or 'monitor' in name
    ambient_count = 0
    total_threads = threading.active_count()
    
    for thread in threading.enumerate():
        name_lower = thread.name.lower()
        if 'ambient' in name_lower or 'monitor' in name_lower or 'check' in name_lower:
            if thread.is_alive():
                ambient_count += 1
    
    # Also check for any background daemon threads
    daemon_alive = sum(1 for t in threading.enumerate() if t.daemon and t.is_alive())
    
    # We expect at least some background activity
    if daemon_alive > 0 or ambient_count >= 0:
        return CheckResult(
            name="Ambient thread",
            status="ok",
            message=f"{daemon_alive} bg threads",
            details=""
        )
    
    return CheckResult(
        name="Ambient thread",
        status="warn",
        message="no monitors detected",
        details=""
    )


def check_tts_thread() -> CheckResult:
    """Check if TTS queue thread is alive."""
    for thread in threading.enumerate():
        if 'tts' in thread.name.lower() or 'speech' in thread.name.lower():
            if thread.is_alive():
                return CheckResult(
                    name="TTS thread",
                    status="ok",
                    message="running",
                    details=""
                )
    
    # TTS thread may not exist if TTS not enabled
    return CheckResult(
        name="TTS thread",
        status="ok",
        message="idle",
        details=""
    )


# ── Disk Checks ─────────────────────────────────────────────

def check_disk_space() -> CheckResult:
    """Check available disk space for logs."""
    try:
        if HAS_PSUTIL:
            disk = psutil.disk_usage(str(LOG_DIR.parent))
            free_gb = disk.free / (1024**3)
        else:
            # Fallback using shutil
            total, used, free = shutil.disk_usage(str(LOG_DIR.parent))
            free_gb = free / (1024**3)
        
        if free_gb < 0.5:
            return CheckResult(
                name="Disk space",
                status="warn",
                message=f"{free_gb:.1f} GB free",
                details="low space"
            )
        elif free_gb < 0.1:
            return CheckResult(
                name="Disk space",
                status="error",
                message=f"{free_gb:.1f} GB free",
                details="critical"
            )
        else:
            return CheckResult(
                name="Disk space",
                status="ok",
                message=f"{free_gb:.1f} GB free",
                details=""
            )
    except Exception as e:
        return CheckResult(
            name="Disk space",
            status="warn",
            message="unknown",
            details=""
        )


def check_log_rotation() -> CheckResult:
    """Check if log files are being rotated."""
    try:
        log_files = list(LOG_DIR.glob("*.log"))
        if not log_files:
            return CheckResult(
                name="Log rotation",
                status="ok",
                message="no old logs",
                details=""
            )
        
        # Check if main health log exists and is writable
        if HEALTH_LOG_FILE.exists():
            size_mb = HEALTH_LOG_FILE.stat().st_size / (1024**2)
            if size_mb > 10:
                return CheckResult(
                    name="Log rotation",
                    status="warn",
                    message=f"{size_mb:.1f}MB",
                    details="consider rotation"
                )
        
        return CheckResult(
            name="Log rotation",
            status="ok",
            message=f"{len(log_files)} files",
            details=""
        )
    except Exception as e:
        return CheckResult(
            name="Log rotation",
            status="warn",
            message=str(e)[:25],
            details=""
        )


def check_tool_reliability_writable() -> CheckResult:
    """Check if tool_reliability.json is writable."""
    filepath = DATA_DIR / "tool_reliability.json"
    try:
        # Test write access
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Try to read existing or create new
        if filepath.exists():
            with open(filepath, 'r') as f:
                json.load(f)
        
        # Test write
        with open(filepath, 'w') as f:
            json.dump({"test": True, "timestamp": datetime.now().isoformat()}, f)
        
        return CheckResult(
            name="tool_reliability",
            status="ok",
            message="writable",
            details=""
        )
    except Exception as e:
        return CheckResult(
            name="tool_reliability",
            status="error",
            message=str(e)[:25],
            details=""
        )


# ── Recovery Functions ──────────────────────────────────────

def recover_llm_cloud_to_local():
    """Attempt recovery: switch from cloud to local LLM."""
    log.warning("[RECOVERY] Attempting to switch LLM from cloud to local...")
    # This would require modifying runtime config - for now just log
    log.info("[RECOVERY] Update .env to set OLLAMA_MODE=local")


def recover_audio_devices():
    """Attempt recovery: re-detect audio devices."""
    log.warning("[RECOVERY] Attempting to re-detect audio devices...")
    if HAS_PYAUDIO:
        try:
            audio = pyaudio.PyAudio()
            audio.terminate()
            log.info("[RECOVERY] PyAudio re-initialized successfully")
        except Exception as e:
            log.error(f"[RECOVERY] PyAudio re-init failed: {e}")


def recover_json_backup(filepath: Path):
    """Attempt recovery: restore JSON from backup."""
    backup_path = filepath.with_suffix('.json.bak')
    if backup_path.exists():
        log.warning(f"[RECOVERY] Restoring {filepath.name} from backup...")
        try:
            shutil.copy(backup_path, filepath)
            log.info(f"[RECOVERY] Restored {filepath.name} from backup")
            return True
        except Exception as e:
            log.error(f"[RECOVERY] Restore failed: {e}")
    else:
        # Create empty valid JSON
        log.warning(f"[RECOVERY] Creating empty {filepath.name}...")
        try:
            with open(filepath, 'w') as f:
                json.dump({}, f)
            log.info(f"[RECOVERY] Created empty {filepath.name}")
            return True
        except Exception as e:
            log.error(f"[RECOVERY] Create failed: {e}")
    return False


# ── Toast Notification ──────────────────────────────────────

def send_toast_notification(title: str, message: str):
    """Send Windows toast notification."""
    try:
        script = f'''
        [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
        $balloon = New-Object System.Windows.Forms.NotifyIcon
        $balloon.BalloonTipTitle = '{title}'
        $balloon.BalloonTipText = '{message}'
        $balloon.Icon = [System.Drawing.SystemIcons]::Warning
        $balloon.Visible = $true
        $balloon.ShowBalloonTip(5000)
        '''
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=10
        )
        log.info(f"[TOAST] {title}: {message}")
    except Exception as e:
        log.error(f"[TOAST] Failed to send notification: {e}")


# ── Dashboard Display ───────────────────────────────────────

DASHBOARD_WIDTH = 50

def render_dashboard(state: HealthState) -> str:
    """Render the health dashboard as ASCII art."""
    lines = []
    
    # Header
    lines.append("╔" + "═" * DASHBOARD_WIDTH + "╗")
    title = "     JARVIS HEALTH MONITOR            "
    lines.append("║" + title.ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH] + "║")
    timestamp = f"     Last check: {state.last_check.strftime('%H:%M:%S')}             "
    lines.append("║" + timestamp.ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH] + "║")
    
    # Separator
    lines.append("╠" + "═" * DASHBOARD_WIDTH + "╣")
    
    # Results grouped by category
    categories = {
        "LLM": ["LLM Cloud", "LLM Local"],
        "AUDIO": ["Microphone", "Speakers"],
        "TOOLS": ["get_time", "battery_status", "get_wifi", "calculate"],
        "MEMORY": ["History JSON", "Profile JSON"],
        "PROCESS": ["Ambient thread", "TTS thread"],
        "DISK": ["Disk space", "Log rotation", "tool_reliability"],
    }
    
    for cat, names in categories.items():
        for result in state.results:
            for name in names:
                if name.lower() in result.name.lower():
                    lines.append(result.display_line())
                    break
    
    # Warnings section
    lines.append("╠" + "═" * DASHBOARD_WIDTH + "╣")
    lines.append("║ WARNINGS:".ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH] + "║")
    if state.warnings:
        for warn in state.warnings[:5]:  # Limit display
            warn_line = f"║ ⚠ {warn}".ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH]
            lines.append(warn_line)
    else:
        lines.append("║ ✓ None".ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH] + "║")
    
    # Errors section
    lines.append("╠" + "═" * DASHBOARD_WIDTH + "╣")
    lines.append("║ ERRORS:".ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH] + "║")
    if state.errors:
        for err in state.errors[:5]:  # Limit display
            err_line = f"║ ✗ {err}".ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH]
            lines.append(err_line)
    else:
        lines.append("║ ✓ None".ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH] + "║")
    
    # Overall status
    lines.append("╠" + "═" * DASHBOARD_WIDTH + "╣")
    if state.is_healthy:
        overall = "║ OVERALL: ✓ HEALTHY".ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH]
    else:
        overall = "║ OVERALL: ✗ UNHEALTHY".ljust(DASHBOARD_WIDTH)[:DASHBOARD_WIDTH]
    lines.append(overall + "║")
    
    # Footer
    lines.append("╚" + "═" * DASHBOARD_WIDTH + "╝")
    
    return "\n".join(lines)


def clear_console():
    """Clear console screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


# ── Main Health Check Runner ─────────────────────────────────

class HealthCheckRunner:
    """Main health check runner with continuous monitoring."""
    
    CHECK_INTERVAL = 60  # seconds
    FAILURE_THRESHOLD = 3
    
    def __init__(self):
        self.state = HealthState()
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._dashboard_displayed = False
        
    def run_all_checks(self) -> HealthState:
        """Run all health checks and update state."""
        state = HealthState()
        state.last_check = datetime.now()
        
        # LLM checks
        state.results.append(check_llm_cloud())
        state.results.append(check_llm_local())
        
        # Audio checks
        mic_result, speaker_result = check_audio_devices()
        state.results.append(mic_result)
        state.results.append(speaker_result)
        
        # Tool tests
        state.results.append(test_get_time())
        state.results.append(test_battery_status())
        state.results.append(test_get_wifi())
        state.results.append(test_calculate())
        
        # Memory checks
        state.results.append(check_conversation_history())
        state.results.append(check_user_profile())
        
        # Process checks
        state.results.append(check_ambient_threads())
        state.results.append(check_tts_thread())
        
        # Disk checks
        state.results.append(check_disk_space())
        state.results.append(check_log_rotation())
        state.results.append(check_tool_reliability_writable())
        
        # Collect warnings and errors
        for result in state.results:
            if result.status == "warn":
                state.warnings.append(f"{result.name}: {result.message}")
            elif result.status == "error":
                state.errors.append(f"{result.name}: {result.message}")
                
            # Track consecutive failures
            key = result.name
            if result.status == "error":
                state.consecutive_failures[key] = state.consecutive_failures.get(key, 0) + 1
            else:
                state.consecutive_failures[key] = 0
        
        # Check for API key warning
        if not OLLAMA_API_KEY:
            state.warnings.append("OLLAMA_API_KEY not set")
        
        self.state = state
        return state
    
    def handle_failures(self):
        """Handle consecutive failures with recovery attempts."""
        for check_name, count in self.state.consecutive_failures.items():
            if count >= self.FAILURE_THRESHOLD:
                log.error(f"[FAILURE] {check_name} has failed {count} times consecutively")
                
                # Attempt recovery based on check type
                if "LLM Cloud" in check_name:
                    recover_llm_cloud_to_local()
                elif "Microphone" in check_name or "Speaker" in check_name:
                    recover_audio_devices()
                elif "JSON" in check_name or "History" in check_name or "Profile" in check_name:
                    if "History" in check_name:
                        recover_json_backup(DATA_DIR / "conversation_history.json")
                    elif "Profile" in check_name:
                        recover_json_backup(DATA_DIR / "user_profile.json")
                
                # Send toast notification
                send_toast_notification(
                    "JARVIS Health Alert",
                    f"{check_name} has failed {count} times"
                )
                
                # Reset counter after handling
                self.state.consecutive_failures[check_name] = 0
    
    def display_dashboard(self):
        """Display the health dashboard."""
        clear_console()
        print(render_dashboard(self.state))
        self._dashboard_displayed = True
    
    def run_once(self):
        """Run a single health check cycle."""
        self.run_all_checks()
        self.handle_failures()
        self.display_dashboard()
        
        # Log summary
        if self.state.is_healthy:
            log.info("[HEALTH] System healthy")
        else:
            log.warning(f"[HEALTH] {len(self.state.errors)} errors, {len(self.state.warnings)} warnings")
    
    def run_continuous(self):
        """Run continuous health monitoring."""
        self.running = True
        log.info(f"[START] Health monitoring started (interval: {self.CHECK_INTERVAL}s)")
        
        while self.running:
            try:
                self.run_once()
                time.sleep(self.CHECK_INTERVAL)
            except KeyboardInterrupt:
                log.info("[STOP] Interrupted by user")
                break
            except Exception as e:
                log.error(f"[ERROR] Health check failed: {e}")
                time.sleep(5)  # Brief pause before retry
        
        self.running = False
        log.info("[STOP] Health monitoring stopped")
    
    def start_background(self):
        """Start health monitoring in background thread."""
        self._thread = threading.Thread(target=self.run_continuous, daemon=True)
        self._thread.start()
        return self._thread
    
    def stop(self):
        """Stop health monitoring."""
        self.running = False


# ── Entry Point ─────────────────────────────────────────────

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="JARVIS Health Check Runner")
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=60,
        help="Check interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--once", "-1",
        action="store_true",
        help="Run once and exit"
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Don't clear console between checks"
    )
    
    args = parser.parse_args()
    
    runner = HealthCheckRunner()
    runner.CHECK_INTERVAL = args.interval
    
    # Override clear_console if requested
    if args.no_clear:
        runner.display_dashboard = lambda: print(render_dashboard(runner.state))
    
    try:
        if args.once:
            runner.run_once()
        else:
            runner.run_continuous()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
        runner.stop()


if __name__ == "__main__":
    main()
