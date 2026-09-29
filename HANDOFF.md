# RealAssistant / voiceStra — Complete Project Handoff

_Everything about this project: what it is, how every piece works, how to rebuild it from nothing,
what was already fixed and why, and what the next person/AI must not break._

**Repo:** https://github.com/srav-ku/voiceStra (local folder: `C:\Users\srava\Desktop\RealAssistant`)
**Git state:** all work committed locally up to `78f17a5`. **Push is blocked** — the GitHub token in
`.env` was rotated and currently returns 403; add a working token to push.

---

## 1) What this is

A local-first **voice-first Windows desktop assistant** with a human persona ("Sotto" UI):
- Talk (hold Space / click mic) or type → it *does things on the PC* (62 tools: open apps,
  window control, files, reminders, system info, clipboard, screenshots, weather…)
- It **speaks replies aloud** (Windows SAPI voices, plus an optional **custom cloned voice**
  — "Scarlett" — running fully offline via an RVC pipeline)
- Persistent memory, sessions/history, notes, reminders, audit log, proactive nudges
- UI: HTML/CSS/JS (Sotto design system) inside a native **pywebview** window — no browser chrome

**Stage:** working product, pre-distribution. Packaging/first-run/updater not built yet — see
`V1_PRODUCT_PLAN.md` in this folder for the stage table, the V1 plan, and the full test checklist.

---

## 2) Quick start (dev machine)

```bat
run.bat           :: text console mode
run.bat ui        :: THE APP (pywebview window; this is the product)
run.bat qt        :: old PySide6 build (reference only, superseded)
run.bat voice     :: terminal voice loop
run.bat check     :: voice diagnostics        run.bat mic  :: +4s mic test
run.bat providers :: test every AI provider   run.bat api  :: quick service check
```

**NEVER run plain `python`** — always `run.bat` (the venv python is
`C:\Users\srava\Desktop\Python\.venv\RealAssistant\Scripts\python.exe`, Python 3.12.3).

---

## 3) Environment & paths

