"""
voice.py - offline voice input/output.

Everything runs on your PC - no cloud, no API, no GPU:

  * Text-to-speech   -> Windows System.Speech (the voices you already have)
  * Speech-to-text   -> Vosk (offline, CPU) with Windows System.Speech as a fallback

Speech-to-text needs `sounddevice` + `vosk` and a small model (see README). If they're
missing, listening just returns nothing and speaking still works.
"""

import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path

from config import VOICE_NAME, VOICE_RATE, MIC_DEVICE

_PS = ["powershell", "-NoProfile", "-Command"]
_NO_WINDOW = 0x08000000
_TIMEOUT = 60

_MODEL_DIR = Path(os.getenv("LOCALAPPDATA", "")) / "RealAssistant" / "models"
_MODEL_NAMES = ["vosk-model-small-en-us-0.15"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _run(script, timeout=_TIMEOUT):
    return subprocess.run(_PS + [script], capture_output=True, text=True,
                          creationflags=_NO_WINDOW, timeout=timeout)


def _q(text):
    return str(text).replace("'", "''")


# ---------------------------------------------------------------------------
# text-to-speech (Windows voices)
# ---------------------------------------------------------------------------
def list_voices():
    script = ("Add-Type -AssemblyName System.Speech; "
              "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
              ".GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }")
    return [line.strip() for line in (_run(script).stdout or "").splitlines() if line.strip()]


def default_voice():
    return VOICE_NAME or ""


def list_recognizers():
    """Ids of the Windows offline recognisers (the fallback engine)."""
    script = ("Add-Type -AssemblyName System.Speech; "
              "[System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()"
              " | ForEach-Object { $_.Id }")
    return [line.strip() for line in (_run(script).stdout or "").splitlines() if line.strip()]


def speak(text, voice=None, rate=None):
    """Say something out loud. If a custom voice is installed, use it."""
    text = (text or "").strip()
    if not text:
        return False

    # custom voice pipeline: TTS -> local conversion -> play
    try:
        import voice_convert
        if voice_convert.model_ready():
            src = Path(tempfile.gettempdir()) / "realassistant_say.wav"
            out = Path(tempfile.gettempdir()) / "realassistant_say_cv.wav"
            if speak_to_wav(text, src, voice=voice, rate=rate):
                converted = voice_convert.convert(src, out)
                if converted and voice_convert.play_wav(converted):
                    return True
    except Exception:
        pass

    voice = voice if voice is not None else (VOICE_NAME or None)
    rate = VOICE_RATE if rate is None else rate
    select = f"$s.SelectVoice('{_q(voice)}'); " if voice else ""
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = {int(rate)}; {select}$s.Speak('{_q(text)}');")
    return _run(script).returncode == 0


def speak_to_wav(text, path, voice=None, rate=None):
    """Render speech to a .wav file (used for testing, and for voice conversion later)."""
    text = (text or "").strip()
    if not text:
        return False
    voice = voice if voice is not None else (VOICE_NAME or None)
    rate = VOICE_RATE if rate is None else rate
    select = f"$s.SelectVoice('{_q(voice)}'); " if voice else ""
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = {int(rate)}; {select}"
              f"$s.SetOutputToWaveFile('{_q(path)}'); $s.Speak('{_q(text)}'); "
              "$s.SetOutputToNull();")
    return _run(script).returncode == 0


# ---------------------------------------------------------------------------
# speech-to-text (Vosk, offline)
# ---------------------------------------------------------------------------
def vosk_model():
    """Path to the downloaded Vosk model, or None."""
    for name in _MODEL_NAMES:
        path = _MODEL_DIR / name
        if path.exists():
            return str(path)
    return None


def stt_ready():
    try:
        import sounddevice  # noqa: F401
        import vosk         # noqa: F401
    except ImportError:
        return False
    return vosk_model() is not None


def list_input_devices():
    """[{index, name, default}] for every microphone-style input device."""
    try:
        import sounddevice as sd
    except ImportError:
        return []
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = -1
    out = []
    for index, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            out.append({"index": index, "name": dev["name"], "default": index == default_in})
    return out


def _resample(samples, src_rate, dst_rate=16000):
    """Linear resample of int16 samples to 16 kHz (Vosk wants 16 kHz mono)."""
    import numpy as np
    if src_rate == dst_rate or samples.size == 0:
        return samples
    count = int(len(samples) * dst_rate / src_rate)
    old = np.linspace(0, 1, len(samples), endpoint=False)
    new = np.linspace(0, 1, count, endpoint=False)
    return np.interp(new, old, samples.astype("float32")).astype("int16")


def record_wav(path, seconds=4, device=None):
    """Record mono audio from the mic. Returns (ok, level, error)."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as e:
        return False, 0.0, f"sounddevice/numpy not installed ({e})"

    dev = MIC_DEVICE if device is None else device

    # work out a sample rate the device actually supports
    rates = [16000]
    try:
        info = sd.query_devices(dev) if dev is not None else sd.query_devices(kind="input")
        rates.insert(0, int(info.get("default_samplerate") or 16000))
    except Exception:
        pass

    audio, used, last_err = None, None, None
    for rate in rates:
        try:
            audio = sd.rec(int(seconds * rate), samplerate=rate, channels=1,
                           dtype="int16", device=dev)
            sd.wait()
            used = rate
            break
        except Exception as e:
            last_err = str(e)
            audio = None
    if audio is None:
        return False, 0.0, last_err or "recording failed"

    samples = np.frombuffer(audio.tobytes(), dtype="int16")
    if used != 16000:
        samples = _resample(samples, used, 16000)

    try:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(samples.astype("int16").tobytes())
    except Exception as e:
        return False, 0.0, str(e)

    level = float((samples.astype("float32") ** 2).mean() ** 0.5) if samples.size else 0.0
    return True, level, None


def transcribe_wav(path):
    """Return (text, error). text is '' when nothing was understood."""
    model_path = vosk_model()
    if not model_path:
        return None, "no vosk model found"
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        with wave.open(str(path), "rb") as wf:
            recognizer = KaldiRecognizer(Model(model_path), wf.getframerate())
            pieces = []
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                if recognizer.AcceptWaveform(data):
                    pieces.append(json.loads(recognizer.Result()).get("text", ""))
            pieces.append(json.loads(recognizer.FinalResult()).get("text", ""))
        return " ".join(p for p in pieces if p).strip(), None
    except Exception as e:
        return None, str(e)


def _windows_listen(timeout):
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


def listen_once(timeout=6, device=None, prefer_vosk=True):
    """Listen once and return the recognised text (offline), or ''."""
    if prefer_vosk and stt_ready():
        tmp = Path(tempfile.gettempdir()) / "realassistant_listen.wav"
        ok, _level, _err = record_wav(tmp, seconds=timeout, device=device)
        if ok:
            text, _err = transcribe_wav(tmp)
            return text or ""
        return ""
    return _windows_listen(timeout)
