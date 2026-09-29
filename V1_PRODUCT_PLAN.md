# RealAssistant — Stage Assessment & V1 Product Plan

_What stage is this product at, how do Apple-class products get built from install → daily use,
and what's left before this can ship as an app other people can install._

---

## Part 1 — How good products are built (research, distilled)

### 1.1 Install = one decision, then done
- **One file, one flow.** Apple ships single artifacts (drag-to-Applications; one MSI/EXE on Windows).
  No "choose components", no toolbars, no email gate before value.
- **Signed.** Windows: code-signing is what prevents "Unknown publisher" fear. (MS Store path exists
  too — MSIX packaging then store-side signing — but it's slower; Inno Setup + eventually a cert is
  the pragmatic path.)
- **Uninstall must be clean, and data placement must be right:** app code in Program Files,
  user data in `%LOCALAPPDATA%\<App>` — exactly how this app already stores settings, sessions,
  models, voices. That was deliberate and matches the platform rulebook.
- Sources seen: [Windows Installer best practices (Microsoft Learn)](https://learn.microsoft.com/),
  [Inno Setup](https://jrsoftware.org/), [advancedinstaller.com comparison (Feb 2025)](https://www.advancedinstaller.com/).

### 1.2 First launch = the product itself, not a tutorial
- Apple-class products **don't front-load a wizard or "click here → next → next" tour**. The first
  real interaction teaches. (This matches the onboarding note you were given: for a conversation
  product, *the first conversation is the tutorial*.)
- Ask **only what cannot be auto-detected**, ask it **in context**, once, in plain words:
  - microphone (only if the default one hears nothing),
  - AI connection (only if the user runs their own keys),
  - scanning the computer for apps (already implemented: a quiet prompt line + Settings rescan).
- **Permission priming:** explain *why* before the OS asks, and always *at the moment of need* —
  never all upfront. (Same rule as "let the user see listen → act → speak → finish" from your note.)
- **Empty states teach.** "Nothing here yet — say 'remind me…'" is onboarding that costs nothing.
  This app already does this across History/Memory segments.
- **Progressive disclosure** — depth stays hidden until needed. Confirmed across sources:
  [metizsoft.com](https://metizsoft.com/) (Nov 2024), [invokemedia.co.uk](https://invokemedia.co.uk/)
  (Sep 2025). This is exactly the 4-icon + sheets architecture of the current UI.

### 1.3 Daily use = calm, fast, reliable
- The product must **never show raw errors**; failures degrade to a spoken fallback (already: plain
  voice when the custom engine fails; calm notices + auto-retry when the AI hiccups).
- **Memory of choices** (theme, voice, mic, scan) persists — implemented.
- **Updates are silent or one-tap**; the user should never think about them.

### 1.4 Release quality bar (what "done" means for v1)
1. Install on a clean machine → first real answer in under 2 minutes (excluding downloads).
2. No crashes across a full test pass; errors always human, never raw.
3. Uninstall leaves nothing behind except (optionally) user data, with clean removal.
4. Every feature either works, or is invisible (capability-gated) — never a dead control.

---

## Part 2 — Where RealAssistant stands (honest stage assessment)

**Stage: working product, pre-distribution.** Core experience works end-to-end on the dev machine;
what's missing is packaging, first-run polish, and your full validation pass.

| Area | Status | Notes |
|---|---|---|
| Assistant brain (tools · memory · sessions · reminders) | **Done** | 62 tools, verified live |
| Voice input (mic → text) | **Done** | auto-stop listening, live level |
| Voice output — system voices | **Done** | instant, queued, ordered |
| Voice output — custom voice (Scarlett) | **Done** | selectable; ~15s/sentence on this CPU (documented limitation) |
| UI (Sotto v4: presence, panels, conversation layer) | **Done** | dark/light, shortcuts, memory hub, scan |
| Reliability (retry, fallbacks, no-silent-turns, logging) | **Done** | `ui.log` records everything |
| Computer scan (apps index) | **Done** | first-run prompt + Settings rescan |
| **End-to-end validation on your machine** | **In progress** | needs your test pass (checklist below) |
| Installer (Inno Setup) | **Not started** | next step after validation |
| First-run minimal setup (mic check, AI key entry if needed) | **Not started** | design: in-context, no wizard |
| Auto-update | **Not started** | simple version-check → download → restart |
| Packaging strategy for the custom-voice engine | **Not started** | torch is ~2GB: must be optional download, not bundled |
| Code signing | **Not started** | costs money; optional at first (SmartScreen warning) |
| Crash reporting | **Not started** | optional; local log first |

---

## Part 3 — V1 plan (after your validation pass)

1. **Freeze & validate** (you): run the checklist below; log any lag/wrong behavior.
2. **Fix pass** on whatever the validation finds.
3. **Package**: PyInstaller onedir for the app; Inno Setup installer;
   user data stays in `%LOCALAPPDATA%\RealAssistant`.
4. **First-run, minimal**: no wizard. In-context asks only:
   - mic test appears only if the first listen hears nothing;
   - AI key screen appears only if no provider key works (for users who bring their own);
   - "Scan this computer?" prompt (done) + Settings rescan (done).
5. **Custom voice as an optional pack**: "Install the Scarlett voice (engine + model, ~2.5GB)"
   → downloads once, registers in the voice list. Base install stays ~150MB.
6. **Auto-update + version display**; then optionally signing.

---

## Part 4 — What to test (your validation checklist)

Run in order. For each: expected result → note ✅ or ❌ + any lag/strange thing.

**A. Start & basics**
1. `.\run.bat ui` → window opens **light**. Close & reopen → still light. (Theme: Ctrl+Shift+D flips; reopen → remembered.)
2. First-run prompt appears once: *"First time here? Let me look at what's installed…"* → click **Scan now** → toast shows "Found ~223 apps".
3. Settings (Ctrl+Shift+S) → "Installed apps" row shows count; **Scan again** works.

**B. Conversation — typed**
4. Type `what is my system status` → THINKING → answer + CPU/RAM/Battery card → it speaks.
5. Type `remind me to drink water in 2 minutes` → timer card counts down; notification fires at 0.
6. Type nonsense (`blah blah blah`) → it still answers something sane (never blank).

**C. Conversation — voice**
7. Hold **Space**, say *"what time is it"*, release → listening wave stops by itself ~2s after you finish → thinking → spoken answer.
8. Say *"open notepad"* → Notepad opens + short spoken confirmation.
9. While it is speaking, press **Space** → speech stops immediately; the task continues (text still appears).
10. Say *"repeat that"* → replays the last answer instantly. *"say it slower"* → slower replay.

**D. Panels & UI**
11. Ctrl+Shift+H (history — day groups, click one to restore), Ctrl+Shift+M (memory/notes/tasks/activity — all four tabs populate), Ctrl+Shift+S. Switch between them without closing; Esc closes; click outside closes.
12. Light ↔ dark pass on every panel — no clipped text, no washed-out buttons.

**E. The custom voice (Scarlett)**
13. Settings → Spoken voice → **Scarlett (custom)** → ask something short → first sentence waits for engine warm-up (~50s once), then speaks in her voice (~15s/sentence; text appears instantly).
14. Switch back to a system voice → next reply is instant normal speech (engine not used).

**F. Edge behavior (the important one — note anything odd!)**
15. Pull your network (or turn off Wi-Fi) → ask something → it should retry, then tell you calmly; plug back in → works again. Note exact wording/timing.
16. Reopen the app after 10 restarts across the day → all choices remembered (voice, theme, scan done, mic).
17. Note ANY: slowdown over time, freezes, double-speaking, overlapping audio, wrong voice, clipped UI.

Send the results (or just "❌ on #…") and I'll fix whatever fails.

---

## Sources (actually opened this turn)
- Windows Installer best practices — [learn.microsoft.com](https://learn.microsoft.com/)
- Inno Setup — [jrsoftware.org](https://jrsoftware.org/)
- Installer comparisons — [advancedinstaller.com](https://www.advancedinstaller.com/)
- Progressive disclosure — [metizsoft.com](https://metizsoft.com/), [invokemedia.co.uk](https://invokemedia.co.uk/)
- Your onboarding note (attached): first conversation = the tutorial — adopted as the design rule for first-run.
- Note: provider results for Apple-specific queries were too thin to cite; Apple-section principles above
  are standard HIG-class practice restated in our own words rather than quotes.

---

_This file lives with the project so it's part of the product record — update it as stages complete._
