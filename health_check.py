# health_check.py — System health monitoring and diagnostics

import psutil

from logger import get_logger

log = get_logger("health_check")


def check_system_health() -> dict:
    """Comprehensive system health check."""
    health_report = {
        "timestamp": None,
        "overall_status": "healthy",
        "checks": {},
    }

    # CPU Check
    cpu_percent = psutil.cpu_percent(interval=1)
    health_report["checks"]["cpu"] = {
        "usage_percent": cpu_percent,
        "status": "warning" if cpu_percent > 80 else "healthy",
        "message": f"CPU usage at {cpu_percent}%",
    }

    # Memory Check
    memory = psutil.virtual_memory()
    health_report["checks"]["memory"] = {
        "usage_percent": memory.percent,
        "available_gb": round(memory.available / (1024**3), 2),
        "total_gb": round(memory.total / (1024**3), 2),
        "status": "warning" if memory.percent > 85 else "healthy",
        "message": f"Memory usage at {memory.percent}%",
    }

    # Disk Check
    disk = psutil.disk_usage("C:\\")
    health_report["checks"]["disk"] = {
        "usage_percent": disk.percent,
        "free_gb": round(disk.free / (1024**3), 2),
        "total_gb": round(disk.total / (1024**3), 2),
        "status": "warning" if disk.percent > 90 else "healthy",
        "message": f"Disk usage at {disk.percent}%",
    }

    # Battery Check (if available)
    try:
        battery = psutil.sensors_battery()
        if battery:
            health_report["checks"]["battery"] = {
                "percent": battery.percent,
                "plugged_in": battery.power_plugged,
                "status": (
                    "warning" if battery.percent < 20 and not battery.power_plugged else "healthy"
                ),
                "message": f"Battery at {battery.percent}%"
                + (" (charging)" if battery.power_plugged else ""),
            }
    except Exception:
        health_report["checks"]["battery"] = {"status": "unknown", "message": "No battery detected"}

    # Process Count Check
    process_count = len(psutil.pids())
    health_report["checks"]["processes"] = {
        "count": process_count,
        "status": "warning" if process_count > 300 else "healthy",
        "message": f"{process_count} processes running",
    }

    # Determine overall status
    for check in health_report["checks"].values():
        if check["status"] == "critical":
            health_report["overall_status"] = "critical"
            break
        elif check["status"] == "warning" and health_report["overall_status"] != "critical":
            health_report["overall_status"] = "warning"

    return health_report
