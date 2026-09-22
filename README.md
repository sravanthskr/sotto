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
| `memory.py` | Persistent local memory (`%LOCALAPPDATA%\RealAssistant\memory.json`). |
| `reminders.py` | Timers/reminders with a background thread; survive restarts. |
| `notes.py` | Quick local notes (`notes.json`). |
| `winctl.py` | Window control (list / focus / minimise / maximise) via Win32. |
| `fileops.py` | File organising for Downloads, with undo. |
| `sysactions.py` | Power (shutdown/restart/sleep/lock) and safe Recycle-Bin deletes. |
| `confirm.py` | Native Windows confirmation dialog for risky actions. |
| `learn.py` | Quietly mines the chat for durable facts to remember. |
| `audit.py` | Local log of every action taken. |
| `main.py` | The loop: context building, tool dispatch, memory compression. |
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
```

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
- **Audit log** - see every action it took
- **Take screenshots** (saved to `Pictures\RealAssistant`)

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
change the model, reply length, or to disable specific tools:

```json
{
  "model": "openai/gpt-oss-20b",
  "temperature": 0.6,
  "max_tokens": 400,
  "denied_tools": []
}
```

Put any tool name in `denied_tools` (e.g. `"shutdown_pc"`) and the assistant will refuse to run it.

## Roadmap

- [x] Text loop, persona, tool calling, app scanner
- [x] Persistent memory, hardened app discovery, multi-tool chaining, graceful errors
- [x] Web search / open site, screenshot, remember, folders, media/volume, clipboard, system info
- [x] Reminders, notes, window control, file organising (with undo)
- [x] System actions with confirmation, safe delete, web answers, streaming replies
- [x] Auto-learning memory, recall/forget, file reading + search, audit log, settings.json
- [ ] Voice: local STT + custom local TTS (no extra AI call)
- [ ] UI (Bring Your Own Key)