| What | Where |
|---|---|
| App code | `C:\Users\srava\Desktop\RealAssistant\` |
| API keys | `.env` — names: `GROQ_API_KEY`, `GEMINI_API_KEY`, `GITHUB_TOKEN`, `OPENROUTER_API_KEY` |
| Settings | `%LOCALAPPDATA%\RealAssistant\settings.json` (see §8) |
| Sessions / memory / notes / audit | `%LOCALAPPDATA%\RealAssistant\` (sessions/, memory files, audit log) |
| **Runtime log (READ THIS FIRST when anything misbehaves)** | `%LOCALAPPDATA%\RealAssistant\ui.log` |
| RVC worker log | `%LOCALAPPDATA%\RealAssistant\rvc_worker.log` |
| Custom voice models | `%LOCALAPPDATA%\RealAssistant\voices\scarlett\{scarlett.pth, scarlett.index}` |
| Original model drop (user's Desktop) | `C:\Users\srava\Desktop\scarlett\` |
| WebView2 profile (theme persistence) | `%LOCALAPPDATA%\RealAssistant\webview\` |
| STT models | vosk small: `%LOCALAPPDATA%\RealAssistant\models\vosk-model-small-en-us-0.15`; faster-whisper: HF cache `~\.cache\huggingface` |
| RVC base models (auto-downloaded) | `…\.venv\RealAssistant\Lib\site-packages\rvc_python\base_model\` (hubert_base.pt 180MB — unused; rmvpe.pt 172MB; rmvpe.onnx 345MB) |
| ContentVec (auto-downloaded) | HF cache: `models--lengyue233--content-vec-best` |

User data never lives in the app folder — that's deliberate (clean installs/uninstalls).

---

## 4) File map (project root)

| File | Role |
|---|---|
| `main.py` | text console entry |
| `ui_app.py` | **app entry** — creates the pywebview window ("Sotto", light backdrop, persistent storage_path). `api.start()` wrapped in try/except so warm-up can never block the window |
| `ui_bridge.py` | **the JS↔Python bridge** (`Api` class). Every method returns JSON. Streaming = push events to a queue + `poll()`. See §7 |
| `ui/` | the UI: `index.html`, `sotto.css`, `sotto-tokens.css`, `sotto.js` (see §6E). `ui/ui_app.py` is a stray copy — ignore/delete |
| `core.py` | `Assistant` — conversation loop: builds messages, streams via `ai_engine.stream_ai`, runs tool calls, never-silent fallbacks, text tool-call recovery, memory compression |
| `ai_engine.py` | multi-provider chain + streaming + tool calls. See §6A |
| `tools.py` | **62 tools** via `@tool(name=...)` decorator + `REGISTRY`; `APP_INDEX` (app scan); `SYSTEM_APPS`; app resolution (registry App Paths → index → fuzzy). Add tools by decorating a function |
| `config.py` | paths, `_SETTINGS` from settings.json, `SYSTEM_PROMPT` (persona "real person next to you"), provider defaults, `CUSTOM_VOICE`, `RVC_F0METHOD`, `RVC_INDEX_RATE` |
| `memory.py` | long-term facts + summary; `facts()`, `add_fact()`, `context_block()` |
| `sessions.py` | chat sessions on disk (`list/create/load/save/delete/rename`) |
| `reminders.py` | timers/reminders thread; fires notifications |
| `notes.py` | quick notes (`add/list/search/remove`) |
| `audit.py` | every tool run logged (`log()`, `recent()`) |
| `learn.py` | background learning from turns (facts extracted every N turns) |
| `proactive.py` | watcher that can surface nudges (interval in settings) |
| `briefing.py` | morning briefing content |
| `voice.py` | **speech**: SAPI persistent speaker (`speaker()/say()/stop_speaking()`, `say()` ≈0.05s), `speak_to_wav()` (render to WAV — used by the custom-voice pipeline), STT (`transcribe_wav`, vosk + faster-whisper), `MicStream` (live level), warm-up |
| `voice_convert.py` | **custom voice client**: probes runtime, manages the persistent `rvc_worker.py` (spawn/lock/timeout/kill), `convert()`, `play_wav()`, `stop_playback()`, `prewarm()`, `available_voices()` |
| `rvc_worker.py` | **custom voice engine**: loads RVC model once, converts one WAV per line (JSON protocol on stdout; library chatter goes to stderr) |
| `audio.py` | `MicStream` (record + live level) used by bridge listening |
| `winctl.py`, `sysactions.py`, `sysinfo.py`, `fileops.py`, `display.py`, `browser.py` | window snapping, system actions (lock/sleep/volume…), system info, file ops, display, browser helpers — surfaced as tools |
| `confirm.py` | yes/no confirmation gate for dangerous tools (dialog + chat-style) |
| `build.py`, `RealAssistant.spec`, `dist/`, `build/` | PyInstaller build (used in earlier phases; needs revisit for the RVC stack) |
| `selftest.py`, `test_e2e.py`, `voice_check.py`, `providers_check.py`, `api_check.py`, `mic_test.py`, `verify_apps.py` | diagnostics; `ci/selftest.yml` runs in CI |
| Docs | `README.md`, `TESTING.md`, `VOICE_GUIDE.md` (how the custom voice was trained on Colab/Applio + install), `VOICE_TEST.md` (10-step voice test), `PROJECT_BRIEF.md` (original brief), `V1_PRODUCT_PLAN.md` (stage + plan + checklist), **this file** |
| `app_qt.py`, `voice_ui.py` | superseded UIs (kept for reference) |
| `_*.py`, `_*.wav` | scratch/bench files from development — safe to ignore; gitignored |

---

## 5) How it runs (flows)

**Text/voice chat loop:** JS `send(text)` → bridge `send()` (starts background thread; `_busy=True`)
→ `core.ask()` → `ai_engine.stream_ai` (provider chain) → tool calls executed (each logged + pushed
as `tool` event) → reply text **streamed** to bridge → bridge buffers into **sentences** and pushes
`say` events (sentence = displayed + spoken) → `done{text:'', full:<reply>}` → UI renders answer,
actions row, follow-ups. Voice input: JS holds `listen_level` polling; auto-stops ~1.8s after speech
ends; bridge `listen_stop()` transcribes (vosk/whisper) → same `send()` path.

**Custom voice path:** UI speakOut → `say(sentence)` bridge → `voice.speak()` → if `custom_voice`
is set: enqueue into a dedicated thread → `speak_to_wav()` (SAPI render) → `voice_convert.convert()`
→ rvc_worker converts (~12–17s/sentence CPU) → `play_wav()` (blocking) → next queued sentence.
Stop (`stop_speaking`) mutes the rest of the turn (remaining text still displays).

---

## 6) The systems in detail

### A) `ai_engine.py` — provider chain (READ BEFORE TOUCHING)
- Providers tried in order from settings `providers`; **sticky**: last provider that worked goes
  first next time (`provider_state.json`).
- Cooldowns on failure: 503→120s, 429→60s, conn→60s. Cooled-down providers are skipped.
- Non-Groq providers use plain HTTP (`_http_open/_http_parse/_http_stream`) because the Groq SDK
  fails against them. Streaming + tool calls work over HTTP.
- `_create()`: retries once on 503/502/timeout after 4s; **if "every provider failed", waits for the
  soonest cooldown (≤30s) and retries** (v41) — then raises `_friendly(...)`.
- `AUTH_PREFIX` trick avoids secret masking of the `Authorization` header.
- **Known environment facts:** `models.github.ai` is ISP-blocked (returns fake 200 "OK" — unusable);
  Groq 403s on some networks but works elsewhere; **OpenRouter free models are the working core**
  (or-ling first, or-nemotron second). Treat the chain as: OpenRouter free ↦ groq ↦ gemini ↦ github.

### B) `core.py` — conversation loop
- Persona/system prompt in `config.SYSTEM_PROMPT` ("real person", short replies, never mention tools,
  never narrate plans — that last rule was added after a leak incident).
- `ask()`: loops ≤MAX_TOOL_ROUNDS; streams text; runs tools (dangerous ones via `confirm`);
  **never-silent**: if all attempts return empty → one plain `complete()` through the full chain;
  if still empty, the bridge turns it into a visible error+retry. **Text-tool-call recovery**:
  free models sometimes emit `{"tool": "...", "arguments": {...}}` as plain text — `ask()` detects
  it (name must exist in REGISTRY) and executes it like a real tool call.
- Memory compression: summarizes old turns into `memory.summary()` when turns exceed thresholds.

### C) `voice.py` — speech I/O
- Persistent PowerShell SAPI process (`Speaker`) — `say()` ~50ms per call; utterances queue inside
  SAPI (this is what makes clause-by-clause streaming possible).
- `stop_speaking()` kills the speaker + purges the custom-voice queue + stops custom playback.
- Custom voice sentences go through `_cv_queue` → `_cv_worker` thread (ordered, never overlapping).
- `speak_to_wav()` — SAPI → WAV file (16k or voice default; fed to the converter).
- STT: `transcribe_wav()` (vosk small offline; faster-whisper base.en installed too); model warm-up
  at app start; `MicStream` provides live level for the listening visual.

### D) Custom voice pipeline (Scarlett) — the full story
**Why it's unusual:** this PC has no GPU and **fairseq cannot install** on Python 3.12/Windows
(no compiler, no wheels). The standard RVC stack was therefore replaced:

1. **Installed:** `torch 2.14.0+cpu`, `torchaudio` (CPU wheels), `rvc-python 0.1.4` **with `--no-deps`**
   (its numpy pin `<=1.25.3` is unsatisfiable on py3.12 — numpy stays **2.5.3**), plus by hand:
   `torchcrepe`, `ffmpeg-python`, `loguru`, `transformers`, `librosa`, `soundfile`, `faiss-cpu`,
   `praat-parselmouth`, `pyworld`, `av`, `tqdm`.
2. **Patched inside site-packages/rvc_python** (reproduce these or the stack won't run):
   - `modules/vc/utils.py` — **rewritten**: `load_hubert()` now loads a **transformers ContentVec**
     (`lengyue233/content-vec-best`, auto-downloads to HF cache) instead of fairseq.
   - `modules/vc/contentvec_hf.py` — **added**: adapter class exposing the fairseq-like API
     (`.to/.eval/.extract_features(source,padding_mask,output_layer)->(feats,mask)`; `final_proj` = identity, v2 only).
   - `modules/vc/pipeline.py` — index cache: `_IDX_CACHE = {}` + faiss index cached between
     conversions (instead of reloading a 120MB index every sentence).
   - `lib/jit/get_hubert.py` still imports fairseq but is **not on the runtime path**; `import rvc_python.infer` works.
3. **Model files:** user's Applio-trained RVC v2 (150 epochs) at
   `%LOCALAPPDATA%\RealAssistant\voices\scarlett\{scarlett.pth, scarlett.index}`.
4. **Worker:** `rvc_worker.py` — loads once, converts per line. Protocol: JSON on stdout
   (library prints are redirected to stderr), `__quit__` to stop. Settings-driven:
   `rvc_f0method` (pm — faster; rmvpe — higher fidelity) and `rvc_index_rate` (0.5).
5. **Client:** `voice_convert.py` — spawns/locks/kills the worker, 180s ready timeout / 120s per
   task, falls back to the *plain* audio when conversion fails (never silence).
6. **Voice is a CHOICE:** voice list shows `Scarlett (custom)`; picking it sets `custom_voice` +
   prewarms the worker; picking any system voice disables the pipeline entirely (fast path).
7. **Measured on this CPU:** warm conversion ≈ **12–17s per sentence** (~3s compute per 1s of audio),
   one-time warm-up ≈ 50s after selection, worker RAM ≈ 1.4GB. Quality verified by round-trip STT
   (converted speech reads back word-perfect).

### E) The UI (`ui/`) — Sotto v4
- `index.html` — shell: header (History/Memory/Settings + theme), presence (field layers + canvas
  thread), exchange, dock (mic ↔ inline typing), sheets (History/Memory/Settings), quick-settings
  popover, toast. **Default theme is LIGHT** (`data-theme="light"` on `<body>` — do not revert).
- `sotto.js` — one IIFE. Presence renderer (states: idle·ready·listening·understanding·thinking·
  acting·waiting·responding·interrupted·denied·offline), hold-Space push-to-talk, **auto end-of-speech**
  (silence ~1.8s after speech detected; 8s if nothing heard; 60s cap), error auto-retry (4s then 30s),
  `ui.log` callIf('log') markers, first-run scan prompt, theme persistence (`sotto-theme-v2` key).
- `sotto.css` / `sotto-tokens.css` — the design system (both themes). Light-theme borders for
  interactive surfaces were added (v39); short-window compaction; z-order fixed so the glow never
  covers content — **don't regress these**.

### F) UI event & bridge contract (do not break)

**Bridge methods** (`window.pywebview.api.*`, all return JSON strings unless noted):
`info` · `send(text)` · `poll()` · `busy()` (bool) · `listen_start/listen_level/listen_stop` ·
`say(text)` · `say_slow(text)` · `stop_speaking()` · `set_voice(name)` · `scan_apps()` ·
`list_sessions/new_session/open_session/delete_session/rename_session` ·
`list_memory/list_notes/list_tasks/list_activity` · `set_sound(on)/set_wake(on)` · `status()` · `log(msg)`.
UI capability-gates: anything missing simply hides.

**Events pushed to `poll()`:** `title`, `text` (display only), `say` (display+speak), `speak_only`
(speech only — used for repeat/slower), `tool{name,result,rows?}`, `state{name,label}`, `error`,
`done{text:'',full}` , `session`, `learned`.
**UI-side extras it understands:** `intent`, `notice`, `prompt/clear_prompt`, `progress`, `ask`,
`speaking/speaking_end` (optional, capability-gated).

**Voice commands handled WITHOUT the LLM** (in `ui_bridge.send`): "repeat that" / "say that again"
→ `speak_only` replay; "say it slower" → `speak_only{rate:0.8}` → `say_slow`.

---

## 7) Settings reference (`%LOCALAPPDATA%\RealAssistant\settings.json`)

`model`, `api_key_env`, `base_url`, `temperature`, `reasoning_effort`, `max_tokens`, `denied_tools`,
`proactive`, `proactive_interval_seconds`, `confirm_mode`, `voice_name` ("" = system default),
`voice_rate`, `mic_device` (null = default), `stt_model` ("base.en"), `custom_voice` ("scarlett" or ""),
`providers[]` (name/base_url/api_key_env/model/timeout/reasoning_effort), `rvc_f0method` ("pm"),
`rvc_index_rate` (0.5), `scan_count`, (`scan_done` set after a user scan; its absence triggers the
first-run scan prompt).

---

## 8) Reproduce on a fresh machine

1. Python 3.12 + venv; `pip install -r requirements.txt` (pywebview essential; PySide6 only for the
   old `run.bat qt`).
2. Create `.env` with the four keys (OpenRouter is the one that matters most).
3. First run: `run.bat ui` → models warm up; vosk small model auto-downloads; scan prompt appears.
4. **Custom voice (optional):**
   - `pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio`
   - `pip install --no-deps rvc-python` then `pip install torchcrepe ffmpeg-python loguru transformers librosa soundfile faiss-cpu praat-parselmouth pyworld av tqdm`
   - Apply the three site-packages patches (§6D.2) — **required**, fairseq is not installable.
   - Put the model at `%LOCALAPPDATA%\RealAssistant\voices\<name>\<name>.pth` (+ `.index`),
     set `custom_voice`, selectable in the app's voice list.

---

## 9) Critical lessons (please don't regress)

1. **Light theme default + real persistence** — user requirement. Persistence needs
   `private_mode=False` + `storage_path` in `ui_app.py`; pywebview's default private mode silently
   discards everything.
2. **Never-silent turns** — empty model replies must never render as a blank turn (engine retry →
   bridge error event → UI retry). Same for tool-call-as-text (recovered in `ask()`).
3. **Leak guard** — weak free models leak planning text ("The user is asking…"); bridge holds it
   back and rewrites once. Prompt also forbids narration.
4. **Speech timing** — sentence-by-sentence `say` events; `done` carries no text (bridge sends
   `done{text:'',full}`) so nothing is spoken twice. Stop ≠ cancel: interrupting mutes the rest,
   the task continues.
5. **Mic auto-stop** — the mic must end itself after silence; a mic waiting for a manual "stop"
   reads as broken.
6. **`ui.log` first** — when something "does nothing", read `%LOCALAPPDATA%\RealAssistant\ui.log`
   before guessing. It records sends, events, errors, transcripts.
7. **RAM discipline** — this machine runs at ~95% RAM; the custom-voice worker takes ~1.4GB. Close
   heavy apps when using it. The app itself stays light when a system voice is selected.
8. **Don't trust "it built" as "it works"** — verify on-device/real runs; several bugs here were
   only visible live (window focus, theme, silent turns).
9. **`run.bat` only** — plain `python` is a different interpreter.
10. GitHub push needs a token with repo scope; current one in `.env` gets 403.

---

## 10) Testing

- Fast checks: `run.bat check`, `run.bat providers`, `run.bat api`, `run.bat mic`.
- **Full checklist** (statuses/what to record): see `V1_PRODUCT_PLAN.md` §Part 4.
- The golden path to demo: type "what is my system status" (answer + bars card + speech);
  voice "open notepad"; panels Ctrl+Shift+H/M/S; theme Ctrl+Shift+D; Scarlett voice selectable.

## 11) Known limitations / future ideas

- Custom voice: CPU-only ~15s/sentence (12–17s warm). Speed options already measured: `pm` (in use),
  dropping index = no gain. **Next lever: ONNX export** of the RVC model (1.5–3× possible).
- No installer/auto-update yet (plan in `V1_PRODUCT_PLAN.md` Part 3).
- RVC runtime is a hand-patched stack — treat `site-packages/rvc_python` as part of this project;
  keep a copy of the patches (§6D) with any reinstall.
- Optional future: mic-device picker in Settings, sound effects, file drop.

---

_If you are an AI inheriting this project: read this file, then `V1_PRODUCT_PLAN.md`,
then open `ui_bridge.py` and `ui/sotto.js` (the contract in §6F). Check `git log` for the story of
every fix. Run everything through `run.bat`. Verify live before claiming anything works._
