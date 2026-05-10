"""Process management tool — list, kill, check running processes."""

import logging
import sys
import time

logger = logging.getLogger(__name__)


def process_manager(
    action: str,
    name: str = None,
    pid: int = None,
    timeout: int = 5,
) -> dict:
    """
    Manage OS processes.
    Actions: list, kill, kill_by_name, is_running, wait_for
    """
    try:
        import psutil
    except ImportError:
        return {
            "success": False,
            "error": "psutil not installed. Run: pip install psutil",
        }

    try:
        # ── list ─────────────────────────────────────────────────────────────
        if action == "list":
            processes = []
            for proc in psutil.process_iter(
                ["name", "pid", "status", "memory_info", "cpu_percent"]
            ):
                try:
                    info = proc.info
                    mem = info.get("memory_info")
                    processes.append(
                        {
                            "name": info.get("name", ""),
                            "pid": info.get("pid"),
                            "status": info.get("status", ""),
                            "memory_mb": round(mem.rss / 1e6, 1) if mem else 0.0,
                            "cpu_percent": info.get("cpu_percent", 0.0),
                        }
                    )
                    if len(processes) >= 50:
                        break
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue

            return {
                "success": True,
                "processes": processes,
                "count": len(processes),
                "action": "list",
            }

        # ── kill ─────────────────────────────────────────────────────────────
        elif action == "kill":
            if pid is None and name is None:
                return {
                    "success": False,
                    "error": "action 'kill' requires 'name' or 'pid' parameter",
                }
            killed = []
            if pid is not None:
                try:
                    psutil.Process(pid).kill()
                    killed.append(pid)
                except psutil.NoSuchProcess:
                    return {"success": False, "error": f"No process with pid={pid}"}
                except psutil.AccessDenied:
                    return {
                        "success": False,
                        "error": f"Access denied killing pid={pid}",
                    }
            else:
                killed = _kill_by_name(name, psutil)
            return {"success": True, "killed": killed, "action": "kill"}

        # ── kill_by_name ──────────────────────────────────────────────────────
        elif action == "kill_by_name":
            if name is None:
                return {
                    "success": False,
                    "error": "action 'kill_by_name' requires 'name' parameter",
                }
            killed = _kill_by_name(name, psutil)
            return {
                "success": True,
                "killed": killed,
                "count": len(killed),
                "action": "kill_by_name",
            }

        # ── is_running ────────────────────────────────────────────────────────
        elif action == "is_running":
            if name is None:
                return {
                    "success": False,
                    "error": "action 'is_running' requires 'name' parameter",
                }
            pids = _find_pids_by_name(name, psutil)
            return {
                "success": True,
                "running": len(pids) > 0,
                "pids": pids,
                "count": len(pids),
                "name": name,
                "action": "is_running",
            }

        # ── wait_for ──────────────────────────────────────────────────────────
        elif action == "wait_for":
            if name is None:
                return {
                    "success": False,
                    "error": "action 'wait_for' requires 'name' parameter",
                }
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                pids = _find_pids_by_name(name, psutil)
                if pids:
                    return {
                        "success": True,
                        "running": True,
                        "pid": pids[0],
                        "action": "wait_for",
                    }
                # Non-blocking wait on Windows with message pumping
                if sys.platform == "win32":
                    import pythoncom
                    grace_end = time.monotonic() + 0.5
                    while time.monotonic() < grace_end:
                        pythoncom.PumpWaitingMessages()
                        time.sleep(0.05)
                else:
                    time.sleep(0.5)
            return {
                "success": False,
                "error": f"{name} did not start within {timeout}s",
            }

        else:
            return {"success": False, "error": f"Unknown action: '{action}'"}

    except Exception as e:
        logger.error(f"process_manager({action}): {e}")
        return {"success": False, "error": str(e)}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _find_pids_by_name(name: str, psutil_mod) -> list:
    """Return list of PIDs whose name contains *name* (case-insensitive)."""
    pids = []
    name_lower = name.lower()
    for proc in psutil_mod.process_iter(["name", "pid"]):
        try:
            if name_lower in (proc.info.get("name") or "").lower():
                pids.append(proc.info["pid"])
        except (
            psutil_mod.NoSuchProcess,
            psutil_mod.AccessDenied,
            psutil_mod.ZombieProcess,
        ):
            continue
    return pids


def _kill_by_name(name: str, psutil_mod) -> list:
    """Kill all processes matching *name*. Return list of killed PIDs."""
    killed = []
    for pid in _find_pids_by_name(name, psutil_mod):
        try:
            psutil_mod.Process(pid).kill()
            killed.append(pid)
        except (
            psutil_mod.NoSuchProcess,
            psutil_mod.AccessDenied,
            psutil_mod.ZombieProcess,
        ):
            continue
    return killed
