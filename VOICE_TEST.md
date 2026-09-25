# Voice test script

A short, high-coverage test: speak these in order and check the expected result. ~5 minutes.
You don't need to test every tool - these 10 cover the important paths.

## 0. Sanity check (no talking)

```powershell
.\run.bat check
```

Use `run.bat` - plain `python` may be a different interpreter that lacks the voice libraries.
Everything should say **PASS**. For the mic test:

```powershell
.\run.bat mic      # speak during the 4s; check `level` and `heard:`
```

Low level means the default mic isn't the one you speak into. Run `voice_check.py` to see the
device list, then set `"mic_device": <index>` in `settings.json`.

## How voice mode works

```powershell
.\run.bat voice
```

- It lists your voices, then shows `[Enter = talk]`.
- Press **Enter** -> it says `listening...` -> speak -> it prints `heard: "<...>"`.
- It performs the action, then **speaks the reply out loud**.
- You can also just **type** a request at the `[Enter = talk]` prompt.

## The script - say these, in order

| # | Say | Expected |
|---|-----|----------|
| 1 | "what's my system status" | info only, no side effects; spoken back |
| 2 | "open notepad" | Notepad opens; heard a short confirmation |
| 3 | "what's the weather" | weather read aloud |
| 4 | "list my notes" | your notes spoken |
| 5 | "remind me in 1 minute to stretch" | it confirms; after a minute you **hear** the reminder |
| 6 | "what do you know about me" | it speaks the facts it remembers |
| 7 | "open chrome and set the volume to 30" | multi-step: both happen, one short confirmation |
| 8 | "close notepad" -> it **asks out loud** -> say **"yes"** | Notepad closes (**key test: voice approval**) |
| 9 | "close notepad" again -> when it asks, say **"no"** | nothing happens, it says it was cancelled (**key test: voice cancel**) |
| 10 | "shut down in 2 minutes" -> say **"yes"** -> then "cancel shutdown" | Windows countdown appears, then stops |

## What "pass" looks like

- It **hears** you (the `heard:` line roughly matches what you said)
- It **does** the thing
- You **hear** its reply
- Risky actions **ask first** and respect your yes/no

## If it mishears you

- Speak in **short phrases**, wait a beat after pressing Enter, keep background noise down.
- `python voice_check.py --mic` - the `level` should be several hundred or more.
- Wrong mic? `"mic_device": <index>` in `settings.json`.
- The bundled English model is small/basic. If accuracy is poor, a larger Vosk model
  (or faster-whisper) improves it - still offline and CPU-only.

## Then: your custom voice

Once 1-10 pass, we plug in the actress voice: drop the RVC model into
`%LOCALAPPDATA%\RealAssistant\voices\<name>\` and set `"custom_voice": "<name>"`.
The normal voice stays as the fallback, so nothing breaks if the model isn't there.
