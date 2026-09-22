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


def _blank():
    """A fresh, independent default (never share mutable objects between instances)."""
    return {"long_term": [], "summary": "", "updated": None}


class Memory:
    def __init__(self, path=None):
        self.path = path or MEMORY_FILE
        self.data = self._load()

    # -- disk -------------------------------------------------------------
    def _load(self):
        data = _blank()
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                data["long_term"] = list(raw.get("long_term", []))
                data["summary"] = str(raw.get("summary", ""))
                data["updated"] = raw.get("updated")
        except Exception as e:
            print(f"[memory] couldn't read memory file ({e}); starting fresh.")
        return data

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

    def remove_fact(self, fact):
        needle = (fact or "").strip().lower()
        if not needle:
            return "Nothing to forget."
        before = len(self.data["long_term"])
        self.data["long_term"] = [f for f in self.data["long_term"] if needle not in f.lower()]
        removed = before - len(self.data["long_term"])
        if removed:
            self._save()
            return f"Forgot {removed} thing(s)."
        return f"I didn't have anything about '{fact}'."

    def clear(self):
        count = len(self.data["long_term"])
        self.data["long_term"] = []
        self._save()
        return f"Cleared {count} thing(s) I knew."

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
