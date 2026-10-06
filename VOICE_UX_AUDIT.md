# Voice & Experience Audit
### Research-informed review of every Sotto feature — October 2026

**How to read this:** markers — **[R]** researched this pass (sources noted) · **[K]** established industry practice · **[V]** verified on this build with evidence · **[F]** fixed in this pass · **[Q]** queued as follow-up.

---

## Part A — What established products do (research findings)

### A1. End-of-speech detection ("endpointing")
- Home Assistant's local voice pipeline uses **Silero VAD** for internal end-of-speech detection (via `pysilero-vad`), configurable per pipeline. **[R]**
- Production voice-agent stacks (AWS reference deployments of Pipecat) run **Silero VAD with silence thresholds around 0.3s** for snappy conversational turn-taking, with tuning expected per deployment. **[R]**
- Practical takeaway: users feel latency mostly in *the gap after they stop talking*. For command-style assistants the usable band is roughly **0.5–1.5s of silence**.
- **Sotto's choice:** adaptive level-based VAD with a **1.2s end-of-silence default** (configurable via `voice_end_silence` setting). Why not Silero today: `torch` currently lives only in the isolated custom-voice worker process; pulling it into the main app adds ~300MB RAM on a modest machine. **Silero (or the lighter WebRTC-VAD) is the documented upgrade path.** **[Q]**

### A2. Barge-in (interrupting the assistant mid-speech)
- Microsoft 365 Copilot voice (Nov 2025, official): *"Users can speak freely during voice chats and interrupt Copilot at any time. When interrupted, Copilot will stop speaking, listen to the new input."* **[R]**
- Historically Siri simply **closed the microphone during TTS playback** to avoid echo cancellation — the well-known downside: you couldn't interrupt; you had to wait for the full response. **[R]**
- **Sotto's choice:** starting to listen **always stops any ongoing speech first** (barge-in implemented this pass). Sotto never keeps the mic open during TTS — exactly to avoid self-echo/false interrupts — and solves interruption the modern way (explicit interrupt via hotkey/orb/mic) rather than the old Siri way. **[F]**

### A3. Wake word
- Copilot ships *"Hey Copilot"* as an **opt-in** feature. **[R]**
- Porcupine / openWakeWord are the local standards; they run as a persistent, low-cost background service. **[R]**
- **Sotto:** wake word exists, ships **disabled by default** (matching industry practice), enabled from Settings. Summon hotkey **Ctrl+Shift+S** was documented in settings but never actually registered — now registered and verified. **[F]**

### A4. Push-to-talk
- Copilot's own pattern: **hold `Win+C` for 1–2 seconds** to talk; wake word is the hands-free alternative. **[R]**
- **Sotto:** a **single tap starts listening** and it auto-stops when you finish — no holding, no second click. Ctrl+Space / Ctrl+Shift+S / pill orb / mic button / Space all trigger the same flow. **[F]**

### A5. Latency
- Recurring guidance: perceived latency is cut by **immediate feedback** and **speaking the first useful sentence as soon as it exists**, more than by raw end-to-end speed. **[K]**
- **Sotto:** immediate listening/thinking states + sentence-by-sentence speech already follow this. **[V]**

---

## Part B — Feature-by-feature audit (this build)

