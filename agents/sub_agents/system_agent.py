"""
System Sub-Agent — PC control: processes, stats, apps, hardware.

Handles tasks like:
  - "Check which apps are using the most CPU right now"
  - "Kill all Chrome processes"
  - "Open Spotify and set volume to 60"
  - "Get system stats and warn if anything is critical"
  - "List all running apps"

Reports findings and actions taken to Jarvis.
"""

from __future__ import annotations

import logging
import time

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register

logger = logging.getLogger(__name__)


class SystemAgent(SubAgentBase):
    name = "system"
    description = (
        "PC control: monitor processes, system stats, open/close apps, "
        "control volume and brightness. Use for hardware and OS-level tasks."
    )
    capabilities = [
        "get_system_stats",
        "list_running_apps",
        "get_process_info",
        "open_app",
        "close_app",
        "kill_process",
        "set_volume",
        "set_brightness",
        "get_battery",
        "screenshot",
    ]

    def run(self, task: SubAgentTask) -> SubAgentResult:
        start = time.time()
        tool_log: list[dict] = []
        goal = task.goal
        ctx = task.context
        errors: list[str] = []
        results: dict = {}

        self._log.info(f"[{task.task_id}] System task: {goal[:100]}")

        action = ctx.get("action", "auto")

        if action == "auto":
            goal_lower = goal.lower()
            import re
            
            # set volume
            if "volume" in goal_lower or "vol" in goal_lower:
                match = re.search(r'(?:volume|vol)\D*(\d+)', goal_lower)
                if match:
                    action = "set_volume"
                    ctx["level"] = int(match.group(1))
            
            # set brightness
            elif "brightness" in goal_lower or "bright" in goal_lower:
                match = re.search(r'(?:brightness|bright)\D*(\d+)', goal_lower)
                if match:
                    action = "set_brightness"
                    ctx["level"] = int(match.group(1))
            
            # kill process / close app
            elif "kill" in goal_lower or "terminate" in goal_lower or "stop" in goal_lower:
                match = re.search(r'(?:kill|terminate|stop)\s+(?:all\s+)?([a-zA-Z0-9._\-]+)', goal_lower)
                if match:
                    action = "kill_process"
                    ctx["process_name"] = match.group(1)
            
            # open app
            elif "open" in goal_lower or "launch" in goal_lower or "start" in goal_lower:
                match = re.search(r'(?:open|launch|start)\s+([a-zA-Z0-9._\-]+)', goal_lower)
                if match:
                    action = "open_app"
                    ctx["app_name"] = match.group(1)
            
            # close app
            elif "close" in goal_lower:
                match = re.search(r'close\s+([a-zA-Z0-9._\-]+)', goal_lower)
                if match:
                    action = "close_app"
                    ctx["app_name"] = match.group(1)
                    
            # battery
            elif "battery" in goal_lower:
                action = "battery"

        # ── SYSTEM STATS ──────────────────────────────────────────────────────
        if action in ("stats", "auto", "health_check"):
            ok, result = self._tool_ok("get_system_stats")
            tool_log.append({"tool": "get_system_stats", **result})
            if ok:
                results["stats"] = result
                # Flag any critical conditions
                alerts = []
                cpu = result.get("cpu_percent", 0)
                ram = result.get("ram_percent", 0)
                disk = result.get("disk_percent", 0)
                bat = result.get("battery_percent")
                if cpu > 90:
                    alerts.append(f"CPU critical: {cpu}%")
                if ram > 85:
                    alerts.append(f"RAM high: {ram}%")
                if disk > 90:
                    alerts.append(f"Disk nearly full: {disk}%")
                if bat is not None and bat < 15 and not result.get("battery_plugged"):
                    alerts.append(f"Battery low: {bat}%")
                results["alerts"] = alerts
            else:
                errors.append(f"get_system_stats: {result.get('error', '?')}")

        # ── LIST RUNNING APPS ─────────────────────────────────────────────────
        if action in ("list_apps", "auto"):
            ok, result = self._tool_ok("list_running_apps")
            tool_log.append({"tool": "list_running_apps", **result})
            if ok:
                results["running_apps"] = result.get("windows", [])
            else:
                errors.append(f"list_running_apps: {result.get('error', '?')}")

        # ── PROCESS INFO (by name) ────────────────────────────────────────────
        if action in ("process_info",) and "process_name" in ctx:
            name = ctx["process_name"]
            ok, result = self._tool_ok("get_process_info", name=name)
            tool_log.append({"tool": "get_process_info", "name": name, **result})
            if ok:
                results["processes"] = result.get("processes", [])
            else:
                errors.append(f"get_process_info({name}): {result.get('error', '?')}")

        # ── OPEN APP ─────────────────────────────────────────────────────────
        if action in ("open_app", "launch") and "app_name" in ctx:
            app = ctx["app_name"]
            ok, result = self._tool_ok("open_app", name=app)
            tool_log.append({"tool": "open_app", "name": app, **result})
            if ok:
                results["launched"] = app
            else:
                errors.append(f"open_app({app}): {result.get('error', '?')}")

        # ── CLOSE APP ─────────────────────────────────────────────────────────
        if action == "close_app" and "app_name" in ctx:
            app = ctx["app_name"]
            force = ctx.get("force", False)
            ok, result = self._tool_ok("close_app", name=app, force=force)
            tool_log.append({"tool": "close_app", "name": app, **result})
            if ok:
                results["closed"] = app
            else:
                errors.append(f"close_app({app}): {result.get('error', '?')}")

        # ── KILL PROCESS ──────────────────────────────────────────────────────
        if action == "kill_process" and "process_name" in ctx:
            name = ctx["process_name"]
            ok, result = self._tool_ok("kill_process", name=name)
            tool_log.append({"tool": "kill_process", "name": name, **result})
            if ok:
                results["killed"] = name
            else:
                errors.append(f"kill_process({name}): {result.get('error', '?')}")

        # ── SET VOLUME ────────────────────────────────────────────────────────
        if action == "set_volume" and "level" in ctx:
            level = int(ctx["level"])
            ok, result = self._tool_ok("set_volume", level=level)
            tool_log.append({"tool": "set_volume", "level": level, **result})
            if ok:
                results["volume"] = level
            else:
                errors.append(f"set_volume({level}): {result.get('error', '?')}")

        # ── SET BRIGHTNESS ────────────────────────────────────────────────────
        if action == "set_brightness" and "level" in ctx:
            level = int(ctx["level"])
            ok, result = self._tool_ok("set_brightness", level=level)
            tool_log.append({"tool": "set_brightness", "level": level, **result})
            if ok:
                results["brightness"] = level
            else:
                errors.append(f"set_brightness({level}): {result.get('error', '?')}")

        # ── BATTERY ───────────────────────────────────────────────────────────
        if action == "battery":
            ok, result = self._tool_ok("get_battery")
            tool_log.append({"tool": "get_battery", **result})
            if ok:
                results["battery"] = result
            else:
                errors.append(f"get_battery: {result.get('error', '?')}")

        # ── Build summary ──────────────────────────────────────────────────────
        elapsed = round(time.time() - start, 2)
        success = bool(results) and not (errors and not results)

        summary_parts = [f"System agent completed '{goal[:80]}':"]

        if "stats" in results:
            s = results["stats"]
            summary_parts.append(
                f"  CPU: {s.get('cpu_percent')}% | "
                f"RAM: {s.get('ram_percent')}% ({s.get('ram_free_gb')} GB free) | "
                f"Disk: {s.get('disk_percent')}% ({s.get('disk_free_gb')} GB free)"
            )
            bat = s.get("battery_percent")
            if bat is not None:
                plugged = "plugged in" if s.get("battery_plugged") else "on battery"
                summary_parts.append(f"  Battery: {bat}% ({plugged})")
            for alert in results.get("alerts", []):
                summary_parts.append(f"  ⚠️  {alert}")

        if "running_apps" in results:
            apps = results["running_apps"]
            visible = [a["title"] for a in apps if a.get("visible")][:10]
            summary_parts.append(f"  Running apps ({len(apps)} total): {', '.join(visible)}")

        if "processes" in results:
            procs = results["processes"]
            for p in procs[:5]:
                summary_parts.append(
                    f"  Process: {p.get('name')} PID={p.get('pid')} "
                    f"CPU={p.get('cpu_percent', '?')}% MEM={p.get('memory_percent', '?'):.1f}%"
                )

        if "launched" in results:
            summary_parts.append(f"  Launched: {results['launched']}")
        if "closed" in results:
            summary_parts.append(f"  Closed: {results['closed']}")
        if "killed" in results:
            summary_parts.append(f"  Killed process: {results['killed']}")
        if "volume" in results:
            summary_parts.append(f"  Volume set to {results['volume']}%")
        if "brightness" in results:
            summary_parts.append(f"  Brightness set to {results['brightness']}%")
        if "battery" in results:
            b = results["battery"]
            summary_parts.append(
                f"  Battery: {b.get('battery_percent')}% — "
                f"{'plugged in' if b.get('plugged_in') else 'on battery'} — "
                f"{b.get('time_remaining', '')}"
            )

        if errors:
            summary_parts.append(f"  Errors: {'; '.join(errors)}")

        if len(summary_parts) == 1:
            summary_parts.append("  No system operations performed (check context keys).")

        return SubAgentResult(
            success=success,
            summary="\n".join(summary_parts),
            data=results,
            error="; ".join(errors) if not success else "",
            tool_calls=tool_log,
            elapsed_s=elapsed,
            agent_name=self.name,
        )


register(SystemAgent())
