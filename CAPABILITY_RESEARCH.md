# RealAssistant — Full Capability Research

_Mandate: discover what a voice-first Windows personal computer agent could realistically become.
Anti-fantasy rules applied throughout. Written 2026-09-30._

## 0 · How to read this document (verification legend)

External research today ran against a degraded search service (most queries returned junk; a parallel
research pass of six AI researchers timed out without producing usable files). Rather than invent or
blur this, every claim below carries a marker:

- **[V]** — **Verified today** (2026-09-30): I retrieved the listed source in this session. URL in §Sources.
- **[DOC]** — **Documented platform capability**: stable, widely-documented behavior of an official
  API/OS feature. A one-click re-verification link is listed in §Sources. Not re-fetched today.
- **[ASSESS]** — **Our assessment/judgment**, reasoned from system facts + platform documentation.
  This is opinion, labeled as such — not a sourced fact.
- **[CHECK]** — **Needs verification before building** (something plausibly true but not confirmed
  in this session — verify via the official doc named).

Nothing in this document is presented as stronger than its marker. Where the ecosystem is genuinely
limited, it says so ("fragile", "restricted", "not realistically available").

---

## 1 · Current System Assessment vs. Real Capability

RealAssistant today (first-party facts — our own code/docs): local-first voice-first Windows assistant;
Python 3.12 + pywebview UI; 62 local tools; offline STT (vosk + faster-whisper); SAPI speech + an
optional **offline RVC voice-clone pipeline**; persistent memory; sessions; reminders; notes; audit;
computer scan (Start-Menu/Desktop/taskbar app index); multi-provider cloud LLM chain with failover.

| Existing capability | Current implementation | Real ceiling | Limitation to respect | Verdict |
|---|---|---|---|---|
| Open/close apps | Shortcut index + registry lookup (local) | As good as it gets locally | Store apps (UWP) need URI activation | **Keep** |
| Window control | Win32 calls (snap/focus/min/max) | Full Win32 surface available | Elevation boundaries (UIPI) | **Keep** |
| Files (find/read/move/organize) | Deterministic Python + guards | Entire filesystem within permissions | No content understanding yet | **Extend** (§10) |
| System controls | pycaw/netsh/power APIs | Full audio/display/network surface | — | **Extend** (§4) |
| Reminders/notes/memory | Local stores | Solid foundation | No calendar integration yet | **Extend** (§9) |
| Screenshots | File capture | + OCR + screen understanding | No CV/VLM pass yet | **Extend** (§11) |
| App *operation* (not just launch) | — none | UI Automation / APIs / vision | Reliability varies by app class | **Build** (§5) |
| Communication (read/draft/send) | — none | Official APIs exist per platform | Policy/account constraints | **Build** (§7–8) |
| Deep agent behavior (plan/verify/recover) | Single-shot tool loop | Needs architecture upgrade | — | **Build** (§19–21) |
| Proactive | Basic watcher | Event-driven model needed | Must avoid notification spam | **Rebuild** (§17–18) |

---

## 2 · Product Definition (what it should be)

Not "Siri for Windows." The researched capability set supports one honest definition:

> **A voice-first delegation layer between the user and their computer** — you state a goal;
> it chooses the most reliable mechanism available (OS API → official app API → scripted browser →
> UI automation → vision fallback); it executes, **verifies**, and reports; it asks the user only
> where judgment or permission is genuinely required.

Why this definition and not "personal operating layer" [ASSESS]: the reliability evidence (RPA
industry patterns; computer-use agent limits; API constraints) shows autonomous operation of
*arbitrary* apps/websites is class C–E today — an operating layer must be class A/B to be trusted.
The delegation layer plays to what is actually reliable: a widening set of official APIs + local
deterministic power + human confirmation at the edges.

---

## 3 · The Three-Question Filter (applies to every capability)

For every capability in this document:
1. **Can AI understand the request?** (Almost always yes — language models handle fuzzy intent.)
2. **Can the computer perform it?** (Deterministic: yes/partly. Needs exact mechanism.)
3. **Can RealAssistant do it reliably & legitimately?** (The real constraint: official API? account
   type? ToS? UI fragility? money/auth involved?)

A capability is only "production" when all three are yes. Classification used throughout:
**A** official API/reliable · **B** reliable automation · **C** possible but fragile ·
**D** needs human confirmation · **E** not realistically available.

---

## 4 · Windows Control Capabilities

