# config.py — Configuration for Personal Assistant

import os

import sounddevice as sd
from dotenv import load_dotenv

load_dotenv()

from function_definitions import get_function_docs

# --- Mode ---
CONTINUOUS_MODE = True  # Set to True to disable wake word and enable continuous conversation
PIPER_EXE = "piper_bin/piper/piper"
PIPER_MODEL = "voices/en_US-lessac-medium.onnx"

# --- TTS Engine Selection ---
# Options: "piper" or "kokoro"
TTS_ENGINE = "kokoro"  # Change to "piper" to use Piper TTS

# --- Kokoro TTS Settings ---
KOKORO_LANG_CODE = "a"  # 'a' for American English, 'b' for British English
KOKORO_VOICE = "bm_george"  # Options: af_heart, af_bella, af_nicole, af_sarah, af_sky, am_adam, am_michael, bf_emma, bf_isabella, bm_george, bm_lewis
KOKORO_SPEED = 1.15  # Speech speed (0.5 - 2.0)


# --- Smart Device Detection ---
def get_preferred_device(kind="input"):
    from logger import get_logger

    log = get_logger("config")
    devices = sd.query_devices()
    # Only log warnings about devices
    if not devices or all(dev[f"max_{kind}_channels"] == 0 for dev in devices):
        log.warning(f"No {kind} devices found!")
    channel_key = f"max_{kind}_channels"
    if kind == "input":
        include_patterns = ["microphone array", "realtek", "microphone"]
        exclude_patterns = ["stereo mix", "camo", "webcam", "virtual", "cable"]
    else:
        include_patterns = ["speaker", "headphone", "realtek", "audio"]
        exclude_patterns = ["virtual", "cable", "stream"]
    for pattern in include_patterns:
        for i, dev in enumerate(devices):
            name = dev["name"].lower()
            if any(ex in name for ex in exclude_patterns):
                continue
            if pattern in name and dev[channel_key] > 0:
                log.warning(f'Selected {kind} device: {dev["name"]} (index {i})')
                return i
    for i, dev in enumerate(devices):
        if dev[channel_key] > 0:
            log.warning(f'Fallback {kind} device: {dev["name"]} (index {i})')
            return i
    try:
        index = sd.query_devices(kind=kind)["index"]
        log.warning(f"Default {kind} device: {sd.query_devices(index)['name']} (index {index})")
        return index
    except sd.PortAudioError as e:
        log.warning(f"Audio device error: {e}")
        return None
    except Exception as e:
        log.warning(f"Unexpected error getting audio device: {e}")
        return None


MIC_DEVICE = get_preferred_device(kind="input")
AUDIO_DEVICE = get_preferred_device(kind="output")

# --- Mic recording ---
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 400
SILENCE_DURATION = 1.5  # Reduced for faster response
MAX_RECORD_SECS = 30  # Reduced to prevent overly long recordings
STT_THRESHOLD_FLOOR = 10  # Lower to catch quiet speech

# --- Ollama Cloud LLM  ---
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
OLLAMA_CLOUD_URL = "https://api.ollama.com/api/chat"
OLLAMA_MODEL = "gpt-oss:20b-cloud"
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "180"))

OLLAMA_TEMPERATURE = 0.7
OLLAMA_MAX_TOKENS = 512
AGENT_MAX_TOKENS = 2000

MAX_HISTORY = 10

_FUNCTION_DOCS = get_function_docs()


def _gather_system_context() -> str:
    """Run once at startup: collect real machine info via PowerShell.

    Returns a formatted string injected into the system prompt so the LLM
    knows the actual environment it is operating in — no more guessing paths,
    usernames, Windows version, or timezone.
    """
    import json as _json
    import subprocess

    script = r"""
$info = @{}
try { $info.username    = $env:USERNAME } catch {}
try { $info.computername = $env:COMPUTERNAME } catch {}
try { $info.userprofile  = $env:USERPROFILE } catch {}
try { $info.os           = (Get-CimInstance Win32_OperatingSystem).Caption } catch {}
try { $info.os_version   = (Get-CimInstance Win32_OperatingSystem).Version } catch {}
try {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $info.cpu = $cpu.Name.Trim()
    $info.cpu_cores = $cpu.NumberOfCores
} catch {}
try {
    $ram_gb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    $info.ram_gb = $ram_gb
} catch {}
try {
    $disk = Get-PSDrive C | Select-Object Used,Free
    $info.disk_free_gb  = [math]::Round($disk.Free  / 1GB, 1)
    $info.disk_total_gb = [math]::Round(($disk.Used + $disk.Free) / 1GB, 1)
} catch {}
try { $info.timezone     = (Get-TimeZone).Id } catch {}
try { $info.timezone_display = (Get-TimeZone).DisplayName } catch {}
try { $info.has_battery  = ($null -ne (Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue)) } catch { $info.has_battery = $false }
try { $info.powershell_version = $PSVersionTable.PSVersion.ToString() } catch {}
$info | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = _json.loads(result.stdout.strip())
    except Exception:
        data = {}

    lines = ["=== LIVE SYSTEM CONTEXT (gathered at startup) ==="]
    lines.append(f"User:          {data.get('username', 'unknown')}")
    lines.append(f"Computer:      {data.get('computername', 'unknown')}")
    lines.append(f"Home folder:   {data.get('userprofile', '%USERPROFILE%')}")
    lines.append(
        f"OS:            {data.get('os', 'Windows')} (build {data.get('os_version', '?')})"
    )
    lines.append(
        f"CPU:           {data.get('cpu', 'unknown')} ({data.get('cpu_cores', '?')} cores)"
    )
    lines.append(f"RAM:           {data.get('ram_gb', '?')} GB")
    lines.append(
        f"Disk C:        {data.get('disk_free_gb', '?')} GB free / {data.get('disk_total_gb', '?')} GB total"
    )
    lines.append(f"Timezone:      {data.get('timezone_display', data.get('timezone', 'unknown'))}")
    lines.append(f"Has battery:   {data.get('has_battery', 'unknown')}")
    lines.append(f"PowerShell:    {data.get('powershell_version', 'unknown')}")
    # Store home path for use in prompt
    global _USER_HOME
    _USER_HOME = data.get("userprofile", r"C:\Users\User")
    return "\n".join(lines)


_USER_HOME = r"C:\Users\User"  # default, overwritten by _gather_system_context()
_SYSTEM_CONTEXT = _gather_system_context()


def get_system_prompt() -> str:
    """DEPRECATED: This function is no longer used.

    The system now uses jarvis_prompt.build_jarvis_prompt() instead.
    This stub remains for backward compatibility with any legacy imports.
    """
    raise NotImplementedError(
        "get_system_prompt() is deprecated. " "Use jarvis_prompt.build_jarvis_prompt() instead."
    )
