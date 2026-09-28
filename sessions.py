"""
sessions.py - saved conversations for the desktop UI.

Each chat is one JSON file under %LOCALAPPDATA%\\RealAssistant\\sessions\\.
It holds the display messages plus the model's working "turns", so reopening a chat
keeps its context.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from config import DATA_DIR

SESSIONS_DIR = DATA_DIR / "sessions"


def _now():
    return datetime.now().isoformat(timespec="seconds")


class SessionStore:
    def __init__(self, path=None):
        self.dir = Path(path) if path else SESSIONS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def _file(self, sid):
        return self.dir / f"{sid}.json"

    def list(self):
        out = []
        for f in self.dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            out.append({
                "id": data.get("id", f.stem),
                "title": data.get("title") or "New chat",
                "updated": data.get("updated", ""),
                "count": len(data.get("messages", [])),
            })
        return sorted(out, key=lambda s: s["updated"], reverse=True)

    def create(self, title="New chat"):
        sid = uuid.uuid4().hex[:12]
        data = {"id": sid, "title": title, "created": _now(), "updated": _now(),
                "messages": [], "turns": []}
        self._write(sid, data)
        return data

    def load(self, sid):
        f = self._file(sid)
        if not f.exists():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception:
            return None

    def save(self, data):
        if not data or not data.get("id"):
            return None
        data["updated"] = _now()
        self._write(data["id"], data)
        return data

    def delete(self, sid):
        f = self._file(sid)
        if f.exists():
            f.unlink()
            return True
        return False

    def rename(self, sid, title):
        data = self.load(sid)
        if not data:
            return False
        data["title"] = title
        self.save(data)
        return True

    def _write(self, sid, data):
        f = self._file(sid)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(f)