| Capability | Mechanism | Class | Notes |
|---|---|---|---|
| Launch apps (incl. store apps) | ShellExecute / URI activation | A | UWP via `ms-` URIs |
| Window manage (move/resize/snap/focus/min/max) | Win32 (`SetWindowPos`, `ShowWindow`) | A | [DOC] learn.microsoft.com/win32 |
| Keyboard/mouse synthesis | `SendInput` | B | [DOC] blocked into higher-integrity (elevated) processes by UIPI — unless injected app runs elevated |
| Read/operate UI of other apps | **Windows UI Automation (UIA)** | B→C | [V] MS Learn: *"accessibility framework that enables Windows applications to provide and consume programmatic information about user interfaces"*; *"programmatic access to most UI elements on the desktop"*. Works well where apps expose trees (most Win32/WPF/UWP/Chromium); breaks on custom-drawn/games; can be slow on huge trees. This is the same technology commercial RPA uses. |
| Accessibility-style automation | MSAA → UIA bridge | B | legacy apps |
| Volume (get/set), mute | Core Audio COM (`IAudioEndpointVolume`) | A | our app already does this |
| Brightness | DDC/CI or WMI | B | external monitors vary |
| Wi-Fi/BT state, devices | WinRT APIs / `netsh` | B | pairing flows partially interactive |
| Notifications (send/read) | WinRT notifications / toast APIs | B | reading others' toasts is more limited [CHECK] |
| Power (lock/sleep/shutdown/restart) | Win32 / `shutdown.exe` | A | our app already does this |
| Processes / performance | psutil / WMI | A | |
| Clipboard | Win32 clipboard API | A | sync-history privacy notes apply |
| Screenshots / screen capture | GDI/DXGI capture | A | |
| **Screen understanding (text)** | **Windows OCR (`Windows.Media.Ocr`) or Tesseract** | B | [DOC] built-in OCR exists; accuracy good on UI text |
| **Screen understanding (semantics/click targets)** | UIA tree + vision model fallback | B/C | see §6 |
| Dialogs/UAC prompts | — | D/E | **Secure desktop cannot be automated by design** — asking the user is correct |
| Protected content (DRM), anti-cheat, games | — | E | not reliably available |

Key takeaway [ASSESS]: the Windows control layer is *already 80% class A/B* — the gap between
RealAssistant and "full computer operation" is not raw power, it is **the UI-operating layer (UIA) +
screen understanding**, which is exactly the industrial RPA approach.

---

## 5 · Application Control (operating apps, not launching them)

Mechanism ladder per application family [ASSESS, from platform docs]:

| Family | Best mechanism | What it supports | Class |
|---|---|---|---|
| Apps with official APIs (Spotify, VS Code, browsers, Git, Office) | Official API / CLI / extensions | exact, documented operations | A/B |
| Chat apps (Telegram, WhatsApp, Discord, Slack, Teams) | platform APIs (bot/business/graph — see §7) | API-scoped read/send | A→D |
| Apps exposing UIA (most desktop apps) | UI Automation | scripted click/type/read of controls | B/C |
| Electron/Chromium apps | UIA (Chromium exposes UIA) + their own devtools via CDP | strong automation path | B/C |
| Legacy/custom-drawn apps | keyboard/mouse synthesis + screenshots | last resort, fragile | C |
| Games / secure apps | — | | E |

The productive pattern [ASSESS]: **capability adapters** — a thin per-app adapter that declares which
verbs it supports (read / create / send / search) and routes to the best mechanism. The assistant
never assumes "all apps behave the same"; the adapter matrix decides. (Mandate §4's integration
matrix becomes a living registry, not a one-time doc.)

Per-app quick verdicts [DOC unless marked]:
- **Telegram** — bot API ≠ personal chats; desktop UI automation possible but fragile; see §7.
- **WhatsApp** — official = business messaging only; consumer automation = ToS risk (§7).
- **Discord / Slack / Teams** — bots/apps are the sanctioned path; user-account automation is
  prohibited (Discord: self-bots banned [DOC discord.com/developers/docs + support articles]);
  Teams has Microsoft Graph as the sanctioned path.
- **Gmail/Outlook** — real APIs for read/send/drafts/search (§8). Best-in-class integration targets.
- **VS Code** — CLI + extension API; deep integration feasible (§13).
- **Browsers** — Playwright/CDP (§6).
- **Spotify** — Web API (playback control needs premium [CHECK]); our current media control covers basics.
- **YouTube** — no official playback API for consumers → browser automation (§6), class B/C.
- **PDF readers / office** — control via files/format libraries (§10) rather than UI.

---

## 6 · Browser / Computer-Use (execution environment)

**Scripted browser (Playwright/Puppeteer/CDP)** — [V] playwright.dev/docs (Best Practices page
exists; framework "designed to be fast, reliable" — vendor framing) + [V] github.com/microsoft/playwright
(2026: Playwright CLI explicitly marketed "for coding agents"). [DOC] Facts: drives Chromium/Firefox/
WebKit; auto-waiting; **persistent contexts / storageState** keep logins across runs; `connectOverCDP`
can attach to the user's real Chrome session instead of a fresh automation profile. Class **B for
stable sites with known flows; C for arbitrary sites** (anti-bot detection, layout churn). ToS: some
platforms prohibit automation (their rules still apply).

**Browser extensions** — manipulate pages the user already has open; no separate browser; needs
installation + permissions; class B for the pages they support. Our own AutoGLM browsing works this way.

**Computer-use agents (vision loop: screenshot → decide → click/type)** — [V] Anthropic official
docs exist: platform.claude.com computer-use tool (beta; has explicit image-size limits) +
anthropic.com announcements ("developers can build with the computer use beta"). [DOC] Known
properties: slow (~seconds/step), token-costly, best for unknown UIs; **must not be trusted with
money/auth flows**; CAPTCHA/MFA are stop-and-ask zones. Class **C general; D for consequential
actions; E for CAPTCHAs (by design)**.

