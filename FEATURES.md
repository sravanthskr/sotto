# RealAssistant — Feature Inventory (everything implemented)

_Deduplicated: "open Telegram" and "open notepad" count as ONE feature (Opening apps), not two._
_Status: ✅ working · ◐ partial (foundation exists) · ○ not yet built (candidates at the end)._

## 1 · Conversation & intelligence
| Feature | What it does |
|---|---|
| ✅ Natural conversation | Voice or typed, same pipeline; keeps context across turns ("what about tomorrow?") |
| ✅ Multi-step reasoning | One ask → several tools in sequence ("open chrome and set volume to 30") |
| ✅ Persona | Talks like a person — short, casual, never mentions being an AI or "tools" |
| ✅ Streaming replies | Text appears as it's generated; speech starts with the first sentence |
| ✅ Intent chip | Quiet tag showing what it understood ("SET REMINDER", "OPEN APP") |
| ✅ Follow-up suggestions | In-flow chips after each answer (Tell me more / Do that again / Never mind) |
| ✅ Answer actions | Copy · Speak again · Slower under each answer |
| ✅ Voice-only commands | "repeat that" / "say it slower" replay instantly, no AI round-trip |
| ✅ Never-silent guarantee | Empty model replies → retried → visible notice; never a blank turn |
| ✅ Weak-model hardening | Planning-leak filter + tool-call-as-text recovery (free-model quirks handled) |

## 2 · AI brain & reliability
| Feature | What it does |
|---|---|
| ✅ Multi-provider chain | 5 providers, automatic failover on failure (503/429/timeout), cooldowns |
| ✅ Sticky best provider | Remembers which provider worked and starts there (persisted) |
| ✅ Smart retries | Engine waits out rate-limits; UI auto-retries (4s, 30s) before giving up |
| ✅ Human errors only | Raw errors/JSON are never shown — calm lines + retry instead |
| ✅ Full request log | Everything recorded to `ui.log` for diagnosis |

## 3 · Voice input
| Feature | What it does |
|---|---|
| ✅ Push-to-talk | Hold **Space** — release sends |
| ✅ Click-to-talk | Mic button toggle + presence click |
| ✅ Auto end-of-speech | Stops listening ~2s after you stop talking (no manual "done") |
| ✅ Live voice reaction | The presence visual moves with your real voice level while listening |
| ✅ Offline speech recognition | Two local engines (vosk + faster-whisper), no cloud, model pre-warmed |
| ✅ Graceful miss | "I didn't quite catch that" instead of dead air |

## 4 · Voice output
| Feature | What it does |
|---|---|
| ✅ Speaks replies | Persistent speech engine; instant dispatch; queues, never overlaps |
| ✅ Custom cloned voice | "Scarlett" — offline voice conversion, selectable in Settings; verified by round-trip |
| ✅ Voice is a choice | System voices = instant plain speech (engine bypassed); custom = pipeline |
| ✅ Interrupt | Stop speech instantly (Space/mic); **stop ≠ cancel** — the task continues silently |
| ✅ Speak-aloud toggle | Mute spoken replies, keep text |
| ✅ Voice picker + test | Choose any installed voice; "Test" hears it once |

## 5 · Apps & windows
| Feature | What it does |
|---|---|
| ✅ Open any installed app | Fuzzy name match; scans Start Menu/Desktop/taskbar (223 indexed here; adapts to any PC) |
| ✅ Close apps | Confirmation-guarded |
| ✅ Window control | List/focus/minimize/maximize/snap any open window |
| ✅ Chrome profiles | List and open specific browser profiles |

## 6 · System control & status
| Feature | What it does |
|---|---|
| ✅ Volume | Get / set |
| ✅ Brightness | Get / set |
| ✅ Media control | Play / pause / next / previous |
| ✅ Power actions | Lock · Sleep · **Shutdown (with cancel)** · Restart — all confirmed first |
| ✅ System status | CPU / RAM / disk / battery + top processes |
| ✅ Network check | Quick connectivity status |
| ✅ Autostart | See and set Windows startup behavior |

