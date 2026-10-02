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

### Added
- Floating mini overlay: shrink Sotto to a small always-on-top bar (new Mini button in the header, or say "mini mode"); expand back from the bar or say "full mode". While it's in mini mode, Ctrl+Space brings Sotto back from anywhere.

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
