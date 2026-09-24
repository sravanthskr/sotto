"""
notes.py - quick local notes you can ask the assistant to read back.

Stored as JSON at %LOCALAPPDATA%\\RealAssistant\\notes.json.
"""

import json
import uuid
from datetime import datetime

from config import NOTES_FILE


class Notes:
    def __init__(self, path=None):
        self.path = path or NOTES_FILE
        self.items = self._load()

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"[notes] couldn't read notes ({e}).")
        return []

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=2, ensure_ascii=False)
        tmp.replace(self.path)

    def add(self, text):
        text = (text or "").strip()
        if not text:
            return "Nothing to note."
        self.items.append({
            "id": uuid.uuid4().hex[:8],
            "text": text,
            "created": datetime.now().isoformat(timespec="seconds"),
        })
        self._save()
        return "Noted."

    def list(self, limit=20):
        return self.items[-limit:]

    def search(self, query):
        q = (query or "").lower().strip()
        if not q:
            return []
        return [n for n in self.items if q in n["text"].lower()]

    def remove(self, key):
        needle = (key or "").lower().strip()
        if not needle:
            return "Nothing to delete."
        before = len(self.items)
        self.items = [n for n in self.items if needle not in n["text"].lower()]
        removed = before - len(self.items)
        if removed:
            self._save()
        return f"Deleted {removed} note(s)." if removed else f"No note matching '{key}'."

    def clear(self):
        count = len(self.items)
        self.items = []
        self._save()
        return f"Cleared {count} note(s)."
