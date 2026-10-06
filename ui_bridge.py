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
_SENT_RE = re.compile(r'[.!?…]{1,3}\s')


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


_META_PATTERNS = (
    "the user is asking", "the user wants", "the user said", "the user might",
    "the user asks", "i should", "i need to", "i can't rewrite", "provided a draft",
    "see a draft", "draft to rewrite", "no draft", "rewrite the draft", "meta-commentary", "the instruction says",
    "looking at the conversation", "first user message", "let me think about",
    "let me use", "let me check", "i will use", "i can use", "as the final reply",
    "not mention", "step 1:",
)


class Api:
    def __init__(self, on_ready=None):
        self.store = SessionStore()
        self.assistant = Assistant(on_text=self._on_text, on_tool=self._on_tool,
                                    on_learned=self._on_learned, on_status=self._on_status,
                                    on_confirm=self._confirm_cb)
        self.session = None
        self._events = []
        self._lock = threading.Lock()
        self._busy = False
        self._thread = None
        self._buf = ""
        self._speak_muted = False
        self._last_reply = ""
        self._last_status = None
        self._turn_checked = False
        self._turn_leak = False
        self._tts = False               # True while a say()/say_slow() call is speaking
        self._wake_on = False           # wake-word listener enabled (in-memory switch)
        self._wake_thread = None
        self._wake_hold = 0.0
        from config import load_settings as _ls
        self._overlay_enabled = bool(_ls().get("overlay_enabled", True))
        self._voice_active = False
        self._voice_stop_req = False
        self._voice_cancel_req = False
        self._overlay_window = None
        self._main_window = None
        # floating-overlay snapshot (read by the overlay pill + its controller)
        self._ov_detail = ""
        self._ov_said = ""
        self._ov_final = ""
        self._ov_err = ""
        self._ov_done_ts = 0.0
        self._ov_err_ts = 0.0
        self._ov_ts = 0.0
        self._theme = "light"
        self._confirm = None            # pending destructive-action gate
        self._interrupted_ts = 0.0      # last time speech was cut off
        self._ov_mic = None             # pill-owned microphone stream
        self._ov_listen = False         # pill is currently listening
        self._ov_turn = False           # current turn was started from the pill

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        self.assistant.start()
        self.assistant.start_watcher()

    # ---- event queue (the UI polls this) -------------------------------
    def _push(self, event):
        _log(f"evt {event.get('type')} {str(event.get('text') or event.get('name') or '')[:90]!r}")
        try:
            self._ov_note(event)
        except Exception:
            pass
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
        """Buffer streamed text and flush it as whole sentences, so speech
        starts with the first sentence instead of waiting for the whole reply."""
        self._buf += chunk
        while True:
            m = _SENT_RE.search(self._buf)
            if m and m.end() >= 2:
                sentence, self._buf = self._buf[:m.end()].strip(), self._buf[m.end():]
                if sentence:
                    self._flush_say(sentence)
                continue
            if len(self._buf) > 220:
                cut = self._buf.rfind(" ", 0, 200)
                if cut > 40:
                    piece, self._buf = self._buf[:cut].strip(), self._buf[cut + 1:]
                    if piece:
                        self._flush_say(piece)
                    continue
            break

    def _flush_say(self, text):
        text = (text or "").strip()
        if not text:
            return
        low = text.lower()
        if any(m in low for m in ("<tool_call", "<function=", "<parameter=")) or (
                low.lstrip().startswith("{") and ('"arguments"' in low or '"args"' in low)
                and ('"name"' in low or '"tool"' in low or '"function"' in low) and len(low) < 1200):
            self._turn_leak = True
            _log("leak-guard: holding back XML tool-call text")
        self._turn_checked = True
        if any(m in low for m in _META_PATTERNS):
            self._turn_leak = True
            _log("leak-guard: holding back planning text")
        if self._turn_leak:
            return
        if self._ov_turn:
            # pill-originated turn: the bridge owns speech (the hidden main
            # window's JS may be throttled and must not double-speak)
            self._push({"type": "text", "text": text + " "})
            if not self._speak_muted:
                self._speak_now(text)
            return
        kind = "text" if self._speak_muted else "say"
        self._push({"type": kind, "text": text + " "})

    def _speak_now(self, text):
        self._tts = True
        try:
            voice.speak(text)
        except Exception as e:
            _log(f"ov speak: {type(e).__name__}: {e}")
        finally:
            self._tts = False

    def _on_status(self, state):
        if state == self._last_status:
            return
        self._last_status = state
        if state == "thinking":
            self._push({"type": "state", "name": "thinking", "label": "Thinking."})

    def _tool_confirm(self, name, result):
        """Remember a clean human confirmation for a tool that just ran."""
        try:
            res = str(result or "").strip()
            confirm = res if (res and len(res) <= 160) else "Done - " + name.replace("_", " ")
            if not hasattr(self, "_turn_tools"):
                self._turn_tools = []
            self._turn_tools.append(confirm)
        except Exception:
            pass

    def _on_tool(self, name, args, result):
        self._push({"type": "state", "name": "acting", "label": "Working on it…"})
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
        self._wake_hold = max(getattr(self, "_wake_hold", 0.0), time.time() + 1.5)
        _log(f"send() called with {text[:120]!r}")
        if not text:
            return json.dumps({"ok": False})
        self._buf = ""
        self._speak_muted = False
        self._last_status = None
        self._turn_checked = False
        self._turn_leak = False
        self._ov_reset_turn()
        self._turn_tools = []
        low = text.lower().strip(" .!?")
        if self._last_reply and low in ("repeat that", "say that again", "say it again", "repeat", "again", "repeat it"):
            self._start_replay({"type": "speak_only", "text": self._last_reply})
            return json.dumps({"ok": True})
        if self._last_reply and low in ("say it slower", "speak slower", "slower", "slow down"):
            self._start_replay({"type": "speak_only", "text": self._last_reply, "rate": 0.8})
            return json.dumps({"ok": True})
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

    def _start_replay(self, event):
        """Replay the last answer by voice — no LLM call, instant."""
        def run():
            try:
                self._push(event)
                self._push({"type": "done", "text": "", "full": "", "followups": []})
            finally:
                self._busy = False
        self._busy = True
        threading.Thread(target=run, daemon=True).start()

    def _repair(self, draft):
        """A weak model leaked planning/meta text - rewrite it into a clean answer."""
        import ai_engine
        self._turn_checked = True
        draft = (draft or "").strip()
        try:
            import re as _re
            draft = _re.sub(r"<tool_call[\s\S]*?|<function=[\s\S]*?</function>", " ", draft).strip()
        except Exception:
            pass
        _log(f"repair: rewriting planning-leaked reply (draft len={len(draft)})")
        fallback = "Sorry - that got tangled on my side. Could you say that again?"
        self._turn_leak = False
        fixed = ""
        if len(draft) >= 12:
            try:
                fixed = (ai_engine.complete([
                    {"role": "system", "content": "You are Sotto's reply editor. You receive a messy internal note. Reply ONLY with the assistant's final answer to the user: 1-2 short, plain, first-person sentences. No planning, no meta talk, no quoting of instructions."},
                    {"role": "user", "content": "Internal note:\n" + draft[:1500]},
                ], max_tokens=220) or "").strip()
            except Exception as e:
                _log(f"repair failed: {e}")
        low_fixed = fixed.lower()
        if (not fixed) or any(m in low_fixed for m in _META_PATTERNS):
            fixed = fallback
            _log("repair: using fallback line")
        self._flush_say(fixed)
        return fixed

    def _run(self, text):
        try:
            reply = self.assistant.ask(text)
            rem, self._buf = self._buf.strip(), ""
            if rem:
                self._flush_say(rem)
            if self._turn_leak:
                reply = self._repair(reply or "")
            if not (reply or "").strip():
                if getattr(self, "_turn_tools", None):
                    reply = self._turn_tools[-1]
                    _log(f"empty final text after tools -> confirmation: {reply[:80]!r}")
                    try:
                        self._flush_say(reply)
                    except Exception:
                        pass
                else:
                    _log("EMPTY reply from ask() -> one server-side retry")
                    try:
                        time.sleep(0.8)
                        reply = self.assistant.ask(text) or ""
                    except Exception as _e2:
                        _log(f"retry ask failed: {_e2}")
                        reply = ""
                    if (reply or "").strip():
                        rem2, self._buf = self._buf.strip(), ""
                        if rem2:
                            self._flush_say(rem2)
                        if self._turn_leak:
                            reply = self._repair(reply or "")
                    else:
                        _log("EMPTY reply after retry -> error event (turn never dies silently)")
                        self._push({"type": "error",
                                    "text": "I didn't get a usable response - one more try..."})
                        return
            self._last_reply = reply
            self.session.setdefault("messages", []).append(
                {"role": "assistant", "text": reply, "ts": time.time()})
            self.session["turns"] = self.assistant.turns
            self.store.save(self.session)
            self._push({"type": "done", "text": "", "full": reply})
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
            self._ov_turn = False

    # ---- live listening (feeds the presence visual) ----------------
    def listen_start(self):
        from audio import MicStream
        self._mic = MicStream()
        self._mic.start()
        return json.dumps({"ok": True})

    def listen_level(self):
        mic = getattr(self, "_ov_mic", None) or getattr(self, "_mic", None)
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

    def voice_turn(self):
        """Hands-free listen cycle (server-side): records until you stop
        talking, then transcribes and runs the turn. Used by the pill,
        the global hotkey and the in-app mic button."""
        if self._busy or getattr(self, "_tts", False):
            if getattr(self, "_tts", False):
                self._speak_muted = True
                try:
                    self.stop_speaking()
                except Exception:
                    pass
                self._play_cue("stop")
                _log("voice_turn: interrupted speech -> will listen when idle")
                threading.Thread(target=self._listen_when_idle, daemon=True).start()
                return json.dumps(True)
            self._push({"type": "notice", "text": "Still on the last thing - one second."})
            self._push({"type": "state", "name": "idle"})
            return json.dumps(False)
        if getattr(self, "_voice_active", False):
            return json.dumps(True)
        self._voice_active = True
        self._voice_stop_req = False
        self._voice_cancel_req = False
        _log("voice_turn: start")
        try:
            self.stop_speaking()
        except Exception:
            pass
        self._push({"type": "state", "name": "listening"})

        def worker():
            text, err = "", None
            cap = None
            try:
                from audio import VoiceCapture
                self._wake_hold = time.time() + 4.0
                time.sleep(0.1)   # settle before capturing
                try:
                    from config import load_settings as _lset
                    _s = _lset()
                except Exception:
                    _s = {}
                end_sil = float(_s.get("voice_end_silence", 0.9) or 0.9)
                vad_mode = int(_s.get("vad_mode", 2) or 2)
                cap = VoiceCapture(end_silence=end_sil, vad_mode=vad_mode, max_len=18.0)
                cap.start(should_stop=lambda: bool(self._voice_stop_req or self._voice_cancel_req))
                self._mic = cap
                # who owns the spoken reply? the pill/hidden case speaks itself
                try:
                    import ctypes as _c
                    u = _c.windll.user32
                    hwnd = u.FindWindowW(None, "Sotto")
                    fg = u.GetForegroundWindow()
                    vis = bool(hwnd) and u.IsWindowVisible(hwnd) and not u.IsIconic(hwnd)
                    self._ov_turn = not (vis and fg == hwnd)
                except Exception:
                    self._ov_turn = True
                cap.wait()
                wav = cap.stop()
                if not self._voice_cancel_req and cap.heard:
                    text, err = voice.transcribe_wav(wav)
                st = cap.stats or {}
                _log(f"voice_turn: stop heard={cap.heard} cancel={self._voice_cancel_req} "
                     f"vad={st.get('vad')} dur={st.get('dur')} peak={st.get('peak')} "
                     f"text={str(text)[:110]!r} err={err}")
                if (not text) and (not self._voice_cancel_req) and not cap.error \
                        and float(st.get("dur") or 0) < 2.6:
                    try:
                        self._play_cue("wake")
                        cap2 = VoiceCapture(end_silence=end_sil, vad_mode=vad_mode)
                        cap2.start(should_stop=lambda: bool(self._voice_stop_req or self._voice_cancel_req))
                        self._mic = cap2
                        cap2.wait()
                        wav2 = cap2.stop()
                        if not self._voice_cancel_req and cap2.heard:
                            text, err = voice.transcribe_wav(wav2)
                        st2 = cap2.stats or {}
                        _log(f"voice_turn retry: heard={cap2.heard} dur={st2.get('dur')} "
                             f"text={str(text)[:110]!r} err={err}")
                    except Exception:
                        pass
            except Exception as e:
                _log(f"voice_turn error: {type(e).__name__}: {e}")
            finally:
                self._mic = None
                self._voice_active = False
                self._voice_stop_req = False
            if self._voice_cancel_req:
                self._voice_cancel_req = False
                self._push({"type": "state", "name": "idle"})
                return
            text = (text or "").strip()
            if not text:
                _caperr = ""
                try:
                    _caperr = (cap.error if cap else "") or ""
                except Exception:
                    _caperr = ""
                msg = "Microphone hiccup - I couldn't hear just now." if _caperr else "I didn't quite catch that."
                self._push({"type": "notice", "text": msg})
                self._push({"type": "state", "name": "idle"})
                return
            self._push({"type": "user_text", "text": text})
            self._ov_turn = True
            self.send(text)

        import threading
        threading.Thread(target=worker, daemon=True).start()
        return json.dumps(True)

    def voice_stop(self):
        """Finish now: stop recording early and process what was said."""
        self._voice_stop_req = True
        return json.dumps(True)

    def voice_cancel(self):
        """Abort the capture without sending anything."""
        self._voice_cancel_req = True
        self._voice_stop_req = True
        return json.dumps(True)

    def log(self, msg):
        _log("js: " + str(msg)[:300])
        return json.dumps(True)

    def set_voice(self, name):
        from config import save_setting
        import config
        name = str(name or "").strip()
        if name.lower().endswith("(custom)"):
            base = name[: -len("(custom)")].strip().lower()
            import voice_convert
            if base in voice_convert.available_voices():
                save_setting("custom_voice", base)
                config.CUSTOM_VOICE = base
                voice_convert.prewarm()
                _log(f"set_voice -> custom '{base}'")
                return json.dumps(True)
            return json.dumps(False)
        # a system voice was chosen: plain SAPI path, custom pipeline off
        save_setting("custom_voice", "")
        config.CUSTOM_VOICE = ""
        ok = bool(save_setting("voice_name", name))
        _log(f"set_voice -> system '{name}' ok={ok}")
        return json.dumps(ok)

    # ---- optional extras (the UI capability-gates on these) ------------
    def status(self):
        try:
            import ai_engine
            active = (getattr(ai_engine, "_STATE", {}) or {}).get("active")
        except Exception:
            active = None
        return json.dumps({"online": True, "provider": active or MODEL_NAME, "state": "ready"})

    def stop_speaking(self):
        self._speak_muted = True
        self._interrupted_ts = time.time()
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

    def scan_apps(self):
        import time as _t
        t0 = _t.time()
        try:
            tools.build_app_index()
            count = len(tools.APP_INDEX)
            from config import save_setting
            save_setting("scan_done", True)
            save_setting("scan_count", count)
            took = round(_t.time() - t0, 2)
            _log(f"scan_apps: {count} apps in {took}s")
            return json.dumps({"count": count, "took": took})
        except Exception as e:
            _log(f"scan_apps failed: {e}")
            return json.dumps({"count": 0, "took": 0, "error": str(e)[:150]})

    # ---- App Lock & Security -------------------------------------------
    def get_lock_status(self):
        from config import load_settings
        s = load_settings()
        enabled = bool(s.get("voice_lock_enabled", False))
        phrase = str(s.get("voice_lock_phrase", "") or "")
        has_phrase = bool(phrase.strip())
        has_pwd = bool(str(s.get("lock_password", "") or "").strip())
        # A lock is only active when the user finished setting it up
        # (enabled + spoken passphrase). A half-configured lock never locks.
        if enabled and not has_phrase:
            try:
                from config import save_setting
                save_setting("voice_lock_enabled", False)
                _log("lock state enabled without a passphrase - auto-disabled")
            except Exception as e:
                _log(f"lock auto-disable failed: {e}")
            enabled = False
        return json.dumps({
            "enabled": enabled,
            "has_phrase": has_phrase,
            "has_password": has_pwd,
            "phrase_hint": (phrase[:3] + "..." + phrase[-2:]) if len(phrase) > 5 else "Set"
        })

    def verify_voice_lock(self, spoken_text):
        from config import load_settings
        s = load_settings()
        if not s.get("voice_lock_enabled", False):
            return json.dumps({"ok": True})
        
        target = str(s.get("voice_lock_phrase", "") or "").strip().lower()
        if not target:
            return json.dumps({"ok": True})
        
        spoken = str(spoken_text or "").strip().lower()
        if not spoken:
            return json.dumps({"ok": False})
        
        # Clean punctuation
        import re
        target_clean = re.sub(r"[^\w\s]", "", target)
        spoken_clean = re.sub(r"[^\w\s]", "", spoken)
        
        # Substring or word overlap matching
        if target_clean in spoken_clean:
            return json.dumps({"ok": True})
        
        target_words = set(target_clean.split())
        spoken_words = set(spoken_clean.split())
        if target_words and spoken_words:
            overlap = len(target_words & spoken_words) / float(len(target_words))
            if overlap >= 0.7:
                return json.dumps({"ok": True})
                
        return json.dumps({"ok": False})

    def verify_password_lock(self, password_text):
        from config import load_settings
        s = load_settings()
        stored_pwd = str(s.get("lock_password", "") or "").strip()
        pwd = str(password_text or "").strip()
        
        # No fallback password stored: only fine while the lock is off.
        # If a lock is active, refuse and point to the Windows-verified reset.
        if not stored_pwd:
            if not bool(s.get("voice_lock_enabled", False)):
                return json.dumps({"ok": True})
            return json.dumps({"ok": False, "error": "No fallback password is set. Use 'Forgot passphrase?' to reset with your Windows sign-in."})
            
        return json.dumps({"ok": (pwd == stored_pwd)})

    def set_lock_settings(self, curr_password, enabled, phrase, new_password):
        from config import load_settings, save_setting
        s = load_settings()
        stored_pwd = str(s.get("lock_password", "") or "").strip()
        
        # Verify current password if a lock or password was previously enabled/set
        if stored_pwd and str(curr_password or "").strip() != stored_pwd:
            return json.dumps({"ok": False, "error": "Incorrect verification password."})
            
        phrase_val = str(phrase or "").strip()
        new_pwd_val = str(new_password or "").strip() if new_password is not None else stored_pwd
        
        if enabled and not phrase_val:
            return json.dumps({"ok": False, "error": "Please provide a spoken passphrase for the voice lock."})
            
        if enabled and not new_pwd_val and not stored_pwd:
            return json.dumps({"ok": False, "error": "Please set a fallback text password."})
            
        save_setting("voice_lock_enabled", bool(enabled))
        save_setting("voice_lock_phrase", phrase_val)
        if new_password is not None and str(new_password).strip():
            save_setting("lock_password", str(new_password).strip())
            
        _log(f"set_lock_settings -> enabled={enabled}")
        return json.dumps({"ok": True})

    def sys_verify_for_reset(self, reason=""):
        """Verify the user with the Windows sign-in (Hello / PIN / password).
        Used to reset a forgotten voice lock."""
        try:
            import sysauth
            r = sysauth.verify_windows_identity(reason or "Reset the Sotto voice lock")
            if r.get("ok"):
                import time as _t
                self._reset_verified_until = _t.time() + 300
            _log(f"sys_verify_for_reset -> ok={r.get('ok')} method={r.get('method', '')}")
            return json.dumps(r)
        except Exception as e:
            _log(f"sys_verify_for_reset failed: {e}")
            return json.dumps({"ok": False, "detail": f"Could not start verification: {str(e)[:120]}"})

    def reset_voice_lock(self, mode, new_phrase="", new_password=""):
        """Reset the voice lock after a successful Windows-identity check.
        mode='remove' disables the lock; mode='update' sets a new passphrase.
        Nothing else is deleted or changed."""
        import time as _t
        if _t.time() > float(getattr(self, "_reset_verified_until", 0)):
            return json.dumps({"ok": False, "error": "Please verify with your Windows sign-in first."})
        from config import save_setting
        mode = str(mode or "").strip().lower()
        if mode == "remove":
            save_setting("voice_lock_enabled", False)
            save_setting("voice_lock_phrase", "")
            save_setting("lock_password", "")
            self._reset_verified_until = 0
            _log("reset_voice_lock -> lock removed via Windows-verified reset")
            return json.dumps({"ok": True})
        if mode == "update":
            phrase = str(new_phrase or "").strip()
            if not phrase:
                return json.dumps({"ok": False, "error": "The new passphrase is empty."})
            save_setting("voice_lock_phrase", phrase)
            save_setting("voice_lock_enabled", True)
            pwd = str(new_password or "").strip()
            if pwd:
                save_setting("lock_password", pwd)
            self._reset_verified_until = 0
            _log("reset_voice_lock -> passphrase updated via Windows-verified reset")
            return json.dumps({"ok": True})
        return json.dumps({"ok": False, "error": "Unknown reset mode."})

    # ---- accounts (Phase 1) --------------------------------------------
    # Credentials are entered in the app's Settings sheet and travel only to this
    # process - they are never accepted through model tool calls.
    def connect_email(self, address, password):
        import mail
        addr = str(address or "").strip()
        _log(f"connect_email {addr}")
        return json.dumps(mail.connect(addr, str(password or "")))

    def disconnect_email(self):
        import accounts
        accounts.clear_email_account()
        return json.dumps(True)

    def connect_calendar_ics(self, url):
        import accounts
        import calendar_api
        url = str(url or "").strip()
        if not url:
            return json.dumps("Error: paste the ICS link first.")
        try:
            text = calendar_api._fetch(url)
            n = len(calendar_api.parse_events(text))
            accounts.set_ics(url)
            return json.dumps(f"Calendar linked - {n} events found.")
        except Exception as e:
            return json.dumps(f"Error: couldn't read that link ({str(e)[:120]}).")

    def google_connect(self):
        import calendar_api
        import threading
        if not calendar_api.google_configured():
            return json.dumps("Google hasn't been set up yet - open 'Google setup (owner)' in Settings -> Accounts first.")
        threading.Thread(target=calendar_api.start_google_oauth, daemon=True).start()
        return json.dumps("Browser opened - finish the Google sign-in there.")

    def set_google_credentials(self, client_id, client_secret):
        from config import save_setting
        cid = str(client_id or "").strip()
        sec = str(client_secret or "").strip()
        if not cid or not sec:
            return json.dumps("Error: paste both the client id and the client secret.")
        save_setting("google_client_id", cid)
        save_setting("google_client_secret", sec)
        _log("set_google_credentials updated (values intentionally not logged)")
        return json.dumps("Saved. Now click Connect on the Google account row and sign in once.")

    def google_setup_hint(self):
        try:
            from config import load_settings
            s = load_settings() or {}
            cid = str(s.get("google_client_id") or "")
            return json.dumps({"client_id": cid, "has_secret": bool(s.get("google_client_secret"))})
        except Exception:
            return json.dumps({})

    def accounts_status(self):
        import accounts
        return json.dumps(accounts.status_lines())

    def disconnect_google(self):
        import accounts
        accounts.clear_oauth("google")
        _log("disconnect_google")
        return json.dumps(True)

    def disconnect_calendar(self):
        import accounts
        accounts.clear_ics()
        _log("disconnect_calendar")
        return json.dumps(True)

    def set_sound(self, on):
        from config import save_setting
        return json.dumps(bool(save_setting("sound_effects", bool(on))))

    def set_wake(self, on):
        """Toggle the hands-free wake word ("hey sotto"). Starts/stops the
        listener live; persists to wake_word_enabled (NOT wake_word, which
        holds the spoken phrase)."""
        from config import save_setting
        on = bool(on)
        ok = bool(save_setting("wake_word_enabled", on))
        if on:
            self._maybe_start_wake()
        else:
            self._wake_on = False
        _log(f"set_wake -> {on} ok={ok}")
        return json.dumps(ok)

    def set_wake_word(self, phrase):
        """Update the wake phrase live (the listener re-reads it each cycle)."""
        from config import save_setting
        phrase = str(phrase or "hey sotto").strip() or "hey sotto"
        ok = bool(save_setting("wake_word", phrase))
        _log(f"set_wake_word -> {phrase!r} ok={ok}")
        return json.dumps({"ok": ok})
    def say_slow(self, text):
        self._tts = True
        try:
            return json.dumps({"ok": bool(voice.speak(text, rate=-3))})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
        finally:
            self._tts = False

    # ---- side panels ---------------------------------------------------
    def info(self):
        import config
        custom = voice_convert.available_voices()
        voices = list(voice.list_voices())
        for c in custom:
            voices.append(c.title() + " (custom)")
        current = voice.default_voice()
        if config.CUSTOM_VOICE and config.CUSTOM_VOICE in custom:
            current = config.CUSTOM_VOICE.title() + " (custom)"
        return json.dumps({
            "model": MODEL_NAME,
            "apps": len(tools.APP_INDEX),
            "scan_needed": not bool(config.load_settings().get("scan_done")),
            "wake_enabled": bool(config.load_settings().get("wake_word_enabled")),
            "wake_word": str(config.load_settings().get("wake_word") or "hey sotto"),
            "overlay_enabled": bool(self._overlay_enabled),
            "memory": self.assistant.memory.facts(),
            "notes": [n["text"] for n in self.assistant.notes.list(50)],
            "reminders": self.assistant.reminders.list(),
            "voices": voices,
            "current_voice": current,
            "custom_voices": custom,
            "providers": [
                {"name": p["name"], "model": p.get("model", ""),
                 "key": bool(os.environ.get(p.get("api_key_env", ""), "").strip())}
                for p in PROVIDERS],
        })

    # ---- window overlay & global hotkey -------------------------------
    def set_window(self, window):
        self._window = window
        self._start_global_hotkey()
        self._maybe_start_wake()

    def _show_window(self):
        w = getattr(self, "_window", None)
        if not w:
            return
        try:
            w.restore()
            w.show()
        except Exception:
            pass
        try:
            import ctypes
            hwnd = ctypes.windll.user32.FindWindowW(None, w.title)
            if hwnd:
                # A background process isn't allowed to grab focus directly;
                # the tap of the Alt key makes Windows permit it.
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _activate_visual(self):
        """Where an activation (hotkey / wake word) becomes visible. With the
        overlay on, the floating pill is the interface and the main window
        stays exactly where the user left it; without it, open the window."""
        if self._overlay_enabled:
            return
        self._show_window()

    def _start_global_hotkey(self):
        """Register native Windows global hotkey Ctrl+Space on background thread."""
        import threading
        import ctypes
        from ctypes import wintypes
        
        def _hotkey_loop():
            try:
                user32 = ctypes.windll.user32
                HOTKEY_ID = 101
                MOD_CONTROL = 0x0002
                VK_SPACE = 0x20
                
                ok1 = bool(user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL, VK_SPACE))
                HOTKEY_ID2 = 102
                MOD_SHIFT = 0x0004
                VK_S = 0x53
                ok2 = bool(user32.RegisterHotKey(None, HOTKEY_ID2, MOD_CONTROL | MOD_SHIFT, VK_S))
                _log(f"hotkeys registered: Ctrl+Space={ok1} Ctrl+Shift+S={ok2}")
                if not ok1 and not ok2:
                    return
                
                msg = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    if msg.message == 0x0312:  # WM_HOTKEY
                        _log("Global hotkey pressed")
                        try:
                            if getattr(self, "_voice_active", False):
                                self.voice_stop()
                            else:
                                if not self._overlay_enabled:
                                    self._activate_visual()
                                self.voice_turn()
                        except Exception as e:
                            _log(f"hotkey voice error: {e}")
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception as e:
                _log(f"hotkey_loop error: {e}")

        threading.Thread(target=_hotkey_loop, daemon=True).start()

    # ---- wake word (hands-free activation) ------------------------------
    def _maybe_start_wake(self):
        """Start the background wake-word listener if enabled in settings."""
        from config import load_settings
        if not load_settings().get("wake_word_enabled"):
            return
        t = self._wake_thread
        if t is not None and t.is_alive():
            self._wake_on = True     # revive if it was signalled to stop
            return
        self._wake_on = True
        self._wake_thread = threading.Thread(target=self._wake_loop, daemon=True)
        self._wake_thread.start()
        _log("wake-word listener started")

    def _main_visible(self):
        """True while the main Sotto window is on screen (its JS is alive)."""
        try:
            import ctypes
            from overlay_win import _main_hwnd
            h = _main_hwnd()
            if not h:
                return False
            u = ctypes.windll.user32
            return bool(u.IsWindowVisible(h)) and not bool(u.IsIconic(h))
        except Exception:
            return True

    def _listen_and_send(self):
        """Hidden-window command capture: listen once, then run the turn
        server-side (the main window's JS may be throttled while hidden)."""
        try:
            from audio import VoiceCapture
            try:
                from config import load_settings as _lset
                _s = _lset()
            except Exception:
                _s = {}
            end_sil = float(_s.get("voice_end_silence", 0.9) or 0.9)
            vad_mode = int(_s.get("vad_mode", 2) or 2)
            self._wake_hold = time.time() + 4.0
            cap = VoiceCapture(end_silence=end_sil, vad_mode=vad_mode, max_len=18.0)
            self._ov_listen = True
            self._ov_mic = cap
            self._push({"type": "state", "name": "listening"})
            cap.wait()
            wav = cap.stop()
            if not cap.heard:
                self._push({"type": "notice", "text": "I didn't quite catch that."})
                self._push({"type": "state", "name": "idle"})
                return
            text, err = voice.transcribe_wav(wav)
            text = (text or "").strip()
            if not text:
                _caperr = ""
                try:
                    _caperr = (cap.error if cap else "") or ""
                except Exception:
                    _caperr = ""
                msg = "Microphone hiccup - I couldn't hear just now." if _caperr else "I didn't quite catch that."
                self._push({"type": "notice", "text": msg})
                self._push({"type": "state", "name": "idle"})
                return
            self._push({"type": "user_text", "text": text})
            self._ov_turn = True
            self.send(text)
        except Exception as e:
            _log(f"listen_and_send error: {type(e).__name__}: {e}")
        finally:
            self._ov_mic = None
            self._ov_listen = False

    def _play_cue(self, which="wake"):
        """Play a clean production-style cue; fall back to a soft beep."""
        try:
            import winsound
            import os as _os
            base = _os.path.dirname(_os.path.abspath(__file__))
            f = _os.path.join(base, "assets", "chime_up.wav" if which == "wake" else "chime_down.wav")
            if _os.path.exists(f):
                winsound.PlaySound(f, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                _log(f"cue {which}: file")
                return
        except Exception:
            pass
        try:
            import winsound
            winsound.Beep(1046 if which == "wake" else 659, 90)
            _log(f"cue {which}: beep")
        except Exception:
            pass

    def _wake_match(self, low):
        """Find the wake phrase; returns (phrase, index) or (None, -1)."""
        try:
            from config import load_settings as _ls
            w = str(_ls().get("wake_word", "hey sotto") or "hey sotto").strip().lower()
        except Exception:
            w = "hey sotto"
        phrases = []
        if w:
            phrases.append(w)
        for extra in ("hey sotto", "hey soto", "hey sato", "hey shato", "hey shoto",
                      "ok sotto", "ok soto", "ok sato", "okay sotto", "okay soto", "okay sato",
                      "hi sotto", "hi sato", "sotto", "soto", "sato", "shato", "shoto", "satoh", "soda"):
            if extra not in phrases:
                phrases.append(extra)
        for ph in phrases:
            i = low.find(ph)
            if i >= 0:
                return ph, i
        try:
            import difflib
            import re as _re2
            for m in _re2.finditer(r"[a-z']+", low):
                wrd = m.group(0)
                if len(wrd) < 4:
                    continue
                for tgt in ("sotto", "soto", "sato", "shato", "shoto"):
                    if difflib.SequenceMatcher(None, wrd, tgt).ratio() >= 0.75:
                        return wrd, m.start()
        except Exception:
            pass
        return None, -1

    def _best_rest(self, text, phrase):
        """Largest non-wake fragment of a transcript (handles repeated wake words)."""
        import re as _re4
        try:
            parts = _re4.split(_re4.escape(phrase), text, flags=_re4.IGNORECASE)
        except Exception:
            parts = [text]
        wake_words = {"hey", "hi", "ok", "okay", "hello", "yo", "sotto", "soto", "sato",
                      "shato", "shoto", "satoh", "soda", "a", "the"}
        best = ""
        for p in parts:
            p = p.strip(" ,.!?;:-")
            if len(p) < 2:
                continue
            words = [wd.strip(",.!?;:-") for wd in p.lower().split()]
            if words and all(wd in wake_words for wd in words):
                continue
            if len(p.split()) > len(best.split()):
                best = p
        return best

    def _listen_when_idle(self, send_text=None):
        """After an interrupt: wait for the current turn to wind down, then act."""
        t0 = time.time()
        while time.time() - t0 < 25:
            if not self._busy and not getattr(self, "_voice_active", False) and not getattr(self, "_tts", False):
                break
            time.sleep(0.3)
        try:
            self._speak_muted = False
            if send_text:
                self._push({"type": "user_text", "text": send_text})
                self._ov_turn = True
                self.send(send_text)
            else:
                self.voice_turn()
        except Exception as e:
            _log(f"listen_when_idle error: {e}")

    def _tts_monitor_once(self):
        """While Sotto is speaking: listen for stop-words or a new wake request."""
        if getattr(self, "_ov_mic", None) or getattr(self, "_mic", None):
            time.sleep(0.3)
            return
        try:
            from audio import VoiceCapture
            try:
                from config import load_settings as _lset
                _s = _lset()
            except Exception:
                _s = {}
            vad_mode = int(_s.get("vad_mode", 3) or 3)
            cap = VoiceCapture(end_silence=0.5, no_speech_timeout=1800.0, max_len=3.2, vad_mode=vad_mode)
            cap.start(should_stop=lambda: bool(not self._tts or not self._wake_on))
            cap.wait(30.0)
            if not cap._done.is_set():
                cap.stop_now()
            wav = cap.stop()
            if not cap.heard or not self._tts or not self._wake_on:
                return
            txt, _e = voice.transcribe_wav(wav)
            text = (txt or "").strip()
            if not text:
                return
            low = " ".join(text.lower().strip(" .,!?;:-").split())
            if not low:
                return
            _log(f"voice: monitor heard {low[:60]!r}")
            spoken = ((getattr(self, "_ov_said", "") or "") + ". " + (getattr(self, "_ov_final", "") or "")).lower()
            if spoken.strip(" ."):
                try:
                    import difflib as _df
                    for seg in spoken.split("."):
                        seg = " ".join(seg.strip(" .,!?;:-").split())
                        if len(seg) >= 6 and (low in seg or _df.SequenceMatcher(None, low, seg).ratio() >= 0.72):
                            return
                except Exception:
                    pass
            words = low.split()
            stops = ("stop", "stop it", "sotto stop", "quiet", "be quiet", "shut up", "shut it",
                     "pause", "sotto pause", "hold on", "hold it", "cancel that", "never mind",
                     "nevermind", "enough", "stop talking", "silence", "sotto quiet")
            hit = False
            for ph in stops:
                if low == ph or low.startswith(ph + " ") or (ph in low and len(words) <= 4):
                    hit = True
                    break
            if hit:
                _log(f"voice: interrupt word {low!r}")
                self._speak_muted = True
                self.stop_speaking()
                self._play_cue("stop")
                threading.Thread(target=self._listen_when_idle, daemon=True).start()
                time.sleep(1.2)
                return
            phrase, idx = self._wake_match(low)
            if idx >= 0:
                rest = self._best_rest(text, phrase)
                _log(f"voice: interrupt wake {text!r} rest={rest!r}")
                self._speak_muted = True
                self.stop_speaking()
                self._play_cue("wake")
                threading.Thread(target=self._listen_when_idle, args=(rest or None,), daemon=True).start()
                time.sleep(1.2)
        except Exception as e:
            _log(f"tts monitor error: {type(e).__name__}: {e}")
            time.sleep(0.5)

    def _wake_loop(self):
        """Continuous background listening for the wake phrase.

        Precise capture (WebRTC VAD): waits silently until speech starts,
        stops at the natural end of speech, then transcribes and checks
        for the wake phrase. Never fights the UI for the microphone."""
        from audio import VoiceCapture
        try:
            from voice import transcribe_wav, stt_ready
            if not stt_ready():
                _log("wake-word: STT not ready - listener stopped")
                self._wake_thread = None
                return
            from config import load_settings
            _log("wake-word: listener running (webrtcvad)")
            while self._wake_on:
                time.sleep(0.2)
                if getattr(self, "_tts", False):
                    self._tts_monitor_once()
                    continue
                if (self._busy or getattr(self, "_mic", None)
                        or getattr(self, "_ov_mic", None) or getattr(self, "_ov_listen", False)
                        or getattr(self, "_voice_active", False)
                        or time.time() < getattr(self, "_wake_hold", 0.0)):
                    continue
                kw = str(load_settings().get("wake_word") or "hey sotto").lower().strip()
                vad_mode = int(load_settings().get("vad_mode", 2) or 2)
                if getattr(self, "_wake_empty_streak", 0) >= 3:
                    time.sleep(6)
                    self._wake_empty_streak = 0
                _log("wake-word: capture starting")
                cap = VoiceCapture(end_silence=0.45, no_speech_timeout=480.0, max_len=5.0, vad_mode=vad_mode)
                cap.start(should_stop=lambda: bool(
                    not self._wake_on or self._busy or getattr(self, "_mic", None)
                    or getattr(self, "_tts", False) or getattr(self, "_voice_active", False)
                    or time.time() < getattr(self, "_wake_hold", 0.0)))
                cap.wait(600.0)
                if not cap._done.is_set():
                    cap.stop_now()
                wav = cap.stop()
                st = cap.stats or {}
                if cap.error:
                    _log(f"wake-word capture error: {cap.error}")
                if not cap.heard:
                    _log(f"wake-word: capture ended - nothing heard (err={cap.error})")
                    continue
                if not self._wake_on:
                    continue
                if float(st.get("peak", 1.0)) < 0.010:
                    _log(f"wake-word: low-level capture skipped peak={st.get('peak')}")
                    continue
                text, _err = transcribe_wav(wav, initial_prompt="Hey Sotto", vad_filter=False)
                text = (text or "").strip()
                if not text:
                    self._wake_empty_streak = getattr(self, "_wake_empty_streak", 0) + 1
                    _log("wake-word: heard something but no words (skipped)")
                    continue
                self._wake_empty_streak = 0
                low = text.lower()
                phrase, idx = self._wake_match(low)
                if idx < 0:
                    _log(f"wake-word ignored {text[:70]!r} dur={st.get('dur')} peak={st.get('peak')}")
                    continue
                rest = self._best_rest(text, phrase)
                _log(f"wake-word heard: {text!r} rest={rest!r}")
                self._activate_visual()
                if rest:
                    self._play_cue("wake")
                    self._push({"type": "user_text", "text": rest})
                    self._ov_turn = True
                    threading.Thread(target=self.send, args=(rest,),
                                     daemon=True).start()
                else:
                    threading.Thread(target=self.voice_turn,
                                     daemon=True).start()
                    time.sleep(0.35)
                    self._play_cue("wake")
                time.sleep(2)
        except Exception as e:
            _log(f"wake-word loop error: {e}")
        finally:
            self._wake_thread = None

    # ---- floating overlay -------------------------------------------------
    _TOOL_PHRASES = {
        "search_web": "Searching the web", "look_up": "Looking that up",
        "read_webpage": "Reading the page", "open_application": "Opening the app",
        "read_screen": "Looking at your screen", "read_window_text": "Reading the window",
        "read_pdf": "Reading the document", "read_file": "Reading the file",
        "email_summary": "Checking your email", "email_read": "Reading your email",
        "email_search": "Searching your email", "email_draft": "Writing a reply",
        "email_send": "Sending the email", "calendar_today": "Checking your day",
        "calendar_week": "Checking your week", "calendar_add": "Adding the event",
        "organize_downloads": "Organising files", "find_files": "Finding the file",
        "run_command": "Running a command", "type_text": "Typing",
        "get_weather": "Checking the weather", "set_reminder": "Setting the reminder",
        "add_note": "Saving the note", "daily_briefing": "Preparing your briefing",
        "take_screenshot": "Taking a screenshot", "smart_find": "Searching your files",
        "move_file": "Moving the file", "copy_file": "Copying the file",
        "save_text_file": "Saving the file",
    }

    def set_overlay_window(self, overlay_win, main_win):
        self._overlay_window = overlay_win
        self._main_window = main_win

    def _ov_note(self, event):
        """Update the floating-overlay snapshot from real assistant events."""
        t = event.get("type")
        now = time.time()
        self._ov_ts = now
        if t in ("say", "text"):
            txt = str(event.get("text") or "").strip()
            if txt:
                self._ov_said = (self._ov_said + " " + txt).strip()[-180:]
                self._ov_detail = self._ov_said
        elif t == "tool":
            name = str(event.get("name") or "")
            self._ov_detail = self._TOOL_PHRASES.get(name, "Working on it")
        elif t == "state":
            label = str(event.get("label") or "").strip()
            if label:
                self._ov_detail = label
        elif t == "done":
            self._ov_final = str(event.get("full") or event.get("text") or self._ov_said or "").strip()
            if not self._ov_final:
                self._ov_final = self._ov_said.strip()
            self._ov_detail = self._ov_final[-180:] if self._ov_final else self._ov_detail
            self._ov_done_ts = now
        elif t == "error":
            self._ov_err = str(event.get("text") or "Something went wrong.").strip()
            self._ov_detail = self._ov_err
            self._ov_err_ts = now

    def _ov_reset_turn(self):
        self._ov_said = ""
        self._ov_detail = ""
        self._ov_final = ""
        self._ov_err = ""
        self._ov_done_ts = 0.0
        self._ov_err_ts = 0.0

    def set_theme(self, theme):
        t = str(theme or "").strip().lower()
        if t == "dark":
            self._theme = "dark"
        elif t in ("light", "system"):
            self._theme = "light"
        return json.dumps(True)

    # ---- floating overlay pill ------------------------------------------
    def overlay_on(self):
        """Live value the visibility controller polls (no file reads)."""
        return bool(self._overlay_enabled)

    def set_overlay(self, on):
        from config import save_setting
        on = bool(on)
        ok = bool(save_setting("overlay_enabled", on))
        self._overlay_enabled = on
        _log(f"set_overlay -> {on} ok={ok}")
        return json.dumps(ok)

    def _confirm_cb(self, question, detail):
        """Destructive-action gate (spec 18). With the overlay enabled the pill
        becomes the confirmation surface (buttons + voice yes/no); otherwise the
        native topmost dialog is used so behaviour never regresses."""
        if not self._overlay_enabled:
            from confirm import ask
            return bool(ask(question, detail))
        ev = threading.Event()
        pend = {"question": question or "", "detail": detail or "",
                "ev": ev, "ok": False}
        self._confirm = pend
        self._push({"type": "confirm", "question": pend["question"],
                    "detail": pend["detail"], "ts": time.time()})
        threading.Thread(target=self._confirm_voice, args=(pend,), daemon=True).start()
        ev.wait(timeout=120)
        ok = bool(pend["ok"])
        if self._confirm is pend:
            self._confirm = None
        self._push({"type": "confirm_resolved", "ok": ok, "ts": time.time()})
        return ok

    def _confirm_voice(self, pend):
        """Let the user answer a confirmation by voice while outside Sotto."""
        try:
            time.sleep(0.25)
            if pend["ev"].is_set():
                return
            try:
                voice.speak(pend["question"])
            except Exception:
                pass
            if pend["ev"].is_set():
                return
            from audio import MicStream
            mic = MicStream()
            mic.start()
            time.sleep(3.5)
            wav = mic.stop()
            text = (voice.transcribe_wav(wav) or "").strip().lower()
            if not text or pend["ev"].is_set():
                return
            yes = ("yes", "yeah", "yep", "ok", "okay", "sure", "do it", "go ahead", "confirm")
            no = ("no", "cancel", "stop", "don't", "do not", "never mind", "nevermind")
            if any(w in text for w in no):
                self.overlay_confirm(False)
            elif any(w in text for w in yes):
                self.overlay_confirm(True)
        except Exception as e:
            _log(f"confirm voice: {type(e).__name__}: {e}")

    def overlay_confirm(self, ok):
        """Confirm/Cancel pressed on the pill."""
        pend = self._confirm
        if pend:
            pend["ok"] = bool(ok)
            pend["ev"].set()
        return json.dumps(True)

    def confirm_action(self, ok=True, *args):
        """Alias kept for the main UI's confirmation buttons."""
        return self.overlay_confirm(ok)

    def _ov_listen_loop(self):
        """Pill-owned listening: open the mic, detect speech end from the real
        level, transcribe, then run the turn - independent of the main window."""
        from audio import MicStream
        mic = MicStream()
        mic.start()
        self._ov_mic = mic
        t0 = time.time()
        heard = False
        silent = 0.0
        wav = None
        try:
            while self._ov_listen:
                time.sleep(0.05)
                try:
                    lv = float(mic.level or 0.0)
                except Exception:
                    lv = 0.0
                if lv > 0.06:
                    heard = True
                    silent = 0.0
                else:
                    silent += 0.05
                el = time.time() - t0
                if el > 0.8 and ((heard and silent > 1.0) or (not heard and el > 8)):
                    break
                if el > 60:
                    break
        finally:
            self._ov_listen = False
            self._ov_mic = None
            try:
                wav = mic.stop()
            except Exception:
                wav = None
        if not wav:
            return
        try:
            text, err = voice.transcribe_wav(wav)
        except Exception as e:
            _log(f"ov transcribe: {type(e).__name__}: {e}")
            text, err = "", True
        _log(f"ov listen -> {str(text)[:120]!r} err={err}")
        if text and not err:
            self._ov_turn = True
            try:
                self.send(text)
            except Exception as e:
                _log(f"ov send: {type(e).__name__}: {e}")
                self._ov_turn = False

    def overlay_tap(self):
        """Orb tapped: start talking - or stop early if already listening."""
        if getattr(self, "_voice_active", False):
            return self.voice_stop()
        return self.voice_turn()
        if self._tts:
            self.stop_speaking()
            return json.dumps(True)
        if self._busy or getattr(self, "_mic", None):
            return json.dumps(True)
        self._ov_listen = True
        threading.Thread(target=self._ov_listen_loop, daemon=True).start()
        return json.dumps(True)

    def request_pill_enter(self):
        """'Send to background' button: hide the main window. From here the
        floating overlay (tap / Ctrl+Space) is the interface."""
        _log("send-to-background -> overlay handles the presence")
        return self.hide_main()

    def overlay_state_raw(self):
        """Snapshot the floating overlay renders. Real states only."""
        now = time.time()
        state, detail, level = "idle", "", 0.0
        if self._confirm:
            state = "confirm"
            detail = self._confirm.get("question", "")
        elif getattr(self, "_mic", None) or self._ov_mic:
            state = "listening"
            try:
                level = self.listen_level()
            except Exception:
                level = 0.0
        elif self._busy:
            state = self._last_status or "thinking"
            if state not in ("thinking", "acting", "responding", "waiting"):
                state = "thinking"
            detail = self._ov_detail
        elif self._tts:
            state = "responding"
            detail = self._ov_detail
        elif (now - self._interrupted_ts) < 1.4 and self._interrupted_ts:
            state = "interrupted"
        elif (now - self._ov_err_ts) < 5.5 and self._ov_err:
            state, detail = "error", self._ov_err
        elif (now - self._ov_done_ts) < 3.8 and (self._ov_final or self._ov_detail):
            state, detail = "done", (self._ov_final or self._ov_detail)
        active = state in ("listening", "thinking", "acting", "responding", "working", "waiting", "confirm")
        linger = state in ("done", "error", "interrupted")
        return {
            "state": state,
            "detail": (detail or "")[-180:],
            "level": round(float(level or 0.0), 3),
            "visible": bool(active or linger),
            "theme": getattr(self, "_theme", "light"),
        }

    def overlay_state(self):
        """Returns JSON string of current state for the overlay webview."""
        return json.dumps(self.overlay_state_raw())

    def overlay_expand(self):
        """Called by overlay webview expand button."""
        self._pill_exit = True
        return json.dumps(True)

    def overlay_expand_pending(self):
        """Polled by the window controller."""
        v = bool(getattr(self, "_pill_exit", False))
        self._pill_exit = False
        return v

    def request_pill_exit(self):
        """Pill expand: bring the main window back."""
        return self.overlay_expand()

    def hide_main(self):
        """Overlay disabled: send Sotto to the background showing nothing."""
        w = getattr(self, "_window", None)
        if not w:
            return json.dumps(False)
        try:
            w.hide()
        except Exception as e:
            _log(f"hide_main error: {e}")
            return json.dumps(False)
        _log("hide_main -> background")
        return json.dumps(True)

    # ---- voice ---------------------------------------------------------
    def listen(self):
        try:
            return json.dumps({"text": voice.listen_once(6) or ""})
        except Exception as e:
            return json.dumps({"text": "", "error": str(e)})

    def say(self, text):
        self._tts = True
        try:
            return json.dumps({"ok": bool(voice.speak(text))})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
        finally:
            self._tts = False
