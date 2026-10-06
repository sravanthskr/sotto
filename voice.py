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
import threading
import wave
from pathlib import Path

from config import VOICE_NAME, VOICE_RATE, MIC_DEVICE, STT_MODEL

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


_cv_queue = None
_cv_thread = None


def _ensure_cv_thread():
    global _cv_thread, _cv_queue
    import queue as _q
    if _cv_queue is None:
        _cv_queue = _q.Queue()
    if _cv_thread is None or not _cv_thread.is_alive():
        _cv_thread = threading.Thread(target=_cv_worker, daemon=True)
        _cv_thread.start()


def _cv_worker():
    """One sentence at a time, in arrival order: render -> convert -> play."""
    while True:
        item = _cv_queue.get()
        if item is None:
            return
        text, voice_name, rate = item
        try:
            _speak_custom_sync(text, voice_name, rate)
        except Exception:
            pass


def _speak_custom_sync(text, voice_name, rate):
    import voice_convert
    src = Path(tempfile.gettempdir()) / "realassistant_say.wav"
    out = Path(tempfile.gettempdir()) / "realassistant_say_cv.wav"
    if speak_to_wav(text, src, voice=voice_name or None, rate=rate):
        converted = voice_convert.convert(src, out)
        voice_convert.play_wav(converted or src)


def speak(text, voice=None, rate=None):
    """Say something out loud. If a custom voice is installed, use it."""
    text = (text or "").strip()
    if not text:
        return False

    # custom voice pipeline: TTS -> local conversion -> play (queued, ordered)
    try:
        import voice_convert
        if voice_convert.model_ready():
            _ensure_cv_thread()
            _cv_queue.put((text, voice, rate))
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


# ---------------------------------------------------------------------------
# fast speech output: one persistent SAPI process (no per-line startup cost)
# ---------------------------------------------------------------------------
class Speaker:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()

    def _ensure(self):
        if self.proc is not None and self.proc.poll() is None:
            return
        select = f"$s.SelectVoice('{_q(VOICE_NAME)}'); " if VOICE_NAME else ""
        script = ("Add-Type -AssemblyName System.Speech; "
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  f"$s.Rate = {int(VOICE_RATE)}; {select}"
                  "while ($true) { $l = [Console]::In.ReadLine(); "
                  "if ($l -eq $null) { break }; "
                  "if ($l.Trim().Length -gt 0) { $s.Speak($l) } }")
        self.proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", script],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=_NO_WINDOW)

    def say(self, text):
        text = (text or "").strip()
        if not text:
            return False
        with self.lock:
            try:
                self._ensure()
                self.proc.stdin.write(text.replace("\n", " ") + "\n")
                self.proc.stdin.flush()
                return True
            except Exception:
                self.proc = None
                return False

    def stop(self):
        try:
            if self.proc and self.proc.stdin:
                self.proc.stdin.close()
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass
        self.proc = None


_speaker = None


def speaker():
    global _speaker
    if _speaker is None:
        _speaker = Speaker()
    return _speaker


def say(text):
    """Speak without blocking the caller (used for streamed sentences)."""
    return speaker().say(text)


def stop_speaking():
    global _speaker
    if _speaker is not None:
        _speaker.stop()
        _speaker = None
    try:
        import voice_convert
        voice_convert.stop_playback()
    except Exception:
        pass
    try:
        while _cv_queue is not None:
            _cv_queue.get_nowait()
    except Exception:
        pass


def warm():
    """Preload the speech-to-text model so the first request isn't slow."""
    def _load():
        try:
            _whisper()
        except Exception:
            pass
    threading.Thread(target=_load, daemon=True).start()


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
    except ImportError:
        return False
    if _whisper_model_name():
        return True
    if vosk_model() and _vosk_importable():
        return True
    return False


def _vosk_importable():
    try:
        import vosk  # noqa: F401
        return True
    except ImportError:
        return False


_WHISPER_CACHE = {"model": None, "name": None}


def _whisper_model_name():
    """The faster-whisper model name, or None if the library isn't installed."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return None
    return STT_MODEL or "small.en"


def _whisper():
    """Lazily load (and cache) the faster-whisper model."""
    name = _whisper_model_name()
    if not name:
        return None
    if _WHISPER_CACHE["model"] is not None and _WHISPER_CACHE["name"] == name:
        return _WHISPER_CACHE["model"]
    try:
        from faster_whisper import WhisperModel
        import os as _os
        threads = min(8, _os.cpu_count() or 4)
        _WHISPER_CACHE["model"] = WhisperModel(name, device="cpu", compute_type="int8",
                                               cpu_threads=threads)
        _WHISPER_CACHE["name"] = name
        return _WHISPER_CACHE["model"]
    except Exception:
        return None


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


def transcribe_wav(path, initial_prompt=None, vad_filter=True):
    """Return (text, error). Uses faster-whisper when available, else Vosk."""
    model = _whisper()
    if model is not None:
        try:
            segments, _info = model.transcribe(
                str(path), language="en", vad_filter=vad_filter,
                condition_on_previous_text=False, beam_size=1,
                initial_prompt=initial_prompt)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text, None
        except Exception as e:
            return None, str(e)
    return _vosk_transcribe(path)


def _vosk_transcribe(path):
    model_path = vosk_model()
    if not model_path:
        return None, "no speech model found"
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
