# Sotto — Final Test Checklist
### What to test, with exact samples — to confirm the product is working and build-ready

**How to run this:** go top to bottom. Each test has a **Sample** (exact words or actions) and an **Expected** result. Starred ★ tests are the *critical path* — if all starred tests pass, the product is functionally build-ready; the rest are spot checks.

**Current build:** the app already running on your machine (Sotto window + voice build from Oct 6).

---

## A. The pill (overlay) — 5 min

| # | Do this | Expect |
|---|---|---|
| A1 ★ | Open/click into the Sotto app | **No pill anywhere.** Normal app only. |
| A2 ★ | Minimize Sotto (or click "Send to background") | After ~1 second, white **"Sotto" pill** appears top-center of the screen. |
| A3 ★ | Click back into the Sotto window | Pill disappears quickly (~0.5s). |
| A4 | Stay in another app with Sotto visible behind it (don't minimize) | **No pill** while idle — pill only appears when Sotto is actually doing something. |
| A5 | Click the **↗** on the pill (while minimized) | Sotto window comes back. |

## B. Voice — hands-free (the heart of it) — 10 min

| # | Do this | Expect |
|---|---|---|
| B1 ★ | With the app minimized: **click the pill orb once, then just talk** — e.g. *"what time is it?"* — then **stop talking and wait** | Pill shows **Listening** (bars move) → you stop → it decides you're done (~1.5s) → **Thinking** → speaks the answer. **No second click.** |
| B2 ★ | From any other app (browser, notepad): press **Ctrl+Space**, just talk — *"open notepad"* — stop, wait | Same hands-free flow. You never touch a button to stop. |
| B3 ★ | In the app: press **Space once** (not hold), say *"hello"*, stop, wait | Listens → auto-stops → replies. Pressing Space again *while listening* finishes it immediately. |
| B4 | While it's **speaking**, press **Ctrl+Space** (or click the orb), then talk | It **stops speaking instantly** and listens to you. (Note: to interrupt you must press — the mic stays closed while it speaks, by design, like real assistants.) |
| B5 | While **listening**, press **Esc** | Cancels quietly — nothing is sent. |
| B6 | Tap orb, then stay silent ~10 seconds | "I didn't quite catch that." → back to idle. |
| B7 | After any reply, say: *"say it slower"* | Repeats the last answer, slower. |

## C. Commands actually execute — 5 min

| # | Sample | Expect |
|---|---|---|
| C1 ★ | *"open telegram"* | Telegram actually opens + clean spoken confirmation like *"Telegram's open."* |
| C2 ★ | *"open youtube"* | Browser opens YouTube. |
| C3 | *"search for best gaming laptops"* | Reads you a short summary of results. |

## D. Email (your Google account) — 5 min

| # | Sample | Expect |
|---|---|---|
| D1 ★ | *"anything urgent in my email?"* | Spoken summary of recent/unread mail. |
| D2 | *"reply to the first one saying I'll confirm tonight"* → hear the draft → then say *"send it"* (send to a friend or yourself as a test) | Draft read aloud → asks before sending → sends after "send it". |

## E. Calendar — 2 min

| # | Sample | Expect |
|---|---|---|
| E1 | *"what's on my calendar tomorrow?"* | Reads tomorrow's events. |
| E2 | *"add a test event tomorrow at 6pm"* — then ask again | Event appears in tomorrow's list. |

## F. Files, notes & memory — 5 min

| # | Sample | Expect |
|---|---|---|
| F1 | *"find my resume"* | Finds it (or asks which one). |
| F2 | *"save a note: buy milk"* → *"what are my notes?"* | Note saved, then listed. |
| F3 | *"remember that my favorite color is blue"* → *"what do you remember about me?"* | Remembered and listed. |

## G. Screen reading — 2 min

| # | Sample | Expect |
|---|---|---|
| G1 | Put some text on screen (an error, a page), then: *"what's on my screen?"* | Reads/summarizes what's visible. |

## H. Stability — 3 min

| # | Do this | Expect |
|---|---|---|
| H1 ★ | Close Sotto; start it again (`run.bat ui`). Then try starting it a second time | Second launch says "already running" and exits. |
| H2 | Leave it minimized a while, use other apps | Pill present, machine stays responsive. |
| H3 | Check the app after a restart: theme + settings kept | Light theme stays, connections stay. |

## I. Optional — Lock (skip unless you want it)

| # | Do this | Expect |
|---|---|---|
| I1 | Settings → enable Voice Lock (set passphrase + fallback password) → restart app | Lock screen appears; say passphrase → unlocks. |
| I2 | Click "Forgot passphrase?" → "Verify with Windows" | Windows sign-in prompt (Hello/PIN/password) → reset/remove lock. Nothing deleted. |

---

## Reporting a failure
Tell me: **the exact words you said** + **what happened instead** (or a screenshot, like before). I can read `%LOCALAPPDATA%\RealAssistant\ui.log` for the full internals.

## Build-readiness rule
- **All ★ tests pass** → the product is functionally ready for packaging (build + versioned release).
- Any ★ fails → tell me; I fix, re-verify, and hand you the updated build to re-run only the failed test.

## Known acceptable-for-now polish (NOT blockers)
- Tiny corner-edge pixels on the pill.
- Calendar: moving/cancelling events (reading/adding works).
- Gmail-native drafts (local drafts work).
- Wake word ("hey sotto") quality pass — it's off by default.
