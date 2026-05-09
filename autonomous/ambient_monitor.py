"""
Ambient system-health monitor — background daemon thread.

Polls psutil every MONITOR_INTERVAL seconds and raises toast / console
alerts via notify_user when hardware thresholds are crossed.

Per-event cooldowns (default 10 min) prevent alert spam while still
re-alerting if the condition persists after the cooldown window ends.

Public API
----------
start() -> dict   — launch the daemon thread (idempotent, guard-safe)
stop()  -> dict   — signal clean shutdown and join the thread
"""

import logging
import platform
import threading
import time

logger = logging.getLogger(__name__)

# ── psutil guard ──────────────────────────────────────────────────────────────
try:
    import psutil as _psutil

    _psutil_available = True
except ImportError:
    _psutil = None  # type: ignore[assignment]
    _psutil_available = False
    logger.warning(
        "ambient_monitor: psutil is not installed — hardware monitoring is "
        "disabled. Install it with: pip install psutil"
    )

# ── Settings ──────────────────────────────────────────────────────────────────
try:
    from settings import (
        AMBIENT_MONITORING,
        BATTERY_CRITICAL_THRESHOLD,
        BATTERY_WARN_THRESHOLD,
        CPU_SPIKE_DURATION,
        CPU_SPIKE_THRESHOLD,
        DISK_WARN_THRESHOLD,
        MEMORY_WARN_THRESHOLD,
        MONITOR_INTERVAL,
    )
except ImportError as _exc:
    logger.warning(
        f"ambient_monitor: settings import failed ({_exc}); using built-in defaults"
    )
    AMBIENT_MONITORING = True
    BATTERY_WARN_THRESHOLD = 20
    BATTERY_CRITICAL_THRESHOLD = 10
    CPU_SPIKE_THRESHOLD = 90
    CPU_SPIKE_DURATION = 30
    MEMORY_WARN_THRESHOLD = 85
    DISK_WARN_THRESHOLD = 92
    MONITOR_INTERVAL = 15

# ── notify_user ───────────────────────────────────────────────────────────────
try:
    from tools.notify_user import notify_user as _notify_user
except ImportError:
    # Graceful fallback: log only so the monitor can still run without the tool.
    def _notify_user(message: str, urgency: str = "normal") -> dict:  # type: ignore[misc]
        logger.warning(f"ambient_monitor [{urgency.upper()}]: {message}")
        return {"success": False, "reason": "notify_user_unavailable"}


# ── Constants ─────────────────────────────────────────────────────────────────
# Base cooldown between repeat alerts for the same event key.
_COOLDOWN_BASE: int = 600        # 10 min — first re-alert window
_COOLDOWN_MAX: int  = 7200       # 2 hr  — cap for persistent conditions

# Meaningful change thresholds — suppress re-alert if the value hasn't moved.
# Key: event key prefix → minimum delta before re-alerting regardless of backoff.
# This stops "Disk is 92% full (8.1 GB free)" firing 6× a night when nothing changed.
_DISK_CHANGE_GB   = 0.5   # must free/lose ≥ 0.5 GB to count as a new event
_MEM_CHANGE_PCT   = 3.0   # must move ≥ 3 percentage points
_CPU_CHANGE_PCT   = 5.0   # must move ≥ 5 percentage points
_BAT_CHANGE_PCT   = 2.0   # must drop ≥ 2 percentage points

# ── Module-level state ────────────────────────────────────────────────────────
_stop_event: threading.Event = threading.Event()
_thread: "threading.Thread | None" = None
_cpu_spike_start: "float | None" = None  # when CPU first exceeded the spike threshold

# Per-event tracking: {event_key: {"last_time": float, "fire_count": int, "last_value": float}}
_alert_state: "dict[str, dict]" = {}


# ── Cooldown helpers ──────────────────────────────────────────────────────────


def _get_backoff(event_key: str) -> int:
    """
    Return the current backoff window for event_key using exponential backoff.

    Sequence: 600s → 1800s → 3600s → 7200s (cap).
    Each time the same event fires, the next window doubles (up to the cap).
    This means a persistent disk-full condition alerts at:
      t=0, t+10min, t+40min, t+1h40min, t+3h40min, t+5h40min ... (capped at +2h)
    """
    count = _alert_state.get(event_key, {}).get("fire_count", 0)
    backoff = _COOLDOWN_BASE * (2 ** count)
    return min(backoff, _COOLDOWN_MAX)


def _value_changed(event_key: str, current_value: float, threshold: float) -> bool:
    """Return True if current_value has changed by ≥ threshold since last alert."""
    last_value = _alert_state.get(event_key, {}).get("last_value")
    if last_value is None:
        return True  # First time — always treat as changed
    return abs(current_value - last_value) >= threshold


