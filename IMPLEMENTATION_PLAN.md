# RealAssistant — Phase-Wise Implementation Plan (Easy → Advanced)

_Companion to CAPABILITY_RESEARCH.md. Difficulty: 🟢 Easy · 🟡 Medium · 🔴 Advanced._
_"Smooth?" = will it work reliably once built (research classes: A/B = smooth, C = works but needs maintenance, D = human confirms, E = do not build)._

**Direct answers first:**
- **Is it implementable?** Yes — everything in phases 0–3 below is class A/B (smooth, reliable).
  Phase 4–5 mix B/C with clear rules. Nothing required depends on "fantasy" features.
- **Will it make the product high-range?** Yes — the leap from "close/open stuff" to a productive
  tool happens at Phase 1 (email/calendar) + Phase 2 (agent kernel). Those two together change what
  the product *is*.

---

## PHASE 0 — Quick Wins (🟢 Easy · all local, no accounts, no risk)
_Goal: make it feel smarter within days, using what already exists (clipboard, files, screenshots)._

**STATUS (2026-09-30): ✅ BUILT & TESTED — all ten items live (75 tools total).**
New tools: `read_pdf` · `save_text_file` · `read_screen` (Windows OCR) · `read_window_text` (UIA) ·
`run_command` · `type_text` · `press_keys` · `save_routine`/`list_routines`/`run_routine` ·
`index_folder`/`smart_find` (local semantic search, fastembed MiniLM).
Verified live: terminal (echo + inline python = 42), PDF (92-page script read), OCR (read the
on-screen console text), UIA (read a Notepad window), typing (35 chars + Enter into Notepad),
routines (saved + ran), semantic search (68 files indexed; "voice conversion worker" → voice_convert.py, 0.4s).

| # | Feature | Difficulty | Mechanism | Smooth? | Notes |
|---|---|---|---|---|---|
| 0.1 | Clipboard intelligence — "explain this / fix this code / summarize / translate what I copied / turn this into an email" | 🟢 | clipboard read (exists) + LLM | A | hours of work; immediate wow |
| 0.2 | "Read this PDF / summarize this document" | 🟢 | pypdf/pdfplumber text extraction + LLM | A | add per-file type handlers |
| 0.3 | "Find the file where X is mentioned" (deepen existing search) | 🟢 | content search (partly exists) + ranking | A | local, fast |
| 0.4 | Save artifacts: "save this as a note / make me a file with this / export as CSV" | 🟢 | existing file ops + doc generation libs | A | python-docx/openpyxl |
| 0.5 | Screen help v0: "what does this error say?" | 🟡 | screenshot (exists) + OCR (Windows OCR/Tesseract) + LLM | B | high daily value |
| 0.6 | Saved routines v0: "start my work" = chain existing tools (open apps, timer, mute) | 🟢 | tool chaining in one command | A | no new infra |
| 0.7 | Window text reading: "read what's in this window" | 🟡 | Windows UI Automation tree read | B | foundation for Phase 3 |
| 0.8 | Local semantic file search (MiniLM-class embeddings + small vector store) | 🟡 | ONNX embed model, sqlite-vec/FAISS | B | runs on 8 GB CPU; index-your-folders feature |
| 0.9 | **Terminal execution** (`run_command(cmd, cwd)` → exit code + stdout + stderr) | 🟢 | subprocess capture | A | the single biggest enabler (confirmed missing in our audit); permission-gated |
| 0.10 | **Type-text tool** (type into the focused window) | 🟢 | SendInput | B | foundational for form-filling; works where UIA can't |

**After Phase 0:** it reads your clipboard, documents, and screen; saves things; runs routines.
All local, nothing to break.

---

## PHASE 1 — Email & Calendar (🟡 Medium · official APIs · THE productivity leap)
_Goal: the assistant starts handling real work. Personal accounts only — no business setup needed._

**STATUS (2026-09-30): ✅ ENGINE BUILT & TESTED (v49, 88 tools).**
Live now: `email_status/summary/search/read/draft/send/send_draft` (send = confirm-gated),
`calendar_connect_ics/today/week/add`, `connect_google`, `account_status`;
Settings → Accounts UI (Email app-password sheet + Calendar ICS sheet + Google connect).
Verified: DPAPI round-trip, ICS today+week w/ weekly recurrence, graceful failures.
User connects via: Gmail app password (3 min) and/or Google Calendar ICS link (30 s) — see ACCOUNTS_SETUP.md.
Dormant until one-time owner setup: full Google OAuth (gmail API + calendar create/move).