| # | Feature | Implementation | Findings / issues | Status |
|---|---|---|---|---|
| 1 | **Voice input** | Server-side listen cycle: mic capture → adaptive VAD (3-frame onset, **1.2s end-silence**, 9s no-speech abort, 45s cap) → local transcription → turn. Triggers: pill orb, Ctrl+Space, Ctrl+Shift+S, mic button, Space. Tap again = finish early-and-send; Esc = cancel. | (a) Was driven by the main window's JS — stalled whenever the window was minimized (the *"pill not listening"* root cause) → rebuilt server-side. (b) No barge-in → fixed. (c) Overlap guard while busy → added. | **[F][V]** (loop start/state/cancel verified in log; recognition accuracy needs your mic) |
| 2 | **Voice output** | Windows SAPI voices + optional custom RVC voice (separate process); sentence streaming; stop vs mute semantics. | Barge-in now stops speech when you start talking. | **[F][V]** |
| 3 | **Overlay pill** | Frameless always-on-top pywebview window. Rules: hidden while the app is focused **or visible-and-idle**; live states whenever the assistant is active anywhere; quiet presence only when minimized/hidden; 8s launch grace; ~1.1s settle; fade in/out; watchdog resyncs stray windows. | Earlier: flashed at launch, appeared during switching, stuck black box → all addressed by new rules + watchdog (working in today's logs). Remaining: small corner-edge artifacts. | **[F][V]** / corners **[Q]** |
| 4 | **Global hotkeys** | Ctrl+Space and Ctrl+Shift+S, both registered as native Windows hotkeys; log confirms `Ctrl+Space=True Ctrl+Shift+S=True`. | Ctrl+Shift+S was claimed but unimplemented → now real. | **[F][V]** |
| 5 | **Wake word** | Local, opt-in (`"hey sotto"`), disabled by default. | Quality pass pending if you enable it. | **[V]** / **[Q]** |
| 6 | **Lock** | Opt-in voice passphrase + recovery via Windows sign-in; verified not appearing when disabled. | Fixed earlier this week (overlay was force-showing; fails open). | **[V]** |
| 7 | **Email** | Your own Google account: summary / search / read / draft / send with confirmation. | Drafts are local until sent (not Gmail-native drafts). | **[V]** / **[Q]** |
| 8 | **Calendar** | Read today/week; add events (Google or .ics). | Moving/cancelling + "find a free hour" still missing. | **[V]** / **[Q]** |
| 9 | **Files** | Find by name/content; read PDFs; organize Downloads (+undo); move/copy/rename; recycle-bin deletes. | — | **[V]** (earlier passes) |
| 10 | **Screen** | On-request OCR / window text reading. | — | **[V]** (earlier passes) |
| 11 | **Routines / notes / reminders / memory** | Save & run action sequences; notes; reminders; visible memory. | Re-verification pass queued with your next test round. | **[Q re-check]** |
| 12 | **Tool-call resilience** | All three leaked-call forms parsed & executed (XML `<function=>`, `<tool_call>{json}`, bare `{json}`); near-miss names (`open_app`) and arg names auto-normalized; bare-JSON held from speech; repair guard; empty-after-tools → clean confirmation. | Fixed today across four commits; live-proven: Notepad and Calculator really opened, with a clean spoken confirmation. | **[F][V]** |
| 13 | **Reliability** | Single-instance guard; never-silent turns; provider retry/cooldowns; boot log clean. | Stale second instance found & killed earlier today. | **[V]** |
| 14 | **Performance** | Local STT; custom voice isolated in its own process; free-tier AI latency is the variable. | — | **[V]** |

---

## Part C — Fixes landed today (commit trail)

- `6653bdf` — execute tool calls leaked as text (JSON+XML recovery); harden reply repair; smooth overlay presence timing
- `6f2c10b` — repair guard catches "see a draft"-style meta replies
- `2d020f9` — clean spoken confirmation after recovered tool calls
- `a564b51` — normalize near-miss tool names/args; hold bare-JSON calls from speech
- `8e11718` — **server-side hands-free listening with auto end-of-speech** (pill/hotkey/mic); overlay presence only when out of sight
- `58e92f8` — barge-in on listen start; **Ctrl+Shift+S hotkey**; configurable end-of-speech (1.2s default)

## Part D — Honest test ledger

**Verified by me on this build:** hotkey registration (both True), overlay watchdog (`pill hidden (resync)` in logs), voice loop mechanics (start → listening state → cancel → idle), real tool execution (Notepad, Calculator), parser unit tests (all three leak forms), clean app boot logs.

**Only your voice can verify:** recognition accuracy on your microphone, how the 1.2s end-of-silence *feels*, barge-in feel, pill behavior across your real switching patterns.

**Queued polish:** pill corner pixels; calendar move/free-time; Gmail-native drafts; Silero/WebRTC VAD upgrade; wake-word quality pass; routine/memory re-checks.
