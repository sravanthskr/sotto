"""
sysinfo.py - system awareness: CPU, memory, disk, battery, processes, network.

Uses psutil when available; every function degrades gracefully if it isn't.
"""

import socket
import time
from datetime import datetime

try:
    import psutil
except ImportError:
    psutil = None


def _gb(n):
    return n / (1024 ** 3)


def system_status():
    """A compact one-line health summary."""
    if psutil is None:
        return "Error: psutil isn't installed (run: pip install psutil)."
    parts = []
    try:
        parts.append(f"CPU {psutil.cpu_percent(interval=0.3):.0f}%")
    except Exception:
        pass
    try:
        vm = psutil.virtual_memory()
        parts.append(f"RAM {vm.percent:.0f}% used ({_gb(vm.available):.1f} GB free)")
    except Exception:
        pass
    try:
        for part in psutil.disk_partitions(all=False):
            if not part.mountpoint.upper().startswith("C:"):
                continue
            usage = psutil.disk_usage(part.mountpoint)
            parts.append(f"C: {_gb(usage.free):.1f} GB free of {_gb(usage.total):.1f} GB")
    except Exception:
        pass
    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            state = "charging" if bat.power_plugged else "on battery"
            parts.append(f"Battery {bat.percent:.0f}% ({state})")
    except Exception:
        pass
    try:
        up = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
        total = int(up.total_seconds())
        parts.append(f"up {total // 3600}h {(total % 3600) // 60}m")
    except Exception:
        pass
    return ". ".join(parts) + "."


def top_processes(limit=5, by="cpu"):
    if psutil is None:
        return "Error: psutil isn't installed (run: pip install psutil)."
    limit = int(limit or 5)
    procs = []
    for proc in psutil.process_iter(["name"]):
        try:
            proc.cpu_percent(None)   # prime the per-process counter
            procs.append(proc)
        except Exception:
            continue
    time.sleep(0.4)                  # let the counters advance
    rows = []
    for proc in procs:
        try:
            rows.append((proc.info.get("name") or "?",
                         float(proc.cpu_percent(None) or 0.0),
                         float(proc.memory_percent() or 0.0)))
        except Exception:
            continue
    idx = 2 if str(by).lower().startswith("mem") else 1
    rows.sort(key=lambda t: t[idx], reverse=True)
    named = [r for r in rows if r[0] != "?"]
    rows = named or rows
    if not rows:
        return "Couldn't read the process list."
    return "; ".join(f"{n} ({c:.0f}% cpu, {m:.1f}% mem)" for n, c, m in rows[:limit])


def network_check():
    parts = []
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=4).close()
        parts.append("internet reachable")
    except Exception:
        parts.append("internet unreachable")
    try:
        socket.gethostbyname("www.google.com")
        parts.append("DNS ok")
    except Exception:
        parts.append("DNS failing")
    return "; ".join(parts) + "."