| # | Feature | Difficulty | Mechanism | Smooth? | Notes |
|---|---|---|---|---|---|
| 1.1 | Connect Google/Microsoft account (OAuth desktop flow, loopback) | 🟡 | official OAuth | A | one-time setup screen |
| 1.2 | "What needs my attention in email?" → summarize + rank | 🟡 | Gmail API / Graph mail read | A | read-only first |
| 1.3 | "Draft a reply to X" → writes draft, you approve | 🟡 | drafts API | A→D | sending stays confirm-first |
| 1.4 | "Send it" (per-message confirm) | 🟢 | send API | D | explicit yes/no confirm (pattern exists) |
| 1.5 | "What's on my calendar today/tomorrow?" | 🟡 | Calendar API read | A | replaces guessy answers |
| 1.6 | "Move my 4pm to 5 / create a meeting Thursday 3pm with Rahul" | 🟡 | Calendar CRUD | A→D | invite = confirm once |
| 1.7 | "Find a free hour this week" | 🟡 | freebusy + light reasoning | A | small planner use |
| 1.8 | Morning brief v2: calendar + email + reminders + weather | 🟢 | combines 1.2/1.5 + existing | A | the daily-habit feature |

**After Phase 1:** it manages your inbox and schedule. This is the "not close/open stuff" turning point.

---

## PHASE 2 — The Agent Kernel (🔴 Advanced · the foundation everything later uses)
_Goal: goal-level tasks with planning, progress, verification, permissions — not single commands._

| # | Feature | Difficulty | Mechanism | Smooth? | Notes |
|---|---|---|---|---|---|
| 2.1 | Task model + planner ("prepare me for the interview" → steps) | 🔴 | plan over existing+new tools | B (with honest failure) | the keystone |
| 2.2 | Real progress in the UI (listening→planning→acting→verifying→done) | 🟡 | Sotto states already exist — wire them | B | makes reliability visible |
| 2.3 | Verifier: no "done" without a check (files re-stat, API read-back, exit codes) | 🟡 | per-capability verifiers | B | trust engine |
| 2.4 | Permission registry UI (READ/WRITE/SEND/DELETE/PURCHASE tiers) | 🟡 | settings-backed, enforced in tool layer | A | safety you can see |
| 2.5 | Failure recovery paths (retry → alternate mechanism → ask user) | 🔴 | error taxonomy + policies | B/C | keep asking at edges |
| 2.6 | Multi-step documents: "gather X from these files → make a report" | 🟡 | 0.2 + 0.4 + planner | B | flagship demo |

**After Phase 2:** it reports honestly ("done, verified" vs "done, couldn't confirm"), recovers,
and asks only at real decisions. This is what separates it from every launcher.

---

## PHASE 3 — Messaging Adapters (🟡 each · official channels only)
_Goal: messaging where platforms officially allow it. Honest limits everywhere else._

