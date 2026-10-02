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


class Api:
    def __init__(self, on_ready=None):
        self.store = SessionStore()
        self.assistant = Assistant(on_text=self._on_text, on_tool=self._on_tool,
                                    on_learned=self._on_learned, on_status=self._on_status)
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
        if any(m in low for m in ("<tool_call", "<function=", "<parameter=")):
            self._turn_leak = True
            _log("leak-guard: holding back XML tool-call text")
        if not self._turn_checked:
            self._turn_checked = True
            if any(m in low for m in ("the user is asking", "the user wants", "i should check",
                                      "i need to check", "let me use", "let me check what", "i can use")):
                self._turn_leak = True
                _log("leak-guard: holding back planning text")
        if self._turn_leak:
            return
        kind = "text" if self._speak_muted else "say"
        self._push({"type": kind, "text": text + " "})

    def _on_status(self, state):
        if state == self._last_status:
            return
        self._last_status = state
        if state == "thinking":
            self._push({"type": "state", "name": "thinking", "label": "Thinking."})

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
        _log(f"send() called with {text[:120]!r}")
        if not text:
            return json.dumps({"ok": False})
        self._buf = ""
        self._speak_muted = False
        self._last_status = None
        self._turn_checked = False
        self._turn_leak = False
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
        """A weak model leaked planning/meta text — rewrite it into a clean answer."""
        import ai_engine
        try:
            import re as _re
            draft = _re.sub(r"<tool_call[\s\S]*?</tool_call>|<function=[\s\S]*?</function>",
                            " ", draft or "").strip()
        except Exception:
            pass
        _log("repair: rewriting planning-leaked reply")
        self._turn_leak = False
        self._turn_checked = True
        fixed = ""
        try:
            fixed = (ai_engine.complete([
                {"role": "system", "content": "Rewrite the draft as the final reply to the user: "
                 "one or two short plain sentences, first person, no planning, no meta-commentary, "
                 "no mention of tools or commands."},
                {"role": "user", "content": draft[:1500]},
            ], max_tokens=300) or "").strip()
        except Exception as e:
            _log(f"repair failed: {e}")
        if fixed:
            self._flush_say(fixed)
            return fixed
        _log("repair produced nothing")
        return ""

    def _run(self, text):
        try:
            reply = self.assistant.ask(text)
            rem, self._buf = self._buf.strip(), ""
            if rem:
                self._flush_say(rem)
            if self._turn_leak:
                reply = self._repair(reply or "")
            if not (reply or "").strip():
                _log("EMPTY reply from ask() -> error event (turn never dies silently)")
                self._push({"type": "error",
                            "text": "I didn't get a usable response — one more try…"})
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
        from config import save_setting
        return json.dumps(bool(save_setting("wake_word", bool(on))))

    def say_slow(self, text):
        try:
            return json.dumps({"ok": bool(voice.speak(text, rate=-3))})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

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
                
                if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL, VK_SPACE):
                    _log("RegisterHotKey failed (may already be registered)")
                    return
                
                msg = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    if msg.message == 0x0312:  # WM_HOTKEY
                        _log("Global hotkey Ctrl+Space pressed")
                        if self._window:
                            try:
                                self._window.restore()
                                self._window.show()
                            except Exception:
                                pass
                        self._push({"type": "hotkey", "action": "activate"})
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception as e:
                _log(f"hotkey_loop error: {e}")

        threading.Thread(target=_hotkey_loop, daemon=True).start()

    def set_window_mode(self, mode):
        """Switch between the full window and the floating mini overlay."""
        m = str(mode or "full").lower()
        w = getattr(self, "_window", None)
        if not w:
            return json.dumps(False)
        try:
            if m == "mini":
                try:
                    self._prev_rect = (w.x, w.y, w.width, w.height)
                except Exception:
                    self._prev_rect = None
                w.resize(380, 118)
                try:
                    import ctypes
                    sw = ctypes.windll.user32.GetSystemMetrics(0)
                    sh = ctypes.windll.user32.GetSystemMetrics(1)
                    w.move(max(0, sw - 380 - 24), max(0, sh - 118 - 64))
                except Exception:
                    pass
                w.on_top = True
                _log("set_window_mode -> mini")
            else:
                w.on_top = False
                prev = getattr(self, "_prev_rect", None)
                if prev:
                    x, y, ww, hh = prev
                    w.resize(int(ww), int(hh))
                    w.move(int(x), int(y))
                    self._prev_rect = None
                else:
                    w.resize(1180, 780)
                _log("set_window_mode -> full")
            return json.dumps(True)
        except Exception as e:
            _log(f"set_window_mode error: {e}")
            return json.dumps(False)

    def set_always_on_top(self, on_top):
        if not getattr(self, "_window", None):
            return json.dumps(False)
        try:
            self._window.on_top = bool(on_top)
            return json.dumps(True)
        except Exception:
            return json.dumps(False)

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