def _can_alert(event_key: str) -> bool:
    """Return True if the backoff window has elapsed since the last alert."""
    last_time = _alert_state.get(event_key, {}).get("last_time", 0.0)
    return time.time() - last_time >= _get_backoff(event_key)


def _fire_alert(
    event_key: str,
    message: str,
    urgency: str,
    current_value: float = None,
    value_threshold: float = None,
) -> None:
    """
    Invoke notify_user and update alert state — but only when BOTH conditions hold:
      1. The backoff window has elapsed.
      2. The metric value has changed meaningfully (if value tracking is used).

    Exponential backoff means repeated identical alerts slow to a maximum of
    one alert per 2 hours, preventing notification spam for persistent conditions.
    """
    # Value-change suppression: if the value hasn't moved enough, skip the alert
    # even if the time window has elapsed.  This stops "Disk 92% (8.1 GB free)"
    # from repeating every 10 minutes when nothing has actually changed.
    if current_value is not None and value_threshold is not None:
        if not _value_changed(event_key, current_value, value_threshold):
            # Value unchanged — only fire if we're past the full max backoff
            # (i.e., condition has persisted for very long and user may have missed it)
            last_time = _alert_state.get(event_key, {}).get("last_time", 0.0)
            if time.time() - last_time < _COOLDOWN_MAX:
                return  # Too soon and no meaningful change — skip

    if not _can_alert(event_key):
        return

    try:
        _notify_user(message, urgency)
    except Exception as exc:
        logger.error(f"ambient_monitor: notify_user raised an exception: {exc}")

    # Update state: increment fire_count for backoff, record time and value
    state = _alert_state.setdefault(event_key, {"fire_count": 0, "last_time": 0.0, "last_value": None})
    state["fire_count"] += 1
    state["last_time"] = time.time()
    if current_value is not None:
        state["last_value"] = current_value

    logger.info(
        f"ambient_monitor: alert fired [{urgency}] (fire #{state['fire_count']}, "
        f"next backoff {_get_backoff(event_key)//60}min) — {message}"
    )


def _clear_alert(event_key: str) -> None:
    """
    Reset the alert state when a condition clears (e.g. battery plugged in,
    CPU drops below threshold).  The next trigger will start fresh with the
    base cooldown and fire_count=0.
    """
    if event_key in _alert_state:
        _alert_state[event_key]["fire_count"] = 0
        _alert_state[event_key]["last_value"] = None


# ── Per-metric checks ─────────────────────────────────────────────────────────


def _check_battery() -> None:
    """
    Alert when the battery drops below warning / critical levels and the
    device is not plugged in.  Silently skips on desktops where
    sensors_battery() returns None.  Resets alert state when plugged in so
    the next unplug starts fresh.
    """
    if _psutil is None:
        return
    battery = _psutil.sensors_battery()
    if battery is None:
        return  # Desktop or battery sensor not available

    pct: float = battery.percent
    plugged: bool = bool(battery.power_plugged)

    if plugged:
        # Condition cleared — reset so the next low-battery event fires immediately
        _clear_alert("battery_critical")
        _clear_alert("battery_warn")
        return

    if pct <= BATTERY_CRITICAL_THRESHOLD:
        _fire_alert(
            "battery_critical",
            f"\u26a0 Battery critically low: {pct:.0f}% — plug in immediately!",
            "high",
            current_value=pct,
            value_threshold=_BAT_CHANGE_PCT,
        )
    elif pct <= BATTERY_WARN_THRESHOLD:
        _fire_alert(
            "battery_warn",
            f"Battery low: {pct:.0f}% remaining — consider plugging in.",
            "normal",
            current_value=pct,
            value_threshold=_BAT_CHANGE_PCT,
        )


def _check_cpu(now: float) -> None:
    """
    Alert only after CPU has been *continuously* above CPU_SPIKE_THRESHOLD
    for at least CPU_SPIKE_DURATION seconds (sustained-spike detection).
    Resets alert state when CPU drops back to normal.
    """
    global _cpu_spike_start

    if _psutil is None:
        return
    cpu_pct: float = _psutil.cpu_percent(interval=None)

    if cpu_pct >= CPU_SPIKE_THRESHOLD:
        if _cpu_spike_start is None:
            _cpu_spike_start = now
        else:
            duration = now - _cpu_spike_start
            if duration >= CPU_SPIKE_DURATION:
                _fire_alert(
                    "cpu_spike",
                    f"CPU has been at {cpu_pct:.0f}% for {int(duration)}s "
                    f"— system may be overloaded.",
                    "high",
                    current_value=cpu_pct,
                    value_threshold=_CPU_CHANGE_PCT,
                )
    else:
        if _cpu_spike_start is not None:
            # CPU recovered — reset backoff so the next spike fires immediately
            _clear_alert("cpu_spike")
        _cpu_spike_start = None