| # | Feature | Difficulty | Mechanism | Smooth? | Notes |
|---|---|---|---|---|---|
| 3.1 | Slack bot (read/summarize/send in your workspace) | 🟡 | Web API + scopes | A/B | needs workspace install |
| 3.2 | Teams via Microsoft Graph | 🟡 | Graph | A | org may need admin consent |
| 3.3 | Telegram bot (chats it's in) | 🟡 | Bot API | B | NOT your personal DMs |
| 3.4 | WhatsApp | — | business API only | D/E | recommend: skip for personal |
| 3.5 | Telegram/Discord desktop UI automation | 🔴 | UIA | C | optional, fragile, off by default |

**Rule:** official path or nothing. No self-bot automation (bans + ToS).

---

## PHASE 4 — Browser & Screen Actions (🔴 Advanced · controlled autonomy)
| # | Feature | Difficulty | Mechanism | Smooth? | Notes |
|---|---|---|---|---|---|
| 4.1 | Playwright on chosen sites ("check my university portal") | 🔴 | Playwright + saved logins | B/C | per-site adapters; stop before submit |
| 4.2 | Form filling from documents ("fill this using my info, don't submit") | 🔴 | DOM + data from files | B/D | user confirms submit |
| 4.3 | "Click Continue" on any app | 🔴 | UIA-first, vision fallback | B/C | never for UAC/payments |
| 4.4 | Vision computer-use last resort | 🔴 | screenshot-VLM loop | C/D | cost-capped, opt-in, never money/auth |

---

## PHASE 5 — Developer Workflows (🟡 Medium)
| # | Feature | Difficulty | Mechanism | Smooth? |
|---|---|---|---|---|
| 5.1 | "Run the tests" / "why are they failing" / fix loop | 🟡 | terminal + files + LLM | B |
| 5.2 | Git: commit, branch, PR via GitHub API | 🟡 | git CLI + REST | A |
| 5.3 | Project memory ("the decision we made about X") | 🟡 | memory scopes + semantic search | B |
| 5.4 | VS Code integration (open file/line, run task) | 🟡 | CLI + extension | B |

---

## PHASE 6 — Proactive Engine (🟡/🔴)
| # | Feature | Difficulty | Notes |
|---|---|---|---|
| 6.1 | Event bus + policy layer (quiet hours, opt-in per type, max/day) | 🔴 | decision engine, must stay boring |
| 6.2 | Watchers: battery, downloads folder, calendar-15min, build-finished | 🟡 | local, cheap |
| 6.3 | Proactive saves ("meeting in 15 — docs ready?") | 🟡 | reuses Phase 1 tasks |

---

## PHASE 7 — Polish & Distribution (🟡)
| # | Feature | Difficulty | Notes |
|---|---|---|---|
| 7.1 | Installer (Inno Setup) + first-run minimal asks | 🟡 | plan exists (V1_PRODUCT_PLAN.md) |
| 7.2 | Optional voice engine as download; auto-update | 🟡 | keeps base install ~150 MB |
| 7.3 | Reliability scoreboard per capability (honest classes surfaced in UI) | 🟡 | trust feature |

---

## Cross-check merge (2026-09-30, second-opinion audit from Antigravity)

A second AI audited our app + researched the same space. Verified against our codebase [first-party check]:

**Accurate → merged or already here:** terminal execution missing (added as 0.9 — biggest single gap);
no type-text tool (added as 0.10); `search_web` opens the browser without reading results (already in
Phase 1's web-reading work; note `look_up`/`read_webpage` DO read); screenshots never analyzed (0.5);
Spotify only opens search (Phase 5 media; **VLC HTTP API added as a 🟢 local media win**); daily
briefing shallow without email/calendar (Phase 1.8); proactive watches only disk+battery (Phase 6).

**One error to correct:** "reminders lost on restart" — FALSE for current code; reminders persist
to JSON already (verified in `reminders.py` `_load`/`_save`).

**Platform table:** matches ours (Gmail/Calendar full ✓, WhatsApp skip ✓, Discord bots ok /
selfbots never ✓, Spotify premium for playback ✓, Playwright medium/fragile ✓, pywinauto ≈ our UIA
rung ✓). Two nuance calls we keep: **Telegram personal-account automation (Telethon/MTProto) = works
technically but gray-area, ban risk → opt-in off-by-default, bot path preferred**; and **Playwright
stays in Phase 4** (their ordering pulls it earlier — we sequence by reliability tier, not excitement).

**Structured tool results** ({success, data, error} instead of plain strings) — good idea, already the
spirit of our Phase 2 Verifier; adopt incrementally as tools get touched.

## Sequencing logic (why this order)
1. Phases 0–1 give value immediately with A-class reliability and no accounts complexity beyond OAuth.
2. Phase 2 must exist before Phase 3+ because messaging/browser tasks NEED plan+verify+permissions.
3. Phase 4 (autonomy) deliberately last — it's the fragile tier; the product shouldn't depend on it.
4. Every phase is additive: nothing here requires rewriting the existing app; the tool gateway,
   UI states, memory, and voice all stay.

## "Unbeatable" = the combination (not any single feature)
Local-first privacy (voice, files, memory, custom voice) + official-API integrations (email/calendar)
+ goal-level planning with **honest verification** + a voice UI that shows real state. No mainstream
assistant combines all four, especially not on an 8 GB laptop.
