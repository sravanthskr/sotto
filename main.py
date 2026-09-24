"""
main.py - the console front-end.

All the intelligence lives in core.Assistant; this file only handles the terminal
(typing, and printing what the assistant says and does).
"""

import sys

from config import MODEL_NAME, ensure_settings_file
import tools
from core import Assistant


def _setup_console():
    """Stop non-cp1252 characters (smart quotes, dashes) from crashing output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_setup_console()


def main():
    ensure_settings_file()
    print(f"Starting up... (model: {MODEL_NAME})")

    state = {"speaking": False, "spoke": False, "tool": False}

    def on_text(chunk):
        if not state["speaking"]:
            print("AI: ", end="", flush=True)
            state["speaking"] = True
            state["spoke"] = True
        print(chunk, end="", flush=True)

    def on_tool(name, args, result):
        if state["speaking"]:
            print()
            state["speaking"] = False
        state["tool"] = True
        print(f"  [{name} -> {result}]")

    def on_reminder(message):
        print(f"\n*** Reminder: {message} ***\n")

    def on_proactive(message):
        print(f"\n[proactive] Heads up - {message}.\n")

    def on_learned(facts):
        print(f"\n[memory] learned: {'; '.join(facts)}")

    assistant = Assistant(on_text=on_text, on_tool=on_tool, on_reminder=on_reminder,
                          on_proactive=on_proactive, on_learned=on_learned)
    assistant.start()

    print(f"[apps] indexed {tools.APP_INDEX.__len__()} shortcuts.")
    if assistant.remembered_count():
        print(f"[memory] remembered {assistant.remembered_count()} thing(s) about you.")
    if assistant.pending_reminders():
        print(f"[reminders] {assistant.pending_reminders()} reminder(s) waiting.")
    print("Ready. Type 'exit' to quit.\n")

    try:
        while True:
            try:
                user_text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_text:
                continue
            if user_text.lower() in ("exit", "quit"):
                break

            state["spoke"] = False
            state["tool"] = False
            try:
                assistant.ask(user_text)
            except Exception as e:
                print(f"  [error] {e}")

            if state["speaking"]:
                print()
                state["speaking"] = False
            if not state["spoke"] and not state["tool"]:
                print("AI: hmm, I didn't catch that - say it again?")
            elif not state["spoke"] and state["tool"]:
                print("AI: done.")
    finally:
        assistant.stop()


if __name__ == "__main__":
    main()
