# voiceStra / RealAssistant

A local-first desktop assistant that runs on your PC and uses a cloud LLM (Groq) as its
brain. It is built to feel like a real person sitting next to you - casual, short, no
"as an AI" nonsense - and to actually *do* things on your computer, not just chat.

> Phase 1 (now): make the **text brain** genuinely human and reliable.
> Phase 2 (later): add voice (local speech-to-text + custom local text-to-speech).
> Phase 3 (later): build the UI around a brain that already works.

## How it works

```
You type  ->  main.py builds context (persona + memory + recent turns)
          ->  ai_engine.py asks Groq (the brain)
          ->  the brain may ask for a tool (JSON)
          ->  tools.py runs it LOCALLY, returns a short result
          ->  the brain says one natural line back to you
```

The cloud model **never** touches your filesystem or terminal directly. It can only request
one of the named tools in `tools.py` with JSON arguments. Everything else stays on your PC:
your API key, your memory file, your file paths.

## Files

| File | What it does |
| --- | --- |
| `config.py` | Model name, memory settings, and the assistant's **persona**. Tune the personality here. |
| `ai_engine.py` | Groq client, retries, message helpers, summarisation. |
| `tools.py` | The **hands**: tool registry + app discovery + every capability. |
| `core.py` | The **engine** (`Assistant`) - any front-end drives this. |
| `memory.py` | Persistent local memory (`%LOCALAPPDATA%\RealAssistant\memory.json`). |
| `reminders.py` | Timers/reminders with a background thread; survive restarts. |
| `notes.py` | Quick local notes (`notes.json`). |
| `winctl.py` | Window control (list / focus / minimise / maximise) via Win32. |
| `fileops.py` | File organising for Downloads, with undo. |
| `sysactions.py` | Power (shutdown/restart/sleep/lock) and safe Recycle-Bin deletes. |
| `confirm.py` | Native Windows confirmation dialog for risky actions. |
| `learn.py` | Quietly mines the chat for durable facts to remember. |
| `audit.py` | Local log of every action taken. |
| `display.py` | Screen brightness + exact master volume. |
| `briefing.py` | Weather + daily briefing + reading a web page's text. |
| `browser.py` | Chrome profile listing + opening a specific account. |
| `sysinfo.py` | System awareness: CPU/RAM/disk/battery, processes, network. |
| `proactive.py` | Conservative background watcher that speaks up when it matters. |
| `main.py` | The console front-end (typing + printing). |
| `voice_ui.py` | **The voice-first app** (Flet: audio-reactive orb). |
| `audio.py` | Live mic level + recording for the visualiser. |
| `ui_app.py` | Chat-style window launcher (pywebview). |
| `ui/` | The desktop UI - HTML/CSS/JS, Apple-style. |
| `ui_bridge.py` | The JS <-> Python bridge for the desktop UI. |
| `sessions.py` | Saved chats for the desktop UI. |
| `voice.py` | Offline speech: Windows TTS + speech recognition (no API, no GPU). |
| `voice_main.py` | The hands-free front-end (push-to-talk, voice confirmations). |
| `voice_convert.py` | Plug-in point for a custom (RVC) voice. |
| `mic_test.py` | Microphone + speech-recognition diagnostic. |
| `voice_check.py` | Full voice self-diagnosis (PASS/FAIL with fixes). |
| `VOICE_GUIDE.md` | How to train your own voice on Colab. |
| `run.bat` | Double-click launcher: `run.bat`, `run.bat voice`, `run.bat check`, `run.bat mic`. |
| `test_e2e.py` | Scripted end-to-end test (uses the API). |
| `TESTING.md` | The manual testing checklist. |
| `selftest.py` | Offline checks (no API key needed). |
| `verify_apps.py` | Lists every app the scanner can find. |

## Setup

Requires Python 3.10+ (tested on 3.13) and a Groq API key (free tier is fine).

```powershell
# 1. install dependencies
python -m pip install -r requirements.txt

# 2. create a .env file in this folder with one line:
#    GROQ_API_KEY=your_key_here

# 3. check everything offline first (no API key needed)
python selftest.py

# 4. run it
python main.py
# ...or just double-click run.bat (it finds the right interpreter for you)
```

If tools report missing libraries, you're running on the wrong Python - the app prints which
interpreter it's using at startup, and `run.bat` picks your project venv automatically.

## What it can do right now

