"""
memory.py - Persistent, local memory.

Two things live here:
  1. long_term - durable facts about the user (name, preferences, habits).
  2. summary   - a rolling compressed summary of past conversation.

Both are stored as JSON on disk, so the assistant actually remembers you between runs.
Nothing here is ever sent anywhere except as part of the normal model context.
"""

import json
import threading
from datetime import datetime

from config import MEMORY_FILE

_LOCK = threading.Lock()

_DEFAULT = {
    "long_term": [],   # list[str]
    "summary": "",     # str
    "updated": None,   # iso timestamp
}


class Memory:
    def __init__(self, path=None):
        self.path = path or MEMORY_FILE
        self.data = self._load()

    # -- disk -------------------------------------------------------------
    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                merged = dict(_DEFAULT)
                for k, v in _DEFAULT.items():
                    merged[k] = raw.get(k, v)
                return merged
        except Exception as e:
            print(f"[memory] couldn't read memory file ({e}); starting fresh.")
        return dict(_DEFAULT)

    def _save(self):
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            tmp.replace(self.path)

    # -- long-term facts --------------------------------------------------
    def add_fact(self, fact):
        fact = (fact or "").strip()
        if not fact:
            return "Nothing to remember."
        if fact.lower() in (x.lower() for x in self.data["long_term"]):
            return "Already knew that."
        self.data["long_term"].append(fact)
        self.data["updated"] = datetime.now().isoformat(timespec="seconds")
        self._save()
        return "Noted."

    def facts(self):
        return list(self.data["long_term"])

    # -- rolling summary --------------------------------------------------
    def set_summary(self, text):
        self.data["summary"] = (text or "").strip()
        self.data["updated"] = datetime.now().isoformat(timespec="seconds")
        self._save()

    def summary(self):
        return self.data.get("summary", "")

    # -- context injected into the system prompt --------------------------
    def context_block(self):
        parts = []
        facts = self.facts()
        if facts:
            parts.append("Things you already know about the user:\n- " + "\n- ".join(facts))
        if self.summary():
            parts.append("Summary of earlier conversation:\n" + self.summary())
        return "\n\n".join(parts)
