"""
main.py - the console front-end.

All the intelligence lives in core.Assistant; this file only handles the terminal
(typing, and showing what the assistant says and does).
"""

import sys

from config import MODEL_NAME, ensure_settings_file, missing_deps
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


def _report_deps():
    missing = missing_deps()
    if missing:
        pip_names = " ".join(pip for _, pip in missing)
        print(f"[deps] running on: {sys.executable}")
        print(f"[deps] missing libraries: {', '.join(mod for mod, _ in missing)}")
        print(f'[deps] install with: "{sys.executable}" -m pip install {pip_names}')


def main():
    ensure_settings_file()
    print(f"Starting up... (model: {MODEL_NAME})")
    _report_deps()

    state = {"speaking": False, "spoke": False, "tool": False}

    def on_status(status):
        # a tiny live indicator so you can tell it's working, not frozen
        sys.stdout.write("  ... thinking\r" if status == "thinking" else " " * 16 + "\r")
        sys.stdout.flush()

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
                          on_proactive=on_proactive, on_learned=on_learned,
                          on_status=on_status)
    assistant.start()

    print(f"[apps] indexed {len(tools.APP_INDEX)} shortcuts.")
    if assistant.remembered_count():
        print(f"[memory] remembered {assistant.remembered_count()} thing(s) about you.")
    if assistant.pending_reminders():
        print(f"[reminders] {assistant.pending_reminders()} reminder(s) waiting.")
    print("Ready. Type 'exit' to quit.\n")

    assistant.start_watcher()   # start nudges only after we've printed "Ready"

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