def _check_memory() -> None:
    """Alert when RAM utilisation exceeds MEMORY_WARN_THRESHOLD."""
    if _psutil is None:
        return
    mem = _psutil.virtual_memory()
    pct: float = mem.percent
    if pct < MEMORY_WARN_THRESHOLD:
        _clear_alert("memory_warn")
        return

    free_mb: int = mem.available // (1024**2)
    urgency = "high" if pct >= 95 else "normal"
    _fire_alert(
        "memory_warn",
        f"Memory usage at {pct:.0f}% ({free_mb} MB free).",
        urgency,
        current_value=pct,
        value_threshold=_MEM_CHANGE_PCT,
    )


def _check_disk() -> None:
    """
    Alert when the system partition exceeds DISK_WARN_THRESHOLD% used.
    Uses free_gb as the change metric — only re-alerts if free space has
    dropped by ≥ _DISK_CHANGE_GB since the last alert, OR the max backoff
    has elapsed (so a persistent full disk gets a reminder every 2 hours,
    not every 10 minutes).
    """
    if _psutil is None:
        return
    root = "C:\\" if platform.system() == "Windows" else "/"
    try:
        usage = _psutil.disk_usage(root)
    except (PermissionError, FileNotFoundError, OSError):
        return

    pct: float = usage.percent
    if pct < DISK_WARN_THRESHOLD:
        _clear_alert("disk_warn")
        return

    free_gb: float = usage.free / (1024**3)
    urgency = "high" if pct >= 98 else "normal"
    _fire_alert(
        "disk_warn",
        f"Disk {root!r} is {pct:.0f}% full ({free_gb:.1f} GB free).",
        urgency,
        current_value=free_gb,
        value_threshold=_DISK_CHANGE_GB,
    )


# ── Main loop ─────────────────────────────────────────────────────────────────


def _monitor_loop() -> None:
    """Daemon thread body: poll hardware metrics and fire threshold alerts."""
    logger.info("ambient_monitor: loop started")

    # Prime the CPU percentage counter so the first interval=None call in
    # _check_cpu has a real baseline rather than returning 0.0.
    if _psutil is not None:
        _psutil.cpu_percent(interval=None)

    while not _stop_event.is_set():
        now = time.time()

        try:
            _check_battery()
        except Exception as exc:
            logger.debug(f"ambient_monitor: battery check error: {exc}")

        try:
            _check_cpu(now)
        except Exception as exc:
            logger.debug(f"ambient_monitor: cpu check error: {exc}")

        try:
            _check_memory()
        except Exception as exc:
            logger.debug(f"ambient_monitor: memory check error: {exc}")

        try:
            _check_disk()
        except Exception as exc:
            logger.debug(f"ambient_monitor: disk check error: {exc}")

        # Block for MONITOR_INTERVAL seconds (or until stop() is called).
        _stop_event.wait(MONITOR_INTERVAL)

    logger.info("ambient_monitor: loop stopped")


# ── Public API ────────────────────────────────────────────────────────────────


def start() -> dict:
    """
    Launch the ambient monitoring daemon thread.

    Silently skips if:
    - ``AMBIENT_MONITORING`` is ``False`` in settings
    - ``psutil`` is not installed
    - The thread is already running (idempotent)

    Returns:
        dict with ``success`` (bool) and optional ``reason`` (str).
    """
    global _thread

    if not AMBIENT_MONITORING:
        logger.info(
            "ambient_monitor: disabled via AMBIENT_MONITORING=False — not starting"
        )
        return {"success": False, "reason": "disabled_by_settings"}

    if not _psutil_available:
        logger.warning(
            "ambient_monitor: psutil is not available — "
            "install with `pip install psutil`"
        )
        return {"success": False, "reason": "psutil_not_installed"}

    if _thread and _thread.is_alive():
        logger.debug("ambient_monitor: already running")
        return {"success": True, "reason": "already_running"}

    _stop_event.clear()
    _thread = threading.Thread(
        target=_monitor_loop,
        daemon=True,
        name="ambient-monitor",
    )
    _thread.start()
    logger.info(
        f"ambient_monitor: started "
        f"(interval={MONITOR_INTERVAL}s, cooldown={_COOLDOWN_SECONDS}s)"
    )
    return {"success": True}


def stop() -> dict:
    """
    Signal the daemon thread to stop and block up to 5 seconds for it to
    finish its current poll cycle.

    Returns:
        dict with ``success`` (bool).
    """
    global _thread
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    logger.info("ambient_monitor: stopped")
    return {"success": True}
