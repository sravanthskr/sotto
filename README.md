# Sotto

> **Consider it done.**

Sotto is a voice-first personal operator for Windows. You say what you want in your own words — and Sotto does the work inside your real email, calendar, files, and apps, then tells you what actually happened. It listens when you hold a key, speaks back in a voice you choose, asks before anything consequential, and never pretends something worked when it didn't.

It is built for one person on one machine: local-first, no GPU required, and your keys stay encrypted on your PC.

*Development note: this project began under the working name "RealAssistant". The repository is `voiceStra`; the product is **Sotto**.*

> **Visuals coming soon.** Screenshots of the current build and a short demo video are being prepared — they will be added here.

## Why This Exists

Using a computer still means doing the work yourself: opening apps, hunting through menus, copying information between windows, repeating the same routine next week, and re-explaining context every tool forgot.

Existing assistants answer questions. Copilots suggest while you drive. Sotto is built to hand the *doing* over — one sentence in, real work out, honestly reported. In practice that means:

- You ask what needs you in your mail — in one sentence, without opening it.
- You add to your calendar by talking, not by clicking through dialogs.
- You find and read documents by describing them.
- You set up repeated errands once as routines, then run them by name.

## What It Does

### Voice interaction
Hold **Space** (or press the mic) and speak naturally. Sotto replies out loud, sentence by sentence, so it starts answering quickly. "Repeat that", "say it slower", and "stop" work at any time — it stops mid-sentence. Choose any installed voice; advanced users can train a custom voice from their own samples.

### Email, handled
With your own Google account connected, Sotto reads, searches, and summarizes mail; writes replies in your voice; and sends only after you confirm. Draft → confirm → send.

### Your calendar
Reads today and the week ahead; adds events — from Google Calendar or an `.ics` feed.

### Files & documents
Finds files by name or by content; reads PDFs and documents; tidies the Downloads folder (with undo); moves, copies, and renames; deletes go to the Recycle Bin.

### What's on your screen
On request, it reads what's on your screen or in a window — errors, pages, forms — and helps with what it sees.

### Apps & system
Opens and closes apps; controls windows; sets volume and brightness; handles media playback; takes screenshots; reads and writes the clipboard; locks, sleeps, restarts, or shuts down — with a confirmation for the big ones.

### Memory, notes, reminders
Sotto remembers durable facts and preferences — visible, editable, and forgettable on request. It keeps quick notes, and sets reminders with natural timing ("remind me at 4").

### Routines & the daily briefing
Save a sequence of actions once and re-run it by name. Ask for a short spoken briefing of your day, or the weather.

### Honest by design
Before consequential actions it asks one clear question. It keeps a local record of what it did (you can ask to see it). When it can't be sure something worked, it says so instead of guessing.

## See It In Action

A typical exchange, up to the confirmation step:

```text
You:    Anything urgent in my email?
Sotto:  Three unread. One needs a reply today — the invoice from Rahul,
        he wants a yes/no by noon.
You:    Reply yes, that it's approved, and ask him to confirm by 4.
Sotto:  Draft: "Hi Rahul — yes, approved. Please confirm by 4." Send it?
You:    Send it.
Sotto:  Sent.
```

Where it can check the result — like a sent email — it checks before saying "done"; when it can't, it says that too. (Full step-by-step verification across every action is in progress; see Current Status.)

### Screenshots & Demo

*Screenshots of the main screen, memory, settings, and history — plus a short recorded demo (ask → confirm → done) — are being prepared and will be added here soon.*

## How It Works

```text
You hold Space and speak
        ↓
Speech recognition runs on your PC (offline)
        ↓
Sotto works out what you're asking
        ↓
It runs the right capability locally
        ↓
It checks the result where it can
        ↓
It replies out loud — in your chosen voice
```

The AI reasoning uses a provider you bring a key for (OpenRouter, Groq, Google Gemini, or GitHub Models — free tiers exist). Nothing but the text of your request goes to that provider: your files, audio, and credentials stay on your machine.