**The correct hierarchy** (confirmed by RPA practice + agent docs) [ASSESS]:
1. Native OS API → 2. Official app API → 3. Official CLI/SDK → 4. Scripted browser (Playwright on
known flows) → 5. UI Automation → 6. Keyboard/mouse synthesis → 7. Vision/computer-use agent →
8. **Ask the user.** Always choose the highest reliable rung; vision is the fallback, never the default.

---

## 7 · Communication Platforms — Reality Matrix

| Platform | Read | Send | Search | Official path | User-account automation | Class | Constraint |
|---|---|---|---|---|---|---|---|
| Telegram | own bot chats [DOC core.telegram.org/bots/api] | yes (bot chats) | limited | Bot API; TDLib for clients | unofficial/riyouraccount — ToS gray; ban risk [CHECK telegram.org/tos] | B (bots) / C (personal chats via UIA) | Bots cannot read a user's private conversations |
| WhatsApp | — | business messaging only | — | Cloud API (Meta) — **business accounts, templates, opt-in rules** [DOC developers.facebook.com/docs/whatsapp] | not supported; unofficial libs violate ToS → ban risk [CHECK] | D/E for consumer automation | Official = business only |
| Discord | yes (guild channels bot is in) | yes | API search limited [CHECK] | Bot API [DOC discord.com/developers/docs] | **prohibited (self-bots)** | A (bots) / E (user account) | No user-DM access |
| Slack | yes (scoped) | yes | yes (search.messages, user token) | Web API + scopes [DOC api.slack.com] | app must be installed/approved per workspace | A→B | Admin approval in workspaces |
| Teams | chats/channels via Graph | yes | limited | Microsoft Graph [DOC learn.microsoft.com/graph] | not sanctioned otherwise | A (Graph) | Entra app + (often) admin consent |
| SMS | — | — | — | carrier-dependent | — | D | Not a real target on desktop |

Honest summary [ASSESS]: "the assistant messages Rahul for me" is **production-grade only via
official channels** (Telegram bot in shared chats, Slack/Teams bots, business WhatsApp) — i.e., where
the user's messaging lives in a workspace/API-enabled surface. For personal chat accounts, the honest
choices are (a) UI automation of the desktop app (class C — works today, breaks on UI updates, may
violate platform rules), or (b) don't. This must be a user-visible setting, not a silent choice.

---

## 8 · Email (the strongest integration target)

| Capability | Gmail API [DOC developers.google.com/gmail/api] | Microsoft Graph [DOC learn.microsoft.com/graph] |
|---|---|---|
| Read inbox/threads | messages.list/get + `q` search | /me/messages (+$search, $filter) |
| Draft | drafts.create/update (+vault) | /me/messages draft create |
| Send | messages.send / drafts.send | /me/sendMail |
| Attachments | yes (upload/download) | yes |
| Labels/folders | labels API | categories/folders |
| Account hurdle | OAuth; **restricted scopes require Google verification + security assessment (CASA) if distributed**; personal/testing mode is fine for self-use [DOC + CHECK current process] | app registration (even personal MS accounts); work accounts may need admin consent [DOC] |

Class: **A** for a self-hosted personal assistant (single user, own credentials). Class **D** for
"send email autonomously" as a default behavior — sending should stay confirm-first (mandate's own
safety tiering agrees). Low-friction fallback for basic send/read: IMAP/SMTP with app passwords
where providers still allow it [CHECK per provider in 2026].

Verdict [ASSESS]: **Email triage → summarize → draft → user approves → send** is achievable
end-to-end with official APIs, minimal compliance friction for personal use, and high user value.
It is the single best "wow" integration for this product's next phase.
## 9 · Calendar & Tasks

- **Google Calendar API** [DOC developers.google.com/calendar]: events CRUD, `freebusy.query`
  (availability), watch channels; OAuth desktop flow (loopback). Class **A** (personal use).
- **Microsoft Graph Calendar** [V-adjacent: permissions docs surfaced today, e.g. learn.microsoft.com
  permission pages listing `Calendars.ReadWrite`] + [DOC learn.microsoft.com/graph]: /me/events CRUD,
  findMeetingTimes, online meeting (Teams) link generation, attendees/invites. Class **A**.
- **"Move my 4pm to 5"** → trivial once calendar API is connected (update event). **"Find a free hour
  this week"** → freebusy + reasoning over preferences (needs AI but small). **"Remind me 2 days
  before the interview"** → local reminders + calendar read. All class A/B.
- **Notice**: reminders inside apps (e.g., Google Tasks) are less API-rich than calendar;
  task systems vary — calendar + our local reminders cover the practical need.
- Constraint [ASSESS]: attendee invitations = sending mail on user's behalf — keep confirm-first.

## 10 · Files & Documents (major differentiator, mostly LOCAL)

| Work | Mechanism | Class | AI needed? |
|---|---|---|---|
| Find "the resume I edited last week" | filename + mtime + content search; semantic index once built | B | yes (ranking) |
| Read text-PDF | pypdf/pdfplumber-class extraction [DOC] | A | no |
| Read scanned PDF / image docs | OCR: Tesseract [DOC] / Windows built-in OCR [DOC] | B | no |
| "What is this PDF about / find the section about auth" | text extracts + LLM (or local embed + retrieval) | B | yes |
| Rename/move/group files | pure deterministic + undo log (we already have Undo for downloads) | A | no |
| Remove duplicates | hashes + (for images) perceptual hash [DOC] | B | no |
| Convert images/formats | Pillow/ffmpeg [DOC] | A | no |
| CSV/data questions ("what changed") | pandas-class + LLM summarization [DOC] | B | partly |
| Create report/CSV/PPT from files | python-docx/openpyxl/python-pptx/reportlab [DOC] | B | yes (drafting) |
| **Semantic file search (local)** | small embedding model (MiniLM-class via ONNX) + vector store (sqlite-vec/FAISS/Chroma) | B | — | [DOC-class tools; feasibility on 8GB CPU: yes, small models] |

