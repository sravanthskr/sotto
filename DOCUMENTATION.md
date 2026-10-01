# Documentation Guide

How documentation in this repository is organized — and where future information should go.

## Current layout

All documents live at the repository root for now (the project is young; keeping them close to the code is deliberate).

| Document | Purpose |
|---|---|
| `README.md` | Product overview, quick start, status. The entry point. |
| `WHAT_SOTTO_DOES_TODAY.md` | Plain-language sheet of what works today. |
| `FEATURES.md` | Full feature inventory (grouped, deduped). |
| `V1_PRODUCT_PLAN.md` | Product plan and test checklist. |
| `IMPLEMENTATION_PLAN.md` | Engineering roadmap, phased. |
| `ACCOUNTS_SETUP.md` | Connecting Google, email, and calendar. |
| `VOICE_GUIDE.md` / `VOICE_TEST.md` | Voice system: usage and testing. |
| `TESTING.md` | How to test the assistant. |
| `BRAND_DISCOVERY.md` | Product identity, naming, brand direction. |
| `CAPABILITY_RESEARCH.md` | Research: what's possible, what's next. |
| `HANDOFF.md` | Maintainer notes: architecture, files, gotchas. |
| `PROJECT_BRIEF.md` | Original project brief. |
| `DOCUMENTATION.md` | This file. |

## Recommended layout (as the project grows)

When root-level docs become too many, move detailed pages under `docs/` and keep `README.md` as the entry point:

```text
README.md                 # map: what this is, why it matters, how to start
docs/
├── getting-started.md    # install & first run, in depth
├── features.md           # detailed feature behavior
├── architecture.md       # technical design (from HANDOFF.md)
├── configuration.md      # keys, settings, connections
├── integrations.md       # Google, .ics, providers
├── roadmap.md            # future plans (from IMPLEMENTATION_PLAN.md)
├── troubleshooting.md    # known problems and fixes
└── contributing.md       # development setup and contribution guide
```

Only create files that are actually needed. A small project with twelve tight documents beats a big project with forty thin ones.

## Maintenance rules

1. **README = map.** Product overview, quick start, current status only. Deep detail links out.
2. **One fact, one home.** If it's explained in a detail document, the README summarizes in one line and links — it does not duplicate.
3. **Status sections stay honest.** Whenever a feature moves (working → in progress → planned, or the reverse), update it in the same change that moves the code. `WHAT_SOTTO_DOES_TODAY.md` and the README's Current Status must agree.
4. **Screenshots are documentation.** They live in `_shots/`. When the UI changes meaningfully, replace the outdated ones and keep only the strongest examples in the README.
5. **Changes between versions** go in `CHANGELOG.md` (create it at the first tagged release) — never in the README.
6. **Design debates, experiments, and internal TODOs** stay out of the README; they belong in issues or working notes.
7. **No secrets, tokens, or personal data** in any document or screenshot.
8. **New features:** decide first whether the README even needs to change (most features only touch `FEATURES.md`). If the product story changed, update the README's story sections — don't append a new section for every feature.
