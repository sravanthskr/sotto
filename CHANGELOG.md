# Changelog

All notable changes to Sotto are recorded in this file.

## [1.1.0] - 2026-10-02

### Added
- Voice lock (opt-in): lock Sotto at startup behind a spoken passphrase, with a fallback text password.
- "Forgot passphrase?" on the lock screen: reset or remove a forgotten lock by verifying with the Windows sign-in (Hello / PIN / password). Nothing is deleted.
- First-run onboarding wizard: AI key setup, permissions overview, and a mic check.
- Hands-free options: continuous listening, wake hotkey (Ctrl+Shift+S), an optional wake word, and a small status overlay.
- Quick notes and local image tools.

### Fixed
- The voice lock could appear at startup even when it was never enabled. The lock now only ever shows for a fully configured, user-enabled lock - and the app fails open (never locks) if the lock state cannot be read.

## [Unreleased]

### Fixed
- Voice is now fully hands-free: listening runs in the backend, auto-detects when you stop talking (~1.5s of silence) and sends automatically - from the mic button, Space, the pill, or the Ctrl+Space hotkey. Tap only to finish early; Esc cancels.
- Overlay pill: never appears while the Sotto window is on your screen (it only surfaces live state when the assistant is actually active); when Sotto is minimised or sent to background it shows the quiet presence.
- Commands like "open telegram" no longer die quietly: when a model leaks a tool call as text, it is now parsed (JSON or XML form) and actually executed.
- Replies can no longer leak internal thinking: the recovery path is guarded end-to-end, and an empty draft now gets a clean fallback instead of a confused rewrite.
- Overlay pill presence is now smooth: no flash at launch, it waits for the switch to settle before appearing, and fades in/out cleanly.


### Changed
- Floating overlay rebuilt: a small frameless always-on-top pill now appears over other apps while Sotto is listening, thinking, working or speaking - then fades away when the task is done. It uses the app's own design system, shows live state with real microphone levels, and never steals focus. Tap the orb to talk, the arrow to reopen Sotto; Ctrl+Space summons it from anywhere. (The experimental tkinter pill is gone.)

### Added
- "Send to background" (header button): hides the main window; the floating overlay keeps the assistant reachable.

*See the Roadmap section of the [README](README.md) for what's being worked on.*

## [1.0.0] — 2026-10-01

First public release of Sotto — a voice-first personal operator for Windows.

### Core
- Voice-first interaction: hold-to-talk, offline speech recognition, spoken replies (sentence by sentence), stop / repeat / say-it-slower
- Voice selection, including a custom voice trained from your own samples
- Local-first privacy: secrets encrypted on your PC; bring-your-own-key AI providers

### Work
- Email via your own Google account: summary, search, read, draft, and send with confirmation
- Calendar: today and week view, add events (Google Calendar or `.ics` feeds)
- Files and documents: search by name or content, read PDFs, organize Downloads (with undo), move / copy / rename, safe deletes
- Screen understanding: read the screen or a window, on request
- Apps and system: open/close apps, window control, volume, brightness, media playback, screenshots, clipboard, power actions with confirmation
- Memory, notes, reminders, routines, daily briefing, weather

### Experience
- Calm light interface (dark theme available), presence states, and panels for memory, history, and settings
- Confirmation-first behavior for consequential actions, with a local record of what was done
