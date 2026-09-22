"""
reminders.py - timers and reminders that survive restarts.

A background thread checks for due reminders and calls `on_fire(reminder)`.
Pending reminders are persisted to disk, so if you set one for tomorrow and close
the app, it's still there (and rescheduled) next time you start.
"""

import json
import threading
import time
import uuid
from datetime import datetime

from config import REMINDERS_FILE


class ReminderManager:
    def __init__(self, on_fire=None, path=None, tick=5.0):
        self.path = path or REMINDERS_FILE
        self.on_fire = on_fire
        self.tick = tick
        self.items = self._load()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # -- disk -------------------------------------------------------------
    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"[reminders] couldn't read reminders ({e}).")
        return []

    def _save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.items, f, indent=2, ensure_ascii=False)
            tmp.replace(self.path)

    # -- api --------------------------------------------------------------
    def add(self, message, due):
        rid = uuid.uuid4().hex[:8]
        with self._lock:
            self.items.append({
                "id": rid,
                "message": (message or "").strip(),
                "due": due.isoformat(timespec="seconds"),
            })
        self._save()
        return rid

    def list(self):
        with self._lock:
            return sorted(self.items, key=lambda r: r["due"])

    def cancel(self, rid):
        rid = str(rid).strip()
        with self._lock:
            before = len(self.items)
            self.items = [r for r in self.items if r["id"] != rid]
            removed = before - len(self.items)
        self._save()
        return removed

    def pending_count(self):
        with self._lock:
            return len(self.items)

    # -- background loop --------------------------------------------------
    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            now = datetime.now()
            due_now = []
            with self._lock:
                keep = []
                for r in self.items:
                    try:
                        if datetime.fromisoformat(r["due"]) <= now:
                            due_now.append(r)
                        else:
                            keep.append(r)
                    except Exception:
                        pass  # drop anything unparsable
                self.items = keep
            if due_now:
                self._save()
                for r in due_now:
                    try:
                        if self.on_fire:
                            self.on_fire(r)
                        else:
                            print(f"\n*** Reminder: {r['message']} ***\n")
                    except Exception as e:
                        print(f"[reminders] error firing reminder: {e}")
            time.sleep(self.tick)
