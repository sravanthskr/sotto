"""
voice_main.py - the hands-free front-end.

Press Enter, speak, and it answers out loud. Risky actions are confirmed by voice too, so
you can approve them by saying "yes" instead of clicking anything.

    python voice_main.py     (or use run.bat with the voice switch)

Everything runs offline on the PC's own speech engine - no API calls, no GPU.
"""

import sys

from config import MODEL_NAME, ensure_settings_file
import voice
from core import Assistant


def _setup_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_setup_console()

_YES = ("yes", "yeah", "yep", "ok", "okay", "sure", "do it", "go ahead", "affirmative")


def main():
    ensure_settings_file()
    print(f"Voice mode (model: {MODEL_NAME})")

    voices = voice.list_voices()
    print(f"[voice] {len(voices)} voice(s): {', '.join(voices[:5])}")
    if not voice.stt_ready():
        print("[voice] speech recognition isn't ready - run:  python voice_check.py")
        print("[voice] (you can still type requests below)")

    buffer = []

    def on_text(chunk):
        buffer.append(chunk)

    def on_tool(name, args, result):
        print(f"  [{name} -> {result}]")

    def on_confirm(question, detail):
        print(f"  [?] {question}")
        try:
            voice.speak(question)
            heard = voice.listen_once(5).lower()
        except Exception as e:
            print(f"  [voice error] {e}")
            heard = ""
        print(f"  (heard: {heard!r})")
        return any(word in heard for word in _YES)

    def on_reminder(message):
        print(f"\n*** Reminder: {message} ***\n")
        voice.speak(f"Reminder: {message}")

    assistant = Assistant(on_text=on_text, on_tool=on_tool, on_confirm=on_confirm,
                          on_reminder=on_reminder)
    assistant.start()
    print("Ready. Press Enter to talk (or type a request). 'exit' to quit.\n")
    assistant.start_watcher()

    try:
        while True:
            try:
                typed = input("[Enter = talk] ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if typed.lower() in ("exit", "quit"):
                break

            if typed:
                user_text = typed                 # typed fallback
            else:
                print("  listening...")
                try:
                    user_text = voice.listen_once(8)
                except Exception as e:
                    print(f"  [mic error] {e}")
                    user_text = ""
                print(f"  heard: {user_text!r}")
            if not user_text:
                continue

            buffer.clear()
            try:
                assistant.ask(user_text)
            except Exception as e:
                print(f"  [error] {e}")
            reply = "".join(buffer).strip()
            if reply:
                try:
                    voice.speak(reply)
                except Exception as e:
                    print(f"  [speak error] {e}")
    finally:
        assistant.stop()


if __name__ == "__main__":
    main()
