"""ClicX system status collection (Fase 1).

Returns a grouped dict for the ``{"t":"status","get":true}`` request. Uses psutil;
on any failure the individual field degrades to 0/None rather than blocking the poll.

IMPORTANT: this is a read-only collector. It makes no calls and has no side effects on
system state. Import locally / lazily so a missing psutil never breaks main.py startup.
"""

from __future__ import annotations

import platform
import time
from typing import Any

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil always present in the plan's deps
    psutil = None


def _battery() -> dict[str, Any] | None:
    if psutil is None:
        return None
    try:
        b = psutil.sensors_battery()
        if b is None:
            return None
        return {
            "percent": int(round(b.percent)),
            "plugged": bool(b.power_plugged),
        }
    except Exception:  # noqa: BLE001
        return None


_cpu_primed = False


def _cpu() -> dict[str, Any] | None:
    """CPU load averaged over the gap since the previous call.

    ``interval=0.1`` samples too narrow a window: it routinely answers 0-1%
    while Task Manager, which averages over about a second, shows ten times
    that. ``interval=None`` returns the average since the last call instead, so
    with the phone polling every 2 s each reading covers those 2 s — the same
    kind of window Task Manager uses — and the call no longer blocks the server
    thread for 100 ms per poll.

    The very first call has no previous sample to compare against and always
    answers 0.0, so prime it once and report that first reading as None.
    """
    global _cpu_primed
    if psutil is None:
        return None
    try:
        cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1
        if not _cpu_primed:
            psutil.cpu_percent(interval=None)
            _cpu_primed = True
            return {"percent": None, "cores": cores}
        return {
            "percent": float(round(psutil.cpu_percent(interval=None), 1)),
            "cores": cores,
        }
    except Exception:  # noqa: BLE001
        return None


def _ram() -> dict[str, Any] | None:
    if psutil is None:
        return None
    try:
        v = psutil.virtual_memory()
        return {
            "total": v.total,
            "used": v.used,
            "percent": float(round(v.percent, 1)),
        }
    except Exception:  # noqa: BLE001
        return None


def _disk() -> dict[str, Any] | None:
    if psutil is None:
        return None
    try:
        u = psutil.disk_usage("C:\\")
        return {
            "total": u.total,
            "used": u.used,
            "free": u.free,
            "percent": float(round(u.percent, 1)),
        }
    except Exception:  # noqa: BLE001
        return None


def _network() -> dict[str, Any] | None:
    if psutil is None:
        return None
    try:
        stats: dict[str, Any] = {"bytes_sent": 0, "bytes_recv": 0}
        for _name, io in psutil.net_io_counters(pernic=True).items():
            stats["bytes_sent"] += io.bytes_sent
            stats["bytes_recv"] += io.bytes_recv
        return stats
    except Exception:  # noqa: BLE001
        return None


def collect_status(*, version: str, ip: str) -> dict[str, Any]:
    """Grouped status payload for ``t:status``. Cheap and non-blocking (~0.2 s)."""
    boot = None
    uptime = None
    if psutil is not None:
        try:
            boot = psutil.boot_time()
            now = time.time()
            uptime = max(0, int(now - boot))
        except Exception:  # noqa: BLE001
            boot = None

    return {
        "device": "ClicX",
        "connected": True,
        "battery": _battery(),
        "cpu": _cpu(),
        "ram": _ram(),
        "disk": _disk(),
        "network": _network(),
        "ip": ip,
        "uptime": uptime,
        "os": platform.platform(),
        "version": version,
    }