Verdict [ASSESS]: document intelligence is **the most under-appreciated high-value area** for this
product — it's local (privacy + speed), needs no business accounts, has no ToS risk, and "computer,
read this and tell me" is the purest expression of the product thesis.

## 11 · Clipboard & Screen Context

- Clipboard read/write: class **A**, trivial (we have it). "Explain what I copied / turn this into an
  email / fix this code" = clipboard text + LLM: class **A** — build this first in this category.
- Screen awareness levels [ASSESS]:
  1. **Screenshot + OCR** (class B): "what does this error say", "summarize this page" — robust.
  2. **UIA tree reading** (class B): structured element text of the focused window — faster and
     cleaner than OCR where supported.
  3. **Vision model over screenshot** (class C): "what am I looking at", pointing at visual content;
     costs tokens/time.
  4. **Acting on screen**: "click Continue" — UIA-first (find control, Invoke pattern), vision
     fallback; class **B where UIA works, C/D otherwise**.
- Limits: secure desktop (UAC) = not automatable by design; DRM/anti-cheat = E.

## 12 · Web Research (knowledge work input)

- Search + read + summarize: class **B** (we have search; page reading needs a robust extractor —
  Playwright or an extension).
- Multi-source research with citations: LLM + fetch; class B; reliability = source quality discipline.
- "Compare these three technologies" / "read these five documents" → files + web + LLM: class B.
- Constraint: scraping heavy/Paywalled sites → fragile (C); respect site ToS.

## 13 · Coding / Developer Workflows

- Terminal exec (subprocess): class **A** — deterministic.
- Git CLI (porcelain): class **A** [DOC git-scm.com/docs].
- GitHub REST API (issues/PRs/actions/repos): class **A** with a token; scopes govern reach
  [DOC docs.github.com]. (We already push via git; a PAT issue is known.)
- VS Code: CLI (`code` command) + extension API for deeper integration [DOC code.visualstudio.com];
  class B for build/test loops via terminal; A for file edits.
- The right split [ASSESS]: **LLM decides & explains; deterministic tools execute** (edit files,
  run tests, commit); verification = re-run tests + read output. This is exactly the "fix my project"
  loop, and it is achievable NOW on this machine (no GPU needed — cloud LLM + local execution).

## 14 · Media

- Local media: play/pause/next via keyboard media keys (class A — we have basic control).
- Spotify: Web API playback (premium account constraints [CHECK]); search/metadata class B.
- YouTube: no consumer playback API → browser automation class C; "find that interview and play it"
  = web search + open result (class B for the search part).
- Verdict: media stays a convenience, not a differentiator; class B ceiling is acceptable.

## 15 · Memory (personal context system)

