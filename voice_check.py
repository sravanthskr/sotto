"""
voice_check.py - full voice self-diagnosis.

    python voice_check.py          # check everything (no recording)
    python voice_check.py --mic    # also record 4s and show the level + transcript

Every line prints PASS or FAIL with the exact fix, so nothing fails silently.
"""

import sys
import tempfile
from pathlib import Path

import voice

_TMP = Path(tempfile.gettempdir())


def check(ok, label, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))
    return bool(ok)


def main():
    print(f"python: {sys.executable}")

    print("\n=== text-to-speech ===")
    voices = voice.list_voices()
    check(bool(voices), "speech voices installed", ", ".join(voices) or "none found")
    wav = _TMP / "vocheck_tts.wav"
    check(voice.speak_to_wav("voice check", str(wav)),
          "can synthesise speech to audio")

    print("\n=== speech-to-text ===")
    deps = True
    for module in ("sounddevice", "numpy", "vosk"):
        try:
            __import__(module)
        except ImportError:
            deps = False
            check(False, f"{module} importable", f"fix: pip install {module}")
    if deps:
        check(True, "sounddevice + numpy + vosk importable")

    model = voice.vosk_model()
    check(bool(model), "vosk model found",
          model or "see README for the one-time model download")

    devices = voice.list_input_devices()
    check(bool(devices), "microphone(s) found", f"{len(devices)} input device(s)")
    for dev in devices[:8]:
        print(f"        [{dev['index']}]{' *default*' if dev['default'] else ''} {dev['name']}")

    print("\n=== result ===")
    ready = voice.stt_ready()
    check(ready, "offline speech recognition ready")
    if not ready:
        print(f"\n  you are running: {sys.executable}")
        print("  that's the wrong Python. Use the project one instead:")
        print("        .\\run.bat check")
        print("        .\\run.bat mic      (to test the microphone)")

    if "--mic" in sys.argv:
        print("\n=== live mic test (4s) - SPEAK NOW ===")
        out = _TMP / "vocheck_mic.wav"
        ok, level, err = voice.record_wav(out, seconds=4)
        check(ok, "recorded audio", err or f"level={level:.0f}")
        if ok:
            text, terr = voice.transcribe_wav(out)
            print("        heard:", repr(text) if terr is None else f"(error: {terr})")
            if level < 50:
                print("        !! very low level - set \"mic_device\": <index> in settings.json")
    else:
        print("\n(tip: run `run.bat mic` to test the microphone)")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
