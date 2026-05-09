"""
network_check — network sense organ.

Provides lightweight connectivity checks before tools that require a network
(search_web, fetch_url, browser, execute_code with network ops).  All stdlib —
zero new dependencies beyond optional `psutil` (already a project dep).

Actions
-------
ping        Check if a host is reachable on port 53 (DNS) or 80/443.
            Returns {reachable, host, latency_ms}.
dns         Resolve a hostname to its IP(s).
            Returns {resolved, host, addresses}.
speed       Rough download speed estimate via a small HTTP download.
            Returns {download_mbps}.  Requires internet access.
connections List active TCP/UDP connections grouped by state.
            Returns {connections, summary}.
interfaces  List network interfaces and their addresses.
            Returns {interfaces}.
"""

from __future__ import annotations

import logging
import socket
import time
import urllib.request

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _tcp_ping(host: str, port: int, timeout: float) -> tuple[bool, float]:
    """Return (reachable, latency_ms). Latency is -1 on failure."""
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = (time.monotonic() - t0) * 1000
            return True, round(latency, 1)
    except OSError:
        return False, -1.0


def _pick_port(host: str) -> int:
    """Choose an appropriate port for connectivity check."""
    if host in ("8.8.8.8", "8.8.4.4", "1.1.1.1"):
        return 53   # DNS
    return 443      # HTTPS for named hosts; fallback to 80 handled in ping


# ── action handlers ───────────────────────────────────────────────────────────

def _action_ping(host: str, timeout: float) -> dict:
    port = _pick_port(host)
    reachable, latency = _tcp_ping(host, port, timeout)
    if not reachable and port == 443:
        # Fallback to port 80
        reachable, latency = _tcp_ping(host, 80, timeout)
    return {
        "success": True,
        "reachable": reachable,
        "host": host,
        "latency_ms": latency if reachable else None,
    }


def _action_dns(host: str) -> dict:
    try:
        infos = socket.getaddrinfo(host, None)
        addresses = list({info[4][0] for info in infos})
        return {"success": True, "resolved": True, "host": host, "addresses": addresses}
    except socket.gaierror as exc:
        return {"success": True, "resolved": False, "host": host, "error": str(exc)}


def _action_speed() -> dict:
    """
    Download a ~1 MB test file from Cloudflare's speed-test endpoint and
    calculate throughput.  Uses only stdlib urllib.
    """
    url = "https://speed.cloudflare.com/__down?bytes=1000000"
    try:
        t0 = time.monotonic()
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
            data = resp.read()
        elapsed = time.monotonic() - t0
        mbps = round((len(data) * 8) / elapsed / 1_000_000, 2)
        return {"success": True, "download_mbps": mbps, "bytes_received": len(data)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _action_connections() -> dict:
    try:
        import psutil

        conns = psutil.net_connections(kind="inet")
        rows = []
        summary: dict[str, int] = {}
        for c in conns:
            state = c.status or "NONE"
            summary[state] = summary.get(state, 0) + 1
            rows.append({
                "fd": c.fd,
                "type": "TCP" if c.type == socket.SOCK_STREAM else "UDP",
                "local": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else None,
                "remote": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None,
                "status": state,
                "pid": c.pid,
            })
        return {"success": True, "connections": rows[:50], "summary": summary,
                "total": len(rows)}
    except ImportError:
        return {"success": False, "error": "psutil not installed — cannot list connections"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _action_interfaces() -> dict:
    try:
        import psutil

        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        result = {}
        for iface, addr_list in addrs.items():
            st = stats.get(iface)
            result[iface] = {
                "is_up": st.isup if st else None,
                "speed_mbps": st.speed if st else None,
                "addresses": [
                    {"family": str(a.family), "address": a.address, "netmask": a.netmask}
                    for a in addr_list
                ],
            }
        return {"success": True, "interfaces": result}
    except ImportError:
        # Fallback: list via socket (IPv4 only, no speed/status)
        import struct
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        return {"success": True, "interfaces": {hostname: {"addresses": [{"address": ip}]}}}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ── public API ────────────────────────────────────────────────────────────────

def network_check(
    action: str = "ping",
    host: str = "8.8.8.8",
    timeout: int = 3,
) -> dict:
    """
    Check network status.

    Parameters
    ----------
    action : str
        One of: ``ping``, ``dns``, ``speed``, ``connections``, ``interfaces``.
    host : str
        Target host for ``ping`` / ``dns`` (default ``8.8.8.8``).
    timeout : int
        Seconds before a ping attempt times out (default 3).

    Returns
    -------
    dict
        Always contains ``success`` (bool).  See module docstring for
        action-specific fields.
    """
    logger.info(f"network_check: action={action} host={host}")
    try:
        if action == "ping":
            return _action_ping(host, float(timeout))
        elif action == "dns":
            return _action_dns(host)
        elif action == "speed":
            return _action_speed()
        elif action == "connections":
            return _action_connections()
        elif action == "interfaces":
            return _action_interfaces()
        else:
            return {"success": False, "error": f"Unknown action '{action}'"}
    except Exception as exc:
        logger.error(f"network_check unexpected error: {exc}")
        return {"success": False, "error": str(exc)}