## 7 · Files & downloads
| Feature | What it does |
|---|---|
| ✅ Find files | By name/pattern, anywhere |
| ✅ Search inside files | Find text within documents |
| ✅ File ops | Copy · move · rename · delete (guarded) · create folder |
| ✅ Folders | Open folders · list contents |
| ✅ Read files | Reads text files aloud/answers from them |
| ✅ Organize Downloads | Auto-sorts by type into folders — **with Undo** |

## 8 · Memory & personal data
| Feature | What it does |
|---|---|
| ✅ Long-term memory | Remembers facts about you; recalls on request ("what do you know about me") |
| ✅ Forget / list facts | Manage what's remembered |
| ✅ Auto-learning | Learns new facts from conversations in the background |
| ✅ Conversation history | Sessions saved; day-grouped browsing; search; restore; delete; "+ New" |
| ✅ Notes | Add · list · search · delete |
| ✅ Reminders / timers | "in 10 minutes" or absolute; list & cancel; fires a notification |
| ✅ Activity log | Full audit of what it did on your PC |

## 9 · Web & info
| Feature | What it does |
|---|---|
| ✅ Web search | Live results in natural answers |
| ✅ Look-ups | Quick facts without opening a browser |
| ✅ Webpages | Read a page's content / open a site |
| ✅ Weather | Local forecast read aloud |

## 10 · Screen & clipboard
| Feature | What it does |
|---|---|
| ✅ Screenshots | Takes + files them automatically |
| ✅ Clipboard | Read · write ("what did I copy?") |

## 11 · Proactive & ambient
| Feature | What it does |
|---|---|
| ✅ Proactive nudges | Watcher can surface helpful suggestions periodically |
| ✅ Daily briefing | One summary of the day |

## 12 · The UI (Sotto)
| Feature | What it does |
|---|---|
| ✅ Living presence | One morphing visual across 11 states (idle·ready·listening·understanding·thinking·acting·waiting·responding·interrupted·denied·offline) — never a spinner |
| ✅ Home | Presence + hint + 4 suggestion chips + clock/connection line — nothing else |
| ✅ Side panels | History / Memory / Settings push the layout (never cover content); direct switching; click-outside closes |
| ✅ Memory hub | Memory · Notes · Tasks · Activity tabs with real data + empty states |
| ✅ Quick settings popover | Theme · voice · sound · wake · motion under the gear |
| ✅ Inline typing | Mic morphs into a text input in place (Ctrl+K); Esc back to voice |
| ✅ Keyboard shortcuts | Ctrl+K · Ctrl+Shift+H/M/S/D · hold-Space · Esc |
| ✅ Themes | Light (default) + dark; instant switch; **remembered across restarts** |
| ✅ First-run scan | Ask-once prompt + Settings rescan (user-initiated, plain language) |
| ✅ Feedback layer | Toasts, calm notices w/ retry, drag-to-dismiss sheets |
| ✅ Accessibility | Screen-reader live region, focus rings, 44px targets, reduced-motion support |
| ✅ Contextual cards | Timer/meter/system cards render from tool results (data-driven) |

## 13 · Safety & operations
| Feature | What it does |
|---|---|
| ✅ Confirmation guard | Dangerous actions ask first — system dialog or in-chat yes/no (works by voice) |
| ✅ Denied-tools list | Hard blocklist in settings |
| ✅ Local-first | STT, TTS, custom voice and memory never leave the PC; keys in `.env` only |
| ✅ One-file launcher | `run.bat` modes: ui / voice / check / mic / providers / api / qt |
| ✅ Self-tests & CI | selftest, e2e, provider/voice/API checks + CI workflow |

---

## Not yet built — candidates for the next level
- **Installer + auto-update** (plan written: `V1_PRODUCT_PLAN.md`)
- **Wake word** (toggle exists; listening backend not implemented) ◐
- **Live partial transcript** while speaking (caret-only today) ◐
- **Sound effects** (preference saved; cues not implemented) ◐
- Volume/media **card widgets** in chat (backend tools exist; payload rendering not wired) ◐
- File drag-and-drop onto the window
- ONNX speedup for the custom voice (~1.5–3× faster conversion)
- Multi-language STT/TTS, calendar/email integrations, skill marketplace…