- **Open apps** (Start Menu + Desktop + Public Desktop + Taskbar + Registry, with ranked
  matching so "chrome" doesn't open "Chrome Remote Desktop"), launched **detached** so an
  app's own console output never leaks into the chat
- **Close apps** (asks for confirmation first)
- **Open websites** and **search the web**
- **Open folders** and **create folders**
- **Media & volume control** (play/pause, next, previous, mute, volume up/down)
- **Clipboard** read and write
- **System info** (time, free disk space, battery)
- **Reminders** ("remind me in 20 minutes", "at 7pm") - persisted, fire while the app runs
- **Notes** you can add, list, and search
- **Window control** - list open windows and focus / minimise / maximise one
- **File organising** - sort Downloads into folders by type, with undo
- **System actions** - shutdown / restart (with Windows' own countdown + cancel), sleep, lock
- **Safe delete** - moves things to the Recycle Bin, never a permanent delete
- **Web answers** - looks things up and answers in its own words
- **Streaming replies** - text appears as it's written, instead of all at once
- **Learns on its own** - quietly picks up durable facts about you from normal chat
- **Memory you control** - ask what it knows, or tell it to forget
- **Reads files** - summarise or answer questions about txt/md/code/PDF/docx
- **Finds files** - by name, or search inside them
- **Moves / copies / renames** files safely (move asks first; copy doesn't)
- **Chrome profiles** - open Chrome under a specific account
- **Reads a web page** back as text, so it can answer from a source
- **Live status** - shows `... thinking` so you always know it's working
- **Answer by voice/text** for risky actions (set `confirm_mode` to `chat`)
- **Audit log** - see every action it took
- **Window snapping** - left / right / top / bottom / centre / maximise
- **Brightness** and **exact volume** percentage
- **Weather** and a **daily briefing** (time, weather, reminders, disk)
- **System awareness** - CPU/RAM/disk/battery, top processes, network check, list installed apps
- **Proactive nudges** - quietly warns about low disk space or low battery
- **Take screenshots** (saved to `Pictures\RealAssistant`)

## The app (voice-first)

The main app is a **voice-first assistant**, not a chat window - pure Python with Flet.

```powershell
.\run.bat ui          # or: python voice_ui.py
```

- A live **audio-reactive orb**: it breathes when idle, expands and brightens with your
  voice while listening, orbits while thinking, and pulses while speaking.
- **Tap the orb** (or the button) to talk; it auto-stops after ~1.2 s of silence.
- Your words appear as a small caption; the reply is **spoken out loud** and shown briefly.
- Minimal chrome: a status line, an optional "Type instead" field, and Settings
  (spoken voice, service check).
- Colours come from the Apple design system (pure black canvas + a single blue accent).

`run.bat chat` opens the earlier chat-style window (sessions, panels) if you want it.

## Desktop app (chat style)

A native window (no browser tab) with a chat UI, saved sessions, side panels and voice.

```powershell
.\run.bat ui          # or: python ui_app.py
```

- **Chat** with live streaming text and tool-activity chips
- **Sessions** - chats are saved and listed in the sidebar; reopen one and its context returns
- **Panels** - Memory / Notes / Reminders in the right rail
- **Voice** - the mic button dictates; the speaker button speaks replies
- **States** - proper empty, loading and error states (with retry)

Design: Apple design-system tokens (`design-systems/apple`) - neutral triad
(`#000000` / `#f5f5f7` / `#ffffff`), single blue accent (`#0071e3`), capsule controls,
thin chrome. The system font stack is used (no Inter/Roboto).

## Voice (offline, no API, no GPU)

The voice front-end uses Windows' own speech engine - nothing is sent anywhere, and there's
nothing extra to install:

```powershell
python voice_main.py        # or:  .\run.bat voice
```

- Press **Enter**, speak, and it replies out loud.
- Risky actions are confirmed **by voice** - say "yes" to approve, no clicking.
- **Text-to-speech** uses the voices already installed on your PC.
- **Speech-to-text** uses **Vosk** (offline, CPU). If it doesn't hear you, run
  `python voice_check.py --mic` - it checks everything and prints PASS/FAIL with the fix.
  Requires `sounddevice`, `numpy`, `vosk`, and a one-time model download (see Setup).

Your own **custom voice sample** is the next step: render to audio, then convert it locally
with a small voice-conversion model (CPU only - no GPU, no API).

### Choosing a voice

Any user can pick their own voice. Set it in `settings.json`:

```json
{ "voice_name": "Microsoft Zira Desktop", "voice_rate": 0 }
```

...or just ask: *"list your voices"*, *"use the Zira voice"*. An empty `voice_name` means the
system default.

### Custom voice (your own sample, or a favourite actor's)

The pipeline to go beyond the built-in voices is:

```
reply text  ->  Windows TTS (any voice)  ->  local voice conversion  ->  your target voice
```

The conversion step is a small **RVC-style** model, trained once from a clean sample of the
target voice. After that it runs **locally on CPU** (no GPU, no API). Training is the heavy
part - a one-time job that can be done on a free cloud GPU; the resulting model is then yours
to run offline.

_Note: cloning a real person's voice is fine for your own personal offline use. Sharing that
model, or using it to impersonate someone publicly, is where it stops being okay - keep it
personal._

## Safety

- The cloud model can only ever *ask for* a named tool - it never runs anything itself.
- Actions that change or remove things (shutdown, restart, sleep, lock, delete, closing apps,
  moving files) pop up a **native confirmation dialog** first. Nothing runs until you approve.
- Shutdown/restart use Windows' own delayed shutdown, so you also get the OS countdown and can
  abort it with "cancel shutdown".
- Deletes go to the **Recycle Bin**, not a permanent delete.

## How to extend it (adding a new tool)

1. Write a function in `tools.py`.
2. Decorate it:

```python
@tool(
    name="set_volume",
    description="Set the system volume to a percentage.",
    parameters={
        "type": "object",
        "properties": {"percent": {"type": "integer"}},
        "required": ["percent"],
    },
    danger=False,
)
def set_volume(percent):
    ...            # do the thing, return a short string
```

That's it - the schema is sent to the model automatically and `main.py` dispatches to it.
Set `danger=True` if the action is destructive; then the assistant will ask you to confirm.

## How to customise

- **Personality/voice:** edit `SYSTEM_PROMPT` in `config.py`.
- **Model:** edit `MODEL_NAME` in `config.py`.
- **Memory size / compression:** `RECENT_TURNS_KEPT`, `SUMMARIZE_WHEN_TURNS_OVER` in `config.py`.
- **An app that won't open:** add its `.exe` path to `CUSTOM_APP_PATHS` in `tools.py`.
- **Forget everything:** delete `%LOCALAPPDATA%\RealAssistant\memory.json`.

## Settings

A `settings.json` is created on first run at `%LOCALAPPDATA%\RealAssistant\settings.json`. Edit it to
change the model, reply length, provider, or to disable specific tools:

```json
{
  "model": "gemini-3.8-flash",
  "api_key_env": "GEMINI_API_KEY",
  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
  "temperature": 0.6,
  "max_tokens": 1024,
  "reasoning_effort": "low",
  "denied_tools": [],
  "proactive": true,
  "proactive_interval_seconds": 300,
  "confirm_mode": "dialog"
}
```

### Switching provider

`base_url` + `api_key_env` + `model` let you point at any OpenAI-compatible service.

- **Default (Groq):** leave `base_url` empty, `api_key_env` = `GROQ_API_KEY`,
  `model` = `openai/gpt-oss-20b`.
- **Google Gemini:** `base_url` = `https://generativelanguage.googleapis.com/v1beta/openai/`,
  `api_key_env` = `GEMINI_API_KEY`, `model` = `gemini-3.8-flash` (or `gemini-flash-latest`).

Then put the matching key in `.env` and check it with `run.bat api`.

### Other settings

`confirm_mode` is `"dialog"` (a native yes/no box) or `"chat"` (answer by typing/voice -
better once the voice layer exists). `reasoning_effort` only applies to `gpt-oss` models.

Put any tool name in `denied_tools` (e.g. `"shutdown_pc"`) and the assistant will refuse to run it.

## Packaging it as an .exe

```powershell
python -m pip install pyinstaller
python build.py
```

That produces `dist\RealAssistant.exe` (one file). Put your `.env` next to the `.exe` before
running it. If a tool uses a library PyInstaller can't detect automatically, add it to
`HIDDEN_IMPORTS` in `build.py`.

## Continuous integration

The self-test workflow lives in `ci/selftest.yml`. GitHub refuses files under `.github/workflows/`
unless the token has the **workflow** scope, so to switch CI on either:

- copy `ci/selftest.yml` to `.github/workflows/selftest.yml` from GitHub's web UI (Actions tab),
  or
- give your token the `workflow` scope, then move the file there.

Once active, it runs the offline self-test on every push and pull request on a Windows runner.

## Roadmap

- [x] Text loop, persona, tool calling, app scanner
- [x] Persistent memory, hardened app discovery, multi-tool chaining, graceful errors
- [x] Web search / open site, screenshot, remember, folders, media/volume, clipboard, system info
- [x] Reminders, notes, window control, file organising (with undo)
- [x] System actions with confirmation, safe delete, web answers, streaming replies
- [x] Auto-learning memory, recall/forget, file reading + search, audit log, settings.json
- [x] Window snapping, brightness, exact volume, weather + daily briefing
- [x] System awareness, proactive nudges, multi-step planning
- [x] Packaging script (.exe) and CI self-test
- [x] Core/UI split, move/copy/rename, Chrome profiles, web reading, verbal confirmations
- [x] Offline voice front-end (Windows speech engine: TTS + recognition, no API)
- [x] Desktop app UI (Apple-style: chat, sessions, panels, voice, states)
- [x] Voice-first app: Flet, audio-reactive orb visualiser, tap-to-talk
- [x] Voice selection (installed voices + system default) and offline TTS/STT
- [ ] Custom voice (RVC-style local conversion from a sample)
- [ ] Deeper browser control (Playwright) and a desktop UI
- [ ] Desktop UI (options: PySide6 / pywebview / Flet - see below)
