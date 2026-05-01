# ambient.py — JARVIS ambient intelligence: proactive monitoring without being asked

"""
Runs background threads that watch the system and surface important events
proactively — battery drain, CPU spikes, upcoming timers, idle detection.
This is what makes an assistant feel like JARVIS rather than a chatbot.
"""

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import psutil

from logger import get_logger

log = get_logger("ambient")

# ── Thresholds ────────────────────────────────────────────────────────────────

BATTERY_WARN_THRESHOLD = 20  # % — warn when below this and unplugged
BATTERY_CRITICAL_THRESHOLD = 10  # % — urgent when below this
CPU_SPIKE_THRESHOLD = 90  # % sustained for CPU_SPIKE_DURATION seconds
CPU_SPIKE_DURATION = 30  # seconds of high CPU before alerting
MEMORY_WARN_THRESHOLD = 85  # % used
DISK_WARN_THRESHOLD = 92  # % used
IDLE_MINUTES = 20  # minutes of silence before proactive check-in
MONITOR_INTERVAL = 15  # seconds between ambient checks


class AmbientMonitor:
    """
    Runs as daemon threads — never blocks the main assistant loop.
    Calls `alert_cb(message)` to surface events to the user via TTS.
    Calls `suggest_cb(suggestion)` for lower-priority proactive tips.
    """

    def __init__(
        self,
        alert_cb: Callable[[str], None],
        suggest_cb: Callable[[str], None] = None,
    ):
        self._alert = alert_cb
        self._suggest = suggest_cb or (lambda s: log.info(f"[AMBIENT] Suggest: {s}"))
        self._stop = threading.Event()

        # State tracking to avoid repeated alerts
        self._battery_alerted_low = False
        self._battery_alerted_critical = False
        self._cpu_spike_start: float | None = None
        self._cpu_spike_alerted = False
        self._memory_alerted = False
        self._last_interaction_time = time.time()
        self._idle_suggested = False

        self._threads: list[threading.Thread] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start all background monitoring threads."""
        specs = [
            ("battery-monitor", self._battery_loop),
            ("resource-monitor", self._resource_loop),
            ("idle-monitor", self._idle_loop),
            ("timer-monitor", self._timer_loop),
        ]
        for name, target in specs:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        log.info(f"[AMBIENT] Started {len(specs)} monitoring threads")

    def stop(self):
        """Signal all threads to exit."""
        self._stop.set()

    def ping(self):
        """Call this whenever the user speaks — resets idle timer."""
        self._last_interaction_time = time.time()
        self._idle_suggested = False

    # ── Battery monitor ───────────────────────────────────────────────────────

    def _battery_loop(self):
        while not self._stop.wait(30):
            try:
                battery = psutil.sensors_battery()
                if battery is None:
                    continue  # Desktop — no battery

                pct = battery.percent
                plugged = battery.power_plugged

                if plugged:
                    # Reset alerts when plugged in
                    self._battery_alerted_low = False
                    self._battery_alerted_critical = False
                    continue

                if pct <= BATTERY_CRITICAL_THRESHOLD and not self._battery_alerted_critical:
                    self._alert(
                        f"Sir, battery is critically low at {int(pct)} percent. "
                        "I recommend plugging in immediately."
                    )
                    self._battery_alerted_critical = True
                    self._battery_alerted_low = True

                elif pct <= BATTERY_WARN_THRESHOLD and not self._battery_alerted_low:
                    mins = int(battery.secsleft / 60) if battery.secsleft > 0 else None
                    time_str = f", approximately {mins} minutes remaining" if mins else ""
                    self._alert(
                        f"Battery is at {int(pct)} percent{time_str}. " "You may want to plug in."
                    )
                    self._battery_alerted_low = True

            except Exception as e:
                log.debug(f"[AMBIENT] Battery check error: {e}")

    # ── Resource monitor ─────────────────────────────────────────────────────

    def _resource_loop(self):
        while not self._stop.wait(MONITOR_INTERVAL):
            try:
                cpu = psutil.cpu_percent(interval=2)
                mem = psutil.virtual_memory().percent
                disk = psutil.disk_usage("C:\\").percent

                # CPU spike detection
                if cpu >= CPU_SPIKE_THRESHOLD:
                    if self._cpu_spike_start is None:
                        self._cpu_spike_start = time.time()
                        self._cpu_spike_alerted = False
                    elif (
                        not self._cpu_spike_alerted
                        and time.time() - self._cpu_spike_start >= CPU_SPIKE_DURATION
                    ):
                        # Find the culprit
                        culprit = _top_cpu_process()
                        self._alert(
                            f"CPU has been at {int(cpu)} percent for over {CPU_SPIKE_DURATION} seconds. "
                            + (f"{culprit} is the primary consumer." if culprit else "")
                        )
                        self._cpu_spike_alerted = True
                else:
                    self._cpu_spike_start = None
                    self._cpu_spike_alerted = False

                # Memory warning
                if mem >= MEMORY_WARN_THRESHOLD and not self._memory_alerted:
                    self._alert(
                        f"Memory usage is at {int(mem)} percent. "
                        "Consider closing unused applications."
                    )
                    self._memory_alerted = True
                elif mem < MEMORY_WARN_THRESHOLD - 5:
                    self._memory_alerted = False

                # Disk warning (low frequency)
                if disk >= DISK_WARN_THRESHOLD:
                    log.warning(f"[AMBIENT] Disk C: at {disk:.1f}%")

            except Exception as e:
                log.debug(f"[AMBIENT] Resource check error: {e}")

    # ── Idle monitor ─────────────────────────────────────────────────────────

    def _idle_loop(self):
        while not self._stop.wait(60):
            try:
                idle_secs = time.time() - self._last_interaction_time
                idle_mins = idle_secs / 60

                if idle_mins >= IDLE_MINUTES and not self._idle_suggested:
                    hour = datetime.now().hour
                    if 9 <= hour < 22:  # Only during waking hours
                        self._suggest(_idle_suggestion(hour))
                    self._idle_suggested = True

            except Exception as e:
                log.debug(f"[AMBIENT] Idle check error: {e}")

    # ── Timer / reminder monitor ──────────────────────────────────────────────

    def _timer_loop(self):
        reminders_dir = Path(__file__).parent / "reminders"
        while not self._stop.wait(10):
            try:
                if not reminders_dir.exists():
                    continue
                now = datetime.now()
                for f in reminders_dir.glob("reminder_*.txt"):
                    try:
                        ts_str = f.stem.replace("reminder_", "")
                        trigger = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                        if now >= trigger:
                            msg = f.read_text(encoding="utf-8").strip()
                            self._alert(f"Timer alert. {msg}")
                            f.unlink()
                    except Exception:
                        pass
            except Exception as e:
                log.debug(f"[AMBIENT] Timer check error: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _top_cpu_process() -> str:
    """Return the name of the process consuming the most CPU."""
    try:
        procs = [
            (p.info["name"], p.info["cpu_percent"])
            for p in psutil.process_iter(["name", "cpu_percent"])
            if p.info["cpu_percent"] and p.info["cpu_percent"] > 5
        ]
        if procs:
            name, pct = max(procs, key=lambda x: x[1])
            return f"{name} is using {pct:.0f} percent CPU"
    except Exception:
        pass
    return ""


def _idle_suggestion(hour: int) -> str:
    if 9 <= hour < 12:
        return "Good morning. Whenever you're ready, I'm here."
    elif 12 <= hour < 14:
        return "You've been idle a while. Good time for a break."
    elif 14 <= hour < 18:
        return "I'm standing by whenever you need me."
    elif 18 <= hour < 22:
        return "Still here if you need anything this evening."
    return ""
