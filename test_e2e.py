"""
test_e2e.py - a scripted end-to-end test that actually talks to the model.

It points memory/notes/reminders at a temporary folder, runs a few safe prompts through
the real Assistant engine, and checks it responds. Uses a few API calls.

    python test_e2e.py
"""

import tempfile
from pathlib import Path

# redirect storage to a temp dir BEFORE anything reads it, so the real files are untouched
import memory
import notes
import reminders

_TEMP = Path(tempfile.mkdtemp())
memory.MEMORY_FILE = _TEMP / "memory.json"
notes.NOTES_FILE = _TEMP / "notes.json"
reminders.REMINDERS_FILE = _TEMP / "reminders.json"

import tools          # noqa: E402
from core import Assistant  # noqa: E402

PROMPTS = [
    "what's two plus two? just the number",
    "what's my system status?",
    "do you remember anything about me?",
]


def main():
    tools.build_app_index()
    assistant = Assistant()   # no callbacks -> silent

    answered = 0
    for prompt in PROMPTS:
        try:
            reply = assistant.ask(prompt)
        except Exception as e:
            print(f"  Q: {prompt}\n  ERROR: {e}\n")
            continue
        print(f"  Q: {prompt}\n  A: {reply[:140]!r}\n")
        if reply:
            answered += 1

    print(f"responded to {answered}/{len(PROMPTS)} prompts")
    ok = answered == len(PROMPTS)
    print("E2E OK" if ok else "E2E FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
