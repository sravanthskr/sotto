"""
ui_bridge.py - the JavaScript <-> Python bridge for the desktop app (pywebview).

Every method returns a JSON string. Streaming works by push-to-queue + poll:
the assistant runs on a background thread, appends events to a list, and the UI polls.
"""

import json
import os
import re
import threading
import time
import traceback
from pathlib import Path

import tools
import voice
import voice_convert
from config import MODEL_NAME, PROVIDERS
from core import Assistant
from sessions import SessionStore

LOG_FILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RealAssistant" / "ui.log"


def _log(msg):
    """Append one line to ui.log so any stall can be diagnosed after the fact."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            if LOG_FILE.stat().st_size > 2_000_000:
                LOG_FILE.unlink()
        except Exception:
            pass
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + str(msg)[:600] + "\n")
    except Exception:
        pass


def _status_rows(text):
    """Best-effort CPU/RAM/Battery bars from the one-line system_status string."""
    rows = []
    for m in re.finditer(r"\b(CPU|RAM|Battery|Disk)\b[^\d%]*(\d+)\s*%", text or ""):
        label, val = m.group(1), int(m.group(2))
        rows.append({"label": label, "value": min(100, val), "text": f"{val}%"})
    return rows


class Api:
    def __init__(self, on_ready=None):
        self.store = SessionStore()
        self.assistant = Assistant(on_text=self._on_text, on_tool=self._on_tool,
                                    on_learned=self._on_learned)
        self.session = None
        self._events = []
        self._lock = threading.Lock()
        self._busy = False
        self._thread = None

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        self.assistant.start()
        self.assistant.start_watcher()

    # ---- event queue (the UI polls this) -------------------------------
    def _push(self, event):
        _log(f"evt {event.get('type')} {str(event.get('text') or event.get('name') or '')[:90]!r}")
        with self._lock:
            self._events.append(event)

    def poll(self):
        with self._lock:
            events, self._events = self._events, []
        return json.dumps(events)

    def busy(self):
        return self._busy

    # ---- assistant callbacks -------------------------------------------
    def _on_text(self, chunk):
        self._push({"type": "text", "text": chunk})

    def _on_tool(self, name, args, result):
        event = {"type": "tool", "name": name, "result": str(result)}
        if name == "system_status":
            rows = _status_rows(str(result))
            if rows:
                event["rows"] = rows
        self._push(event)

    def _on_learned(self, facts):
        self._push({"type": "learned", "facts": list(facts)})

    # ---- sessions ------------------------------------------------------
    def list_sessions(self):
        return json.dumps(self.store.list())

    def new_session(self, title="New chat"):
        self.session = self.store.create(title or "New chat")
        self.assistant.turns = []
        return json.dumps(self.session)

    def open_session(self, sid):
        data = self.store.load(sid)
        if not data:
            return json.dumps(None)
        self.session = data
        self.assistant.turns = data.get("turns") or []
        return json.dumps(data)

    def delete_session(self, sid):
        self.store.delete(sid)
        if self.session and self.session.get("id") == sid:
            self.session = None
            self.assistant.turns = []
        return json.dumps(True)

    def rename_session(self, sid, title):
        return json.dumps(self.store.rename(sid, title))

    # ---- chat ----------------------------------------------------------
    def send(self, text):
        text = (text or "").strip()
        _log(f"send() called with {text[:120]!r}")
        if not text:
            return json.dumps({"ok": False})
        if self.session is None:
            self.session = self.store.create("New chat")
            self.assistant.turns = []
        self.session.setdefault("messages", []).append(
            {"role": "user", "text": text, "ts": time.time()})
        if self.session.get("title") in (None, "", "New chat"):
            self.session["title"] = text[:40]
            self._push({"type": "title", "title": self.session["title"]})
        self._busy = True
        self._thread = threading.Thread(target=self._run, args=(text,), daemon=True)
        self._thread.start()
        return json.dumps({"ok": True})

    def _run(self, text):
        try:
            reply = self.assistant.ask(text)
            if not (reply or "").strip():
                _log("EMPTY reply from ask() -> error event (turn never dies silently)")
                self._push({"type": "error",
                            "text": "I didn't get a usable response — one more try…"})
                return
            self.session.setdefault("messages", []).append(
                {"role": "assistant", "text": reply, "ts": time.time()})
            self.session["turns"] = self.assistant.turns
            self.store.save(self.session)
            self._push({"type": "done", "text": reply})
            self._push({"type": "session", "session": self.session})
        except Exception as e:
            msg = str(e)
            _log("ASK ERROR: " + traceback.format_exc()[:900])
            low = msg.lower()
            if any(k in low for k in ("provider", "llm", "503", "429", "timed out", "timeout", "unreachable", "connection")):
                short = "I couldn't reach my thinking service just now — trying again."
            else:
                short = "Something went wrong on my side — trying again."
            print("ask error:", msg)
            self._push({"type": "error", "text": short})
        finally:
            self._busy = False

    # ---- live listening (feeds the presence visual) ----------------
    def listen_start(self):
        from audio import MicStream
        self._mic = MicStream()
        self._mic.start()
        return json.dumps({"ok": True})

    def listen_level(self):
        mic = getattr(self, "_mic", None)
        try:
            return float(mic.level) if mic else 0.0
        except Exception:
            return 0.0

    def listen_stop(self):
        mic, self._mic = getattr(self, "_mic", None), None
        if mic is None:
            return json.dumps("")
        wav = mic.stop()
        text, err = voice.transcribe_wav(wav)
        _log(f"listen_stop -> {str(text)[:120]!r} err={err}")
        return json.dumps("" if err else (text or ""))

    def log(self, msg):
        _log("js: " + str(msg)[:300])
        return json.dumps(True)

    def set_voice(self, name):
        from config import save_setting
        return json.dumps(bool(save_setting("voice_name", name)))

    # ---- optional extras (the UI capability-gates on these) ------------
    def status(self):
        try:
            import ai_engine
            active = (getattr(ai_engine, "_STATE", {}) or {}).get("active")
        except Exception:
            active = None
        return json.dumps({"online": True, "provider": active or MODEL_NAME, "state": "ready"})

    def stop_speaking(self):
        try:
            voice.stop_speaking()
        except Exception:
            pass
        return json.dumps(True)

    def list_memory(self):
        try:
            rows = [{"title": f} for f in self.assistant.memory.facts()]
        except Exception:
            rows = []
        return json.dumps(rows)

    def list_notes(self):
        try:
            items = self.assistant.notes.list(50)
            rows = [{"title": n.get("text", ""), "when": n.get("created")} for n in reversed(items)]
        except Exception:
            rows = []
        return json.dumps(rows)

    def list_tasks(self):
        try:
            rows = [{"title": r.get("message", ""), "when": r.get("due")}
                    for r in self.assistant.reminders.list()]
        except Exception:
            rows = []
        return json.dumps(rows)

    def list_activity(self):
        try:
            import audit
            rows = [{"title": f'{e.get("tool", "action")} — {str(e.get("result", ""))[:90]}',
                     "when": e.get("ts")} for e in reversed(audit.recent(30))]
        except Exception:
            rows = []
        return json.dumps(rows)

    def set_sound(self, on):
        from config import save_setting
        return json.dumps(bool(save_setting("sound_effects", bool(on))))

    def set_wake(self, on):
        from config import save_setting
        return json.dumps(bool(save_setting("wake_word", bool(on))))

    def say_slow(self, text):
        try:
            return json.dumps({"ok": bool(voice.speak(text, rate=-3))})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ---- side panels ---------------------------------------------------
    def info(self):
        return json.dumps({
            "model": MODEL_NAME,
            "apps": len(tools.APP_INDEX),
            "memory": self.assistant.memory.facts(),
            "notes": [n["text"] for n in self.assistant.notes.list(50)],
            "reminders": self.assistant.reminders.list(),
            "voices": voice.list_voices(),
            "current_voice": voice.default_voice(),
            "custom_voices": voice_convert.available_voices(),
            "providers": [
                {"name": p["name"], "model": p.get("model", ""),
                 "key": bool(os.environ.get(p.get("api_key_env", ""), "").strip())}
                for p in PROVIDERS],
        })

    # ---- voice ---------------------------------------------------------
    def listen(self):
        try:
            return json.dumps({"text": voice.listen_once(6) or ""})
        except Exception as e:
            return json.dumps({"text": "", "error": str(e)})

    def say(self, text):
        try:
            return json.dumps({"ok": bool(voice.speak(text))})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
