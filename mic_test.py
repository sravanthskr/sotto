"""
mic_test.py - diagnose the microphone and offline speech recognition.

    python mic_test.py

It lists your input devices, records a few seconds, shows the level, and prints what the
offline recogniser heard. If the level is near zero, the default mic isn't the one you're
speaking into - set "mic_device" in settings.json to the right index.
"""

import sys
from pathlib import Path

import voice


def main():
    print("=== input devices ===")
    devices = voice.list_input_devices()
    if not devices:
        print("  none found - is `sounddevice` installed?  (pip install sounddevice vosk)")
    for dev in devices:
        mark = "  <-- default" if dev["default"] else ""
        print(f"  [{dev['index']}] {dev['name']}{mark}")

    print("\n=== offline model ===")
    print("  vosk model:", voice.vosk_model() or "NOT FOUND")
    print("  stt ready :", voice.stt_ready())

    seconds = 4
    print(f"\n=== recording {seconds}s from the default mic - SAY SOMETHING NOW ===")
    out = Path("mic_test.wav")
    ok, level, err = voice.record_wav(out, seconds=seconds)
    print(f"  recorded={ok}  level={level:.0f}  -> {out.resolve()}")
    if err:
        print("  error:", err)

    if ok and level < 50:
        print("  !! level is very low - the default mic probably isn't the one you spoke into.")
        print("     Set \"mic_device\": <index> in settings.json to the device you actually use.")

    if out.exists():
        text, err = voice.transcribe_wav(out)
        if err:
            print("  vosk error:", err)
        else:
            print("  vosk heard:", repr(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
