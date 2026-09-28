# RealAssistant — Project Brief (for UI design review)

> Hand this to any AI/designer. It describes what the product **is**, how it **works**, what the
> UI **currently is**, and the constraints any new UI must respect.

---

## 1. One line

A **local-first, voice-first desktop assistant for Windows** that talks like a person, controls the
real computer through 62 safe tools, remembers the user across sessions, and runs without a GPU —
packaged as a single Python app.

## 2. Vision & feel

- Not a chatbot. A presence that sits on your PC: you talk, it acts, it answers out loud.
- Persona: casual friend, short replies, **no "as an AI"**, no emoji, never corporate.
- Privacy: API keys, memory, files stay local. The cloud model gets **no** filesystem/terminal
  access — it can only ask for one of the 62 named tools, which the local Python validates and runs.
- Constraint priority: **no GPU**, modest CPU/RAM (the target machine struggles at ~95% RAM under
  load), must stay light and fast.

## 3. How it works (data flow)

```
mic → Vosk/faster-whisper (offline STT) → text
                                   │
                    core.Assistant.ask(text)
                                   │
        ┌──────────────────────────┴─────────────────────────┐
        │  builds context: persona + memory facts + summary  │
        │  + recent turns + current date/time               │
        └──────────────────────────┬─────────────────────────┘
                                   │
                     LLM provider (OpenAI-compatible)
              Gemini (primary) / Groq (fallback; ISP-blocked)
                                   │
                 returns either plain text, or tool_calls[]
                                   │
              tools.run(...)  ── validated + logged locally ──► acts on Windows
                                   │
                     tool result fed back → final reply
                                   │
        streamed to UI word-by-word → spoken via TTS (offline)

Side channels: persistent memory, reminders thread, proactive watcher (low disk/battery),
audit log, auto fact-learning (every 4 turns).
```

## 4. Architecture (Python 3.12, 41 files)

