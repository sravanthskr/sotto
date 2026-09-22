"""
proactive.py - a quiet background watcher.

When it notices something genuinely useful (disk nearly full, battery about to die) it
can speak up. It is deliberately conservative: one message per condition, with a long
cooldown, so it never becomes a nag.
"""

import threading
import time

try:
    import psutil
except ImportError:
    psutil = None

DEFAULTS = {
    "enabled": True,
    "interval_seconds": 300,     # how often to look
    "low_disk_gb": 10.0,
    "low_battery_pct": 20.0,
    "cooldown_seconds": 3600,    # don't repeat the same nudge within an hour
}


class ProactiveWatcher:
    def __init__(self, notify, config=None):
        self.notify = notify
        self.cfg = dict(DEFAULTS)
        if config:
            self.cfg.update(config)
        self._last_fired = {}
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None or not self.cfg["enabled"] or psutil is None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _due(self, key, now):
        if now - self._last_fired.get(key, 0) >= self.cfg["cooldown_seconds"]:
            self._last_fired[key] = now
            return True
        return False

    def check_once(self, now=None):
        """Return the messages that should surface right now (usually none)."""
        if psutil is None:
            return []
        now = now if now is not None else time.time()
        messages = []

        try:
            for part in psutil.disk_partitions(all=False):
                if not part.mountpoint.upper().startswith("C:"):
                    continue
                free_gb = psutil.disk_usage(part.mountpoint).free / (1024 ** 3)
                if free_gb < self.cfg["low_disk_gb"] and self._due("disk", now):
                    messages.append(f"your C: drive is down to {free_gb:.1f} GB free")
        except Exception:
            pass

        try:
            bat = psutil.sensors_battery()
            if (bat is not None and not bat.power_plugged
                    and bat.percent <= self.cfg["low_battery_pct"]
                    and self._due("battery", now)):
                messages.append(f"battery's at {bat.percent:.0f}% and not charging")
        except Exception:
            pass

        return messages

    def _loop(self):
        while not self._stop.is_set():
            try:
                for message in self.check_once():
                    self.notify(message)
            except Exception:
                pass
            time.sleep(self.cfg["interval_seconds"])
