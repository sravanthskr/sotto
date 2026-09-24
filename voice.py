"""
voice.py - offline voice input/output using Windows' built-in speech engine.

No cloud, no API calls, no GPU, no model downloads:

  * Text-to-speech  -> System.Speech.Synthesis  (the voices already on your PC)
  * Speech-to-text  -> System.Speech.Recognition (works offline)

Swapping in your own custom voice sample is a later step (see README - Voice).
Everything here is plain PowerShell + the .NET speech assemblies that ship with Windows.
"""

import subprocess

_PS = ["powershell", "-NoProfile", "-Command"]
_NO_WINDOW = 0x08000000
_TIMEOUT = 60


def _run(script, timeout=_TIMEOUT):
    return subprocess.run(_PS + [script], capture_output=True, text=True,
                          creationflags=_NO_WINDOW, timeout=timeout)


def _q(text):
    return str(text).replace("'", "''")


def list_voices():
    """Names of the speech voices installed on this PC."""
    script = ("Add-Type -AssemblyName System.Speech; "
              "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
              ".GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }")
    r = _run(script)
    return [line.strip() for line in (r.stdout or "").splitlines() if line.strip()]


def list_recognizers():
    """Ids of the offline speech recognisers available on this PC."""
    script = ("Add-Type -AssemblyName System.Speech; "
              "[System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()"
              " | ForEach-Object { $_.Id }")
    r = _run(script)
    return [line.strip() for line in (r.stdout or "").splitlines() if line.strip()]


def speak(text, voice=None, rate=0):
    """Say something out loud with the PC's own voices. Returns True on success."""
    text = (text or "").strip()
    if not text:
        return False
    select = f"$s.SelectVoice('{_q(voice)}'); " if voice else ""
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = {int(rate)}; {select}$s.Speak('{_q(text)}');")
    return _run(script).returncode == 0


def speak_to_wav(text, path, voice=None, rate=0):
    """Render speech to a .wav file (handy for testing without making noise)."""
    text = (text or "").strip()
    if not text:
        return False
    select = f"$s.SelectVoice('{_q(voice)}'); " if voice else ""
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = {int(rate)}; {select}"
              f"$s.SetOutputToWaveFile('{_q(path)}'); $s.Speak('{_q(text)}'); "
              "$s.SetOutputToNull();")
    return _run(script).returncode == 0


def listen_once(timeout=6):
    """Listen on the default mic once and return the recognised text (offline), or ''."""
    script = ("Add-Type -AssemblyName System.Speech; "
              "$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
              "$r.SetInputToDefaultAudioDevice(); "
              "$r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar)); "
              f"$res = $r.Recognize([TimeSpan]::FromSeconds({int(timeout)})); "
              "if ($res) { $res.Text }")
    try:
        return (_run(script, timeout=timeout + 20).stdout or "").strip()
    except Exception:
        return ""