## Getting Started

### Requirements

- Windows 10 or 11 (64-bit)
- Python 3.12
- A microphone and speakers
- An API key for an AI provider — free tiers work (see Configuration)
- Internet connection for the AI reasoning
- No GPU required (the optional custom voice is CPU-only)

### Installation

```powershell
git clone https://github.com/srav-ku/voiceStra.git
cd voiceStra
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

**Recommended path (in the app):** open **Settings** and add your AI provider key there; connect Google for email and calendar the same way. Keys entered in the app are stored encrypted on your PC.

**Advanced path (`.env` file):** copy the template and fill in whichever provider(s) you use:

```powershell
copy .env.example .env
```

```ini
OPENROUTER_API_KEY=your-key-here
GROQ_API_KEY=your-key-here
GEMINI_API_KEY=your-key-here
GITHUB_TOKEN=your-token-here
```

For connecting Google step by step, see [`ACCOUNTS_SETUP.md`](ACCOUNTS_SETUP.md).

### Run

```powershell
run.bat ui
```

Other modes: `run.bat voice` (terminal voice mode) · `run.bat check` and `run.bat mic` (voice diagnostics) · `run.bat providers` (provider speed test) · `run.bat qt` (earlier Qt build, kept for reference).

`run.bat` automatically uses the project's `.venv` when present.

### First Run

No wizard — one screen. Allow microphone access when Windows asks (or run `run.bat mic` if something seems quiet). Sotto may ask to scan your installed apps; that's how it can open them by name later. Then hold **Space** and try one of the suggestions on screen: *System status*, *Set a timer*, *What's playing*, or *Organise downloads*.

## Usage — things you can say

- **Email** — "Anything urgent in my email?" · "What did Sara send?" · "Reply that I'll confirm tonight." · "Send it."
- **Calendar** — "What's tomorrow?" · "Add a meeting with Rahul on Thursday at 3."
- **Files & documents** — "Find my resume." · "What does this PDF say?" · "Organise my downloads." · "Move these into the Project folder."
- **Screen** — "What's this error?" · "Summarize what's on screen."
- **Apps & system** — "Open Photoshop." · "Volume at 30." · "Lock the PC."
- **Memory & notes** — "Remember I ship on Fridays." · "Note: milk and eggs." · "Remind me at 4 to call the bank." · "What do you know about me?"
- **Routines** — "Save this as my Monday routine." · "Run my Monday routine."
- **Voice** — "Repeat that." · "Say it slower." · "Stop."

## Current Status

*Honest snapshot: if it's listed as working, it has been exercised on a real machine.*

**Working today**
- Full voice loop: hold-to-talk, offline speech recognition, spoken replies, stop / repeat / slower, voice selection
- Custom voice (experimental, optional): trained from your own samples, running through a local pipeline — slower than built-in voices
- Email via your own Google account: summary, search, read, draft, send (with confirmation)
- Calendar: today & week, add events (Google or `.ics`)
- Files: find by name or content, read PDFs, organise Downloads (+ undo), move/copy/rename, safe deletes
- Screen reading and window text (on request)
- Apps & system: open/close, windows, volume, brightness, media, screenshots, clipboard, power actions (with confirmation)
- Memory, notes, reminders, routines, daily briefing, weather
- Interface: light (default) and dark; panels for memory, history, and settings

**In progress**
- The agent kernel: multi-step jobs with planning, verification, and permission tiers
- Calendar: moving and cancelling events; finding free time
- First-run polish and an installer

**Planned**
- "Prepare me for X" workflows (for example, interview prep) end-to-end
- More Google services (Drive, Tasks) and a wider set of app integrations
- Opt-in proactive briefs and monitoring; wake-word support

## Roadmap

```text
Voice control        →  it does what you say
Computer tasks       →  it handles errands across your apps     ← now
Multi-step jobs      →  it completes goals, with a check
Prepared work        →  it gets things ready before you ask
```

The larger plan lives in [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

## Documentation

| Document | What's inside |
|---|---|
| [`WHAT_SOTTO_DOES_TODAY.md`](WHAT_SOTTO_DOES_TODAY.md) | Plain-language sheet of everything that works right now |
| [`FEATURES.md`](FEATURES.md) | Full feature inventory |
| [`V1_PRODUCT_PLAN.md`](V1_PRODUCT_PLAN.md) | Product plan and test checklist |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Engineering roadmap, phased |
| [`ACCOUNTS_SETUP.md`](ACCOUNTS_SETUP.md) | Connecting Google, email, and calendar |
| [`VOICE_GUIDE.md`](VOICE_GUIDE.md) | Voices and the custom voice pipeline |
| [`TESTING.md`](TESTING.md) | How to test the assistant |
| [`BRAND_DISCOVERY.md`](BRAND_DISCOVERY.md) | Product identity and brand direction |
| [`CAPABILITY_RESEARCH.md`](CAPABILITY_RESEARCH.md) | Research notes: what's possible, what's next |
| [`HANDOFF.md`](HANDOFF.md) | Maintainer notes: architecture, files, gotchas |
| [`DOCUMENTATION.md`](DOCUMENTATION.md) | Where documentation lives and how it's maintained |

## Limitations

- **Windows only** (10/11, 64-bit). No macOS or mobile.
- **Bring your own AI key.** Free provider tiers work but can be slow or flaky; paid keys are steadier.
- **Email and calendar need your Google setup** (or an `.ics` feed). Outlook IMAP with app passwords is not supported — Microsoft disabled basic auth; a Graph integration is future work.
- **No GPU:** built-in voices are instant, but the optional custom voice runs on CPU and is slow — seconds per sentence, about a minute for a long paragraph.
- **Multi-step goals are not here yet.** "Get me ready for tomorrow's interview" as a single ask is the next milestone (the agent kernel), not a current claim.
- **Screenshots and docs can lag the newest UI** occasionally; core flows are kept current.
- **Single user, single machine.** No accounts, no sync.
- Early software: expect rough edges, and no installer yet.

## Privacy & Permissions

- **Microphone** — used only while you're holding to talk. Speech recognition runs on your PC; audio isn't stored.
- **AI provider** — the reasoning happens through the provider you choose, with your own key. Only the text of your request goes out; files, audio, and credentials stay local.
- **Google account (optional)** — you sign in yourself; tokens stay on your machine, and you can disconnect any time from Settings.
- **Secrets** — encrypted on your PC before being stored (Windows DPAPI, under `%LOCALAPPDATA%\RealAssistant`).
- **Screen** — read only when you ask.
- **Consequential actions** — confirmations before sending, deleting, or power actions; a local record of actions is kept.
- **No telemetry.** Nothing is sent anywhere except your chosen AI provider.

## Contributing

An early, single-maintainer project. Found a bug or have a suggestion? Open a GitHub issue with what you tried and what happened. Keep pull requests small and focused; run `run.bat check` before submitting. For anything larger, please open an issue first.

## Acknowledgements

- **UI & app shell:** [pywebview](https://pywebview.flowrl.com/) (WebView2); PySide6 for the earlier Qt build
- **Speech recognition:** [Vosk](https://alphacephei.com/vosk/) and [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — both run locally
- **Speech output:** Windows SAPI voices; the custom-voice pipeline builds on the RVC community's work (via Applio), adapted to run without the fairseq dependency
- **AI providers:** OpenRouter, Groq, Google Gemini, and GitHub Models — bring your own key
- **Google:** Gmail and Calendar APIs, with your own sign-in
- **Foundations:** numpy, sounddevice, pypdf, Pillow, psutil, pycaw, ddgs, python-dotenv

## License

No license has been chosen for this project yet — all rights reserved by default. A license will be added before any public release.