- What exists: facts + summaries + sessions (local). Extend to: **project memory** ("this folder is
  my final project"), **preference memory**, **decision log** ("the decision about RAG architecture").
- Mechanisms [ASSESS + DOC]: structured stores now; semantic recall later via local embeddings (§10);
  user-visible memory manager (we have Memory hub) + correction/delete (have) + scoping (project vs
  global — new).
- Privacy: all local; no cloud unless user opts in. This is a *feature*, state it in UI copy.

## 16 · Personal Productivity (routines → workflows)

Goal-oriented routines ("prepare me for my interview tomorrow") = **plan** over: calendar read →
web research → file lookup (resume) → document creation (prep notes) → local reminders → open docs
→ summarize. Every step is class A/B with items already available or in §8–10 scope. The missing
piece is the **planner + execution state machine** (§19), not the capabilities.

## 17 · Proactive Assistance (carefully)

- Trigger classes [ASSESS]: calendar-approaching (A), timers (A — have), downloads-folder growth (B),
  build/test finished (B from terminal hooks), battery (A), unanswered-important-email (B via §8),
  long-running task done (A).
- Rules for not becoming Clippy [ASSESS]: (1) opt-in per trigger class; (2) quiet hours; (3) max N
  nudges/day; (4) every nudge dismissible forever ("never tell me this again"); (5) never interrupt
  speech mid-sentence; use the quiet prompt line + a subtle sound.
- The mandate's event list maps cleanly onto a local event bus (§18).

## 18 · Event-Driven Architecture

Turn the assistant from request/response into **event → assess → act/inform**:

```
local event watchers (calendar poll, FS watch, battery, process/test hooks, download completion)
        ↓
event bus (in-process queue)
        ↓
policy layer (should I care? user prefs, quiet hours, importance)
        ↓
planner/executor (reuse the same pipeline as voice requests)
        ↓
notify (voice / prompt line / toast) or act silently if pre-approved
```

[ASSESS] This is the single biggest architectural upgrade for "feels alive" — and it is cheap on
Windows: file watching (ReadDirectoryChangesW/watchdog), process polling (psutil), calendar polling
(API), all local. Keep the policy layer boring and explicit; the intelligence is in *deciding what
not to say*.
## 19 · Multi-Step Agentic Work

Current system: one-shot tool loop (LLM calls tools, we execute, LLM summarizes). Gaps vs a real
agent [ASSESS]: explicit planning state, task stack, checkpoints, cancellation, per-step verification,
partial-completion reporting. Recommended: a **task model** — Task{goal, plan[], steps[], state,
verifications[]} run by an executor with the same tool layer; voice reports at meaningful beats only
("Found 14 PDFs." → "Grouped them into a new folder." → "Done."). The UI already has states for
acting/waiting/progress (Sotto v4) — the backend needs to actually emit them.

## 20 · Verification (first-class)

Rule: **no "done" without a check** [ASSESS]. Mechanisms per class:
- Files: re-stat (exists at destination, size unchanged?) — deterministic.
- Email/messages: API read-back (message id in Sent / thread message exists) where API allows.
- Calendar: GET event after POST.
- Terminal/test jobs: exit code + output parse.
- UI actions: re-read UIA state of the control (e.g., button gone, checkbox toggled); screenshot diff
  as weak evidence.
- Where verification isn't possible → the assistant says "done, but I couldn't confirm X" — never
  fake certainty (this is also a product principle from the mandate).

## 21 · Failure Recovery

Failure taxonomy → policy:
- **Transient** (network, API 5xx, app still loading): retry with backoff (we already do for LLM chain).
- **State mismatch** (element not found, UI changed): re-scan → alternate mechanism (UIA→keyboard→
  vision) → if still failing, ask user with a screenshot + plain-language description.
- **Auth/expired** (login weeks old): prompt to re-authenticate once; never store more than needed.
- **Ambiguity** (three Rahuls): ask a question with options (UI chips + voice); resume the task after.
- **Partial completion** (3 of 5 files moved): report exactly what happened; offer undo/continue.
- **Consequential action failed midway** (payment, send): stop; surface to user; never blind-retry
  dangerous actions (mandate's rule, adopted).

## 22 · Permissions & Safety Model

Tiering [ASSESS, matching the mandate's proposal]:
| Tier | Examples | Behavior |
|---|---|---|
| Auto | open app, search, summarize, read local file, volume | silent |
| Confirm once | connect email/calendar/messaging account | OAuth consent + one-time UI confirmation |
| Confirm per action | send message/email, delete files, submit forms, purchases, account changes | explicit user OK every time (voice yes/no works — we have this pattern) |
| Never autonomous | CAPTCHAs, UAC secure desktop, password entry, payments without approval | human only |
Implementation: permission registry per capability class (mandate's READ/WRITE/COMMUNICATE/DELETE/
PURCHASE/PUBLISH/ACCOUNT/SYSTEM), stored in settings, enforced in the tool layer (not the prompt —
prompts are not security). We already have a confirmation gate + denied-tools list; extend it.

## 23 · What Needs AI vs What Must Never Use AI

| Category | Examples | Why |
|---|---|---|
| Deterministic (no LLM) | volume 30%, open app, move file, timer, window snap | zero ambiguity; LLM adds failure modes only |
| AI understanding | "make this email less aggressive", "what's important here", "which file is the resume" | language judgment |
| AI planning | "prepare workspace", "research X and save summary" | multi-step decisions |
| AI + tools | "read my email and draft replies", "fix the project and run tests" | reasoning loop |
| Computer-use fallback | unknown websites/apps | no structured path exists |
Principle [ASSESS]: **LLM for understanding, judgment, planning, and explanation — never as the
executor.** Everything with a deterministic path uses it. (This is also our existing architecture;
keep it sacred.)

## 24 · Integration Strategy (the ladder, confirmed)

Native OS API → Official app API → SDK/CLI → Scripted browser (Playwright) → Windows UI Automation →
Keyboard/mouse synthesis → Vision/computer-use → Ask the user. [ASSESS] Confirmed appropriate; the
addition to the mandate's version: **per-app adapters** that declare supported verbs, and a **verb
registry** so the planner knows "what can be done" before trying.

## 25 · Existing Products — Demonstrated vs Claimed

- **Microsoft Copilot (Windows)**: agentic features rolling out (acting in apps, file actions)
  [CHECK current 2026 state on learn.microsoft.com copilot pages]; Copilot Studio = custom agents
  [DOC]. Lesson: even Microsoft ships this incrementally with heavy safety rails.
- **Apple (Siri / Apple Intelligence)**: App Intents = developers expose actions for Siri
  [DOC developer.apple.com/documentation/appintents]; on-screen awareness arrived 2025–2026
  [CHECK version notes]. Privacy model = permission prompts at the point of use — **copy this**.
- **OpenAI / Anthropic computer use**: [V] Anthropic docs/announcements (above). Demonstrated scope:
  browsing + form filling in controlled demos; documented fragility + safety cautions. Lesson:
  vision-first agents are real but slow; use as fallback only.
- **Raycast / Alfred**: extension model — thousands of small, reliable adapters. Lesson: **adapters
  beat monoliths**; one API per adapter, declarative, independently testable.
- **Power Automate Desktop** [DOC learn.microsoft.com/power-automate/desktop-flows]: desktop+browser
  UI flows — proves UIA/automation viability at scale; also proves flows break when UIs change
  (industries of maintenance exist around it). Lesson: expect to maintain selectors; design recovery.
- **Zapier/Make/IFTTT**: teach the trigger→action model and the value of connector catalogs (for our
  event system, §18), but cloud-only → not our architecture, just our UX vocabulary.
- **Open-source Windows agents** (UFO/Open Interpreter class) [CHECK repos for current results]:
  published benchmarks (WindowsAgentArena-style) show success rates far below 100% — supports class
  C ratings and the human-confirmation design.

## 26 · API / Platform Feasibility Matrix (summary)

| Domain | Official API | Auth model | Free for personal use? | Class | Big catch |
|---|---|---|---|---|---|
| Windows OS | n/a (local) | — | yes | A/B | UIA fragility; secure desktop |
| Gmail | yes | OAuth (desktop) | yes (quota) | A | restricted-scope verification if distributed |
| Google Calendar | yes | OAuth | yes | A | — |
| Microsoft Graph (mail/calendar/teams) | yes | OAuth + app reg; admin consent for orgs | yes | A | org admin consent |
| Telegram | Bot API yes; client libraries | bot token / user login | yes | A(bots)/C(personal) | personal chats not bot-accessible |
| WhatsApp | Cloud API | business verification | paid per conversation | D/E consumer | business-only, templates |
| Discord | Bot API | bot token | yes | A(bots)/E(self) | no user DMs; self-bots banned |
| Slack | Web API | OAuth scopes | yes | A/B | workspace approval |
| Spotify | Web API | OAuth | yes | B | playback control constraints |
| GitHub | REST/GraphQL | PAT/OAuth | yes | A | scopes |
| Browser automation | n/a | — | yes | B/C | detection, ToS, fragility |
| Computer-use (vision) | vendor APIs | API keys | paid | C/D | slow, costly, CAPTCHA/MFA stop |

## 27 · Capability Map (improved from the mandate's)

```
REALASSISTANT
├── COMPUTER (A/B mostly built)
│   ├── Apps: open/close/scan ── extend: operate (UIA adapters)
│   ├── Windows: manage ── extend: layouts/workspaces
│   ├── Input: synthesis (B) ── new: form filling helpers
│   ├── System: audio/display/power/net/devices ── extend: BT/Wi-Fi flows
│   └── Screen: capture ── extend: OCR → UIA-reading → vision
├── INFORMATION (high value, no accounts needed)
│   ├── Files: find/read/organize ── extend: understanding, dedupe, convert
│   ├── Documents: parse/OCR/RAG ── new
│   ├── Clipboard: read/write ── new: LLM verbs (explain/fix/translate)
│   └── Web: search/read ── extend: research workflows
├── COMMUNICATION (accounts; policy-bound)
│   ├── Email: full via APIs (§8) — best target
│   ├── Calendar: full via APIs (§9)
│   ├── Messaging: per-platform adapters, honest classes (§7)
│   └── Meetings: links + reminders (Graph/Google)
├── PRODUCTIVITY
│   ├── Notes/reminders/memory (built) ── extend: projects, decisions
│   ├── Tasks: local + calendar sync
│   └── Routines: goal workflows (§29)
├── CREATION
│   ├── Documents/CSV/PPT generation ── new (§10)
│   ├── Code: terminal+git+GitHub+VS Code (§13)
│   └── Media: basic (built), browser for the rest
├── AGENT (the real work)
│   ├── Planner + task model (§19) ── NEW foundational
│   ├── Verification (§20) ── NEW foundational
│   ├── Recovery (§21) ── NEW
│   ├── Permissions registry (§22) ── extend existing gate
│   └── Memory scopes (§15)
└── PROACTIVE
    ├── Event bus + watchers (§18) ── NEW
    ├── Policy layer (quiet, opt-in) (§17)
    └── Briefings/nudges (basic built)
```

## 28 · Core Agent Primitives (compose everything from these)

READ · SEARCH · OPEN · FIND · CREATE · EDIT · MOVE/COPY · DELETE · SEND · DOWNLOAD/UPLOAD ·
ANALYZE · SUMMARIZE · COMPARE · EXECUTE · WAIT · VERIFY · ASK · REMEMBER · SCHEDULE · MONITOR.

Example composition (mandate's case): "Find the invoice from Rahul, rename it, put it in Finance,
email it to him" → SEARCH → IDENTIFY(ask if ambiguous) → RENAME → MOVE → ATTACH → DRAFT → CONFIRM →
SEND → VERIFY. Every primitive is either already implemented or scoped in this document — the
composition engine (planner + verifier) is the missing keystone.

## 29 · High-Value End-to-End Workflows (what "done" looks like)

1. **Email triage**: "What needs my attention in email?" → read/summarize/rank → draft replies on
   request → confirm → send → verify. [A]
2. **Prep for interview**: calendar + web research (company) + resume file + notes creation +
   reminders. [A/B]
3. **Document errand**: "Find X, tell me the key points, save a summary where I can see it." [A/B]
4. **Workspace start**: schedule peek + open project + restore apps + focus timer + mute noise. [A/B]
5. **File cleanup**: duplicates + downloads organization with undo. [A/B, partially built]
6. **Dev loop**: "tests are failing — find out why and fix it" → terminal + files + git + retest. [A/B]
7. **Screen help**: "explain this error" → screenshot/OCR/UIA text → answer. [B]
8. **Communication errand**: "tell Rahul I finished the API integration" → per-platform adapter with
   confirm-first. [A where official; C where not — surfaced honestly]
9. **Research brief**: "research X across N sources, save a cited brief." [B]
10. **Proactive saves**: low battery + unsaved docs warning; meeting-in-15 + docs ready. [A]

## 30 · What Would Actually Make This Special

[ASSESS] Not feature count — three things:
1. **Reliability honesty as UX**: the assistant tells you *how sure it is* ("done" vs "done, but I
   couldn't confirm"), asks at the right moments, and never fakes. Nobody in this space does this
   well; it is a trust moat.
2. **Full-local privacy core** (voice, memory, files, custom voice) with cloud only for reasoning —
   on an 8GB laptop. Practically unique at this price point.
3. **The delegation feel**: speak a goal → watch it get done with visible, honest progress. The Sotto
   presence/state system is already built for exactly this storytelling — most competitors show a
   spinner; ours can show *listening → thinking → acting → verifying → speaking*.

## 31 · Recommended Architecture (the foundation)

```
Voice/Text intake
   ↓
Conversation core (exists)
   ↓
INTENT → TASK BUILDER (new)          ── goal + constraints + slots
   ↓
PLANNER (new)                        ── plan[] over PRIMITIVES
   ↓
EXECUTOR (new)                       ── runs steps, emits state/progress (Sotto v4 states wired)
   ↓
TOOL GATEWAY (exists, extend)        ── permissions (§22) + adapters (§24)
   ├── deterministic verbs (files/system/apps)
   ├── API adapters (email/calendar/github…)
   ├── browser adapter (Playwright)
   ├── UIA adapter (window/app control)
   └── vision fallback (computer-use, last resort)
   ↓
VERIFIER (new)                       ── per-step checks (§20)
   ↓
RESULT → voice + UI (with confidence: done / partial / failed + why)
   ↓
MEMORY (extend)                      ── facts, projects, decisions, preferences
   ↑
EVENT BUS + POLICY (new, §18) ── proactive triggers reuse the same executor
```

Keystone insight [ASSESS]: four new systems (Task Builder, Planner, Verifier, Event Policy) unlock
almost everything; everything else is adapters on an already-working tool gateway.

## 32 · Phase Roadmap (by architectural dependency)

- **Phase 0 — Foundation (must come first)**: permission registry, task model, verifier skeleton,
  event bus skeleton, adapters pattern. *No user-visible features; everything depends on it.*
- **Phase 1 — Context & Understanding**: clipboard verbs, screen OCR/UIA reading, file intelligence
  (parse/OCR/dedupe), local semantic search (small). *High value, zero accounts, all local.*
- **Phase 2 — Real Integrations I**: Email (Gmail/Graph) full loop with confirm-first; Calendar
  (both) + availability; these two alone create most "wow".
- **Phase 3 — Multi-Step Work**: planner over primitives; progress beats; verification everywhere;
  document creation (reports/CSV/PPT). 
- **Phase 4 — Messaging adapters** (per-platform, honest classes; Telegram/Slack/Teams first —
  official paths only; WhatsApp = business-only note).
- **Phase 5 — Dev & power tools**: git/GitHub/VS Code loops; terminal-driven tasks; project memory.
- **Phase 6 — Proactive agent**: event watchers + policy + briefings; routines as saved plans.
- **Phase 7 — Computer-use fallback**: Playwright for chosen sites; vision agent last-resort with
  hard limits (no money/auth; always confirm).
- **Phase 8 — Maturation**: reliability scores per capability, memory scoping, performance,
  packaging/updater, privacy dashboard.

Dependency order matters [ASSESS]: permissions+task+verify (0) → context (1) → accounts (2) →
planning (3) → breadth (4–5) → proactivity (6) → autonomy (7) → polish (8). Building messaging
before verification, or autonomy before permissions, produces the classic fragile-bot failure.

## 33 · What Must NOT Be Built Yet

Vision-first autonomy; any purchase/payment automation; messaging self-bot automation; local LLMs
larger than small utility models (8GB ceiling); cloud-only features that break the local-first
promise; proactive triggers without the policy layer.

## 34 · Risks & Limitations (plain)

- UIA/browser fragility = ongoing maintenance cost; mitigate with adapters + recovery + honesty.
- Platform policies (WhatsApp self-automation, Discord self-bots, CAPTCHAs) = hard boundaries;
  respect them, surface them.
- Verification is never 100%; the product's promise must be honest confidence reporting.
- 8GB/no-GPU: all reasoning stays cloud (free-tier variance — we live it daily); local stays files/
  audio/index only.
- API cost creep: email/calendar APIs are free-ish; computer-use/vision loops are the expensive ones
  → keep them manual-tier.

## 35 · Final Product Vision (one paragraph)

RealAssistant becomes the **delegation layer for a personal Windows computer**: you speak a goal; it
picks the most reliable mechanism (OS → official API → scripted browser → UI automation → vision as
last resort); it executes with visible, honest state; it verifies and reports plainly; it asks only
at genuine decisions; it is local-first in privacy while using cloud intelligence where it must; and
it stays boringly reliable where it claims reliability — because that is the entire product.

---

# THE REALASSISTANT MASTER PLAN

### A · Product definition
A voice-first **delegation layer** between the user and their computer: state a goal, it plans,
executes through the most reliable available mechanism, verifies, reports; confirms only where
judgment/permission is required.

### B · Capability universe (honest classes)
Built/A: apps, windows, files, system, reminders/memory/notes. Ready-to-integrate/A: Gmail, Google
Calendar, Microsoft Graph (mail/calendar/teams), GitHub, Slack(bots), Telegram(bots), git/terminal.
Feasible B/C: document intelligence, OCR/screen reading, local semantic search, Playwright flows,
document generation. Restricted D/E: consumer WhatsApp automation, Discord/Telegram self-bots,
CAPTCHA/MFA/UAC, payments, arbitrary-app vision autonomy.

### C · Architecture
Today's conversation core + tool gateway (keep) + **Task Builder, Planner, Verifier, Permission
Registry, Event Policy, Adapter layer** (add). One executor for voice requests AND proactive events.

### D · Dependencies
Permissions/task/verify → context (files/screen/clipboard) → accounts (email/calendar) → planning →
breadth (messaging/dev) → proactivity → autonomy (browser/vision) → maturation.

### E · Phases
Phase 0 Foundation → 1 Context → 2 Email+Calendar → 3 Multi-step → 4 Messaging → 5 Dev → 6 Proactive
→ 7 Computer-use fallback → 8 Maturation. (Details in §32.)

### F · Highest-value workflows
Email triage loop; interview/day prep; document errands; file cleanup; dev fix loop; screen help;
communication errands (official paths); research briefs; workspace routines; proactive saves (§29).

### G · Limitations (cannot be promised)
No CAPTCHA/UAC bypass; no consumer WhatsApp; no self-bot messaging; no purchase automation; vision
agents remain slow/fragile (fallback only); UI automation needs maintenance; 8GB local ceiling.

### H · First engineering milestone
**The Capability Kernel** — Phase 0: Permission Registry + Task model + Verifier + Event bus skeleton
+ Adapter interface, wired into the existing tool gateway, with the Sotto UI states (acting/waiting/
progress/verifying) driven by real execution. It ships zero flashy features and makes every later
phase additive instead of a rewrite — the exact foundation the mandate asked for.

---

## Sources

### Verified in this session (2026-09-30) [V]
- Microsoft Learn — UI Automation overview (win32): learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32
- Microsoft Learn — UI Automation Fundamentals: learn.microsoft.com/en-us/windows/win32/winauto/entry-uiautocore-overview
- Microsoft Learn — UI Automation Overview (.NET): learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-overview
- Microsoft — Microsoft-UI-UIAutomation utilities (GitHub): github.com/microsoft/Microsoft-UI-UIAutomation
- Wikipedia — Microsoft UI Automation (background): en.wikipedia.org/wiki/Microsoft_UI_Automation
- Anthropic — Computer use tool docs: platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
- Anthropic — "Introducing computer use…" news: anthropic.com/news/3-5-models-and-computer-use
- Anthropic — "Developing a computer use model": anthropic.com/news/developing-computer-use
- Microsoft — Playwright repo (incl. 2026 CLI-for-agents note): github.com/microsoft/playwright
- Playwright — Best Practices: playwright.dev/docs
- Microsoft Learn — Windows Installer best practices; Graph permission pages (Calendars.ReadWrite surfaced via learn.microsoft.com search result)
- (Earlier sessions, same project: jrsoftware.org Inno Setup; advancedinstaller.com; progressive-disclosure articles)

### Official re-verification checklist [DOC → open these before building]
- Telegram: core.telegram.org/bots/api · core.telegram.org/bots/faq · telegram.org/tos
- WhatsApp: developers.facebook.com/docs/whatsapp/cloud-api · business.whatsapp.com
- Discord: discord.com/developers/docs · Discord support: "self-bot" policy article
- Slack: api.slack.com/methods · api.slack.com/scopes
- Microsoft Graph: learn.microsoft.com/graph/api/user-sendmail · /me/events · findMeetingTimes
- Gmail: developers.google.com/gmail/api (scopes + verification/CASA pages)
- Google Calendar: developers.google.com/calendar/api
- Playwright persistence/CDP: playwright.dev/docs (storageState, connectOverCDP)
- Power Automate Desktop: learn.microsoft.com/power-automate/desktop-flows
- Apple App Intents: developer.apple.com/documentation/appintents
- Windows OCR: learn.microsoft.com/uwp/api/windows.media.ocr
- Git: git-scm.com/docs · GitHub: docs.github.com/rest
- VS Code API/CLI: code.visualstudio.com/api · code.visualstudio.com/docs/editor/command-line
- Windows notifications: learn.microsoft.com/windows/apps (toast APIs)
- Anthropic computer use limits: platform.claude.com docs (already [V])

### Methodology honesty
Six parallel AI researchers were dispatched; all six timed out on the degraded search service without
producing files. Verification in this document therefore rests on: (a) the [V] sources above
(retrieved today), (b) [DOC]-marked stable platform documentation named for one-click re-verification,
and (c) clearly-labeled [ASSESS] judgment. No claim is presented as verified unless it is.
