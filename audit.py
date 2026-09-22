"""
audit.py - a local record of every action the assistant took.

One JSON object per line in %LOCALAPPDATA%\\RealAssistant\\audit.log, so you can always
look back and see exactly what it did and what came back.
"""

import json
from datetime import datetime

from config import AUDIT_LOG


def log(tool, args, result, danger=False):
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "args": args if isinstance(args, dict) else {},
        "danger": bool(danger),
        "result": str(result)[:300],
    }
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def recent(limit=20):
    if not AUDIT_LOG.exists():
        return []
    try:
        lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for line in lines[-int(limit):]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