| Layer | Files | Role |
|---|---|---|
| Entry points | `main.py` console, `app_qt.py` **the app**, `voice_main.py` terminal voice | front-ends |
| Engine | `core.py` (`Assistant` facade: `ask()`, callbacks: text/tool/status/confirm) | the brain loop |
| LLM | `ai_engine.py` | provider client, streaming (SSE), tool-call parsing, retries/backoff |
| Hands | `tools.py` (registry + 62 tools), `fileops`, `winctl`, `sysactions`, `sysinfo`, `display`, `browser`, `briefing` | everything it can do |
| Mind | `memory.py`, `learn.py`, `notes.py`, `reminders.py`, `audit.py`, `proactive.py`, `sessions.py` | memory & state |
| Voice | `voice.py` (TTS + STT), `audio.py` (live mic level), `voice_convert.py` (custom voice hook) | speech |
| Config | `config.py` + `settings.json` (`%LOCALAPPDATA%\RealAssistant\`) | model, provider, voice, permissions |
| Ops | `selftest.py`, `test_e2e.py`, `api_check.py`, `voice_check.py`, `mic_test.py`, `build.py` | tests/diagnostics |

The engine is **UI-agnostic**: any front-end drives the same `Assistant` object via callbacks
(`on_text`, `on_tool`, `on_status`, `on_confirm`, `on_reminder`). That's the seam a new UI plugs into.

## 5. What it can actually do (62 tools, grouped)

- **Apps & windows**: open/close apps (Start Menu + Desktop + Taskbar + Registry, ranked matching), list apps, list/focus/minimise/maximise/snap windows
- **Files**: read (txt/md/code/PDF/docx), find by name & content, move/copy/rename, create folders, organise Downloads with undo, recycle-bin delete
- **Web**: search (`look_up`), read a page's text, open site/browser, Chrome profile listing & launch
- **System**: status (CPU/RAM/disk/battery/uptime), top processes, network check, brightness, exact volume, media keys, clipboard, screenshots
- **Power** (confirm-gated): shutdown/restart with Windows' own countdown, cancel, sleep, lock
- **Time & notes**: reminders (persisted), notes CRUD, daily briefing, weather
- **Memory**: `remember`, list/forget facts, auto-learning from chat
- **Meta**: audit log view, voices, autostart toggle, `say`
- Safety: destructive actions pop a native confirm (or chat confirm), everything is audit-logged.

## 6. Voice pipeline (offline, no API, no GPU)

- **STT**: `faster-whisper small.en` on CPU (accurate; Vosk is the fallback). Auto-stop after ~1.2 s silence.
- **TTS**: Windows SAPI voices (David/Zira installed) — instantly available, zero download.
- **Custom voice (planned)**: RVC-style conversion trained once on Colab from a sample, then run on CPU locally (`voice_convert.py` is the plug-in point). A 12-min clean sample exists.

## 7. Providers

- Primary: **Gemini `gemini-3.8-flash`** via its OpenAI-compatible endpoint.
- Fallback: **Groq** (currently blocked on the user's ISP; works on mobile data).
- Configurable via `settings.json`: `model`, `base_url`, `api_key_env`.
- Rate reality: free tier is **per-minute request limited**; the app minimises calls (learning every 4 turns) and backs off on 429.

## 8. Current UI (what exists now)

**`app_qt.py` — PySide6 (Qt), pure Python, dark "Aura" style.**

- **Sidebar**: Home / Tasks / Insights / Settings (icon buttons, active state highlighted).
- **Home**: central **orb with two blinking eyes**, concentric rings, and a **44-bar live waveform**.
  Four states: idle (breathing) · listening (reacts to mic level) · thinking (rotating ring) ·
  speaking (pulses).
- **Transcript** below the orb: bubble messages (user tinted violet/blue, assistant glass), streamed.
- **Quick chips** when idle; **floating glass input bar** (＋ attach, text, gradient mic, send).
- **Compact mode**, `Ctrl+Space` show/hide, hold-`Space` push-to-talk.
- **Tasks** = real reminders; **Insights** = real audit-log stats; **Settings** = voice, provider, service check.
- Render: `preview_aura.png`.
- Not done: sound effects, file attachments, live partial transcription.

(History: pywebview/HTML chat UI and a Flet attempt both exist in the repo but are superseded.)

## 9. Hard constraints for any new UI

1. **Pure Python desktop** — no browser, no Electron, no JS toolchain; must drive `core.Assistant` directly.
2. **No GPU**; keep RAM/CPU modest; cold start fast.
3. **Offline-capable**: STT/TTS/memory/tools are local; only the LLM needs the network.
4. **Windows-first** (uses Win32/COM/registry).
5. **Single window**, resizable; compact mode expected; must survive a low-end laptop.
6. **Ships as one .exe** (PyInstaller) eventually — keep dependencies lean.
7. Accessibility: keyboard reachable, visible focus, ≥44 px targets, readable contrast.

## 10. Questions worth answering for a better UI

- How should a **voice-first** app avoid becoming "a chat app with a mic"? What is the ideal
  hierarchy when the primary content is *speech* and the transcript is secondary?
- What should the **idle → listening → thinking → speaking** states communicate, and how should they
  differ visually beyond colour?
- How much transcript belongs on screen? Should it be ephemeral (fade after speaking) or a persistent log?
- What belongs in **compact mode** (always-on-top orb) vs the full window?
- How to surface **62 tools' activity** without noise — what does "it's working" look like when the
  user is listening, not reading?
- How to make **memory** feel present but private?
- Any better metaphor than a sidebar + orb for a desktop assistant?

## 11. Repo

- `https://github.com/srav-ku/voiceStra` (current: v32, commit `f76d541`)
- Docs: `README.md` (setup), `TESTING.md`, `VOICE_TEST.md`, `VOICE_GUIDE.md` (custom voice)
