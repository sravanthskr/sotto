"""
voice_convert.py - custom voice (RVC) conversion via a persistent worker.

The voice is a CHOICE: pick "Scarlett (custom)" in the app and replies run
through the RVC pipeline; pick any system voice and the app uses plain SAPI
with no extra processing.

The worker (rvc_worker.py) loads the model once and stays warm, so each
sentence costs only the conversion time, not a model reload.
"""

import json
import os
import subprocess
import sys
import threading
import winsound
from pathlib import Path

from config import CUSTOM_VOICE, VOICE_MODELS_DIR

_LOCK = threading.Lock()
_WORKER = None
_LOG = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RealAssistant" / "rvc_worker.log"


def voices_dir():
    return VOICE_MODELS_DIR


def available_voices():
    """Names of installed custom voices (folders containing a .pth model)."""
    if not VOICE_MODELS_DIR.exists():
        return []
    return sorted(p.name for p in VOICE_MODELS_DIR.iterdir()
                  if p.is_dir() and any(p.glob("*.pth")))


def configured_voice():
    return CUSTOM_VOICE or ""


def model_dir(name=None):
    name = name or configured_voice()
    if not name:
        return None
    path = VOICE_MODELS_DIR / name
    return path if path.is_dir() else None


def model_ready(name=None):
    return model_dir(name) is not None


def runtime_ready():
    try:
        import rvc_python  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def _readline_timeout(proc, timeout):
    box = {}

    def _r():
        try:
            box["line"] = proc.stdout.readline()
        except Exception:
            pass

    t = threading.Thread(target=_r, daemon=True)
    t.start()
    t.join(timeout)
    return box.get("line")


def _kill_worker():
    global _WORKER
    try:
        if _WORKER is not None and _WORKER.poll() is None:
            try:
                _WORKER.stdin.write("__quit__\n")
                _WORKER.stdin.flush()
            except Exception:
                pass
            try:
                _WORKER.wait(timeout=3)
            except Exception:
                try:
                    _WORKER.kill()
                except Exception:
                    pass
    except Exception:
        pass
    _WORKER = None


def _ensure_worker():
    global _WORKER
    if _WORKER is not None and _WORKER.poll() is None:
        return _WORKER
    if not runtime_ready():
        return None
    env = dict(os.environ)
    env["RVC_NAME"] = configured_voice() or "scarlett"
    try:
        from config import RVC_F0METHOD, RVC_INDEX_RATE
        env["RVC_F0"] = str(RVC_F0METHOD)
        env["RVC_INDEX"] = str(RVC_INDEX_RATE)
    except Exception:
        pass
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        log = open(_LOG, "a", encoding="utf-8")
    except Exception:
        log = subprocess.DEVNULL
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "rvc_worker.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
        text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent), env=env,
    )
    line = _readline_timeout(proc, 180)
    try:
        hello = json.loads(line or "{}")
    except Exception:
        hello = {}
    if not hello.get("ready"):
        try:
            proc.kill()
        except Exception:
            pass
        return None
    _WORKER = proc
    return _WORKER


def convert(wav_in, wav_out, name=None):
    """Convert a WAV into the target voice. Returns wav_out on success, else None."""
    if model_dir(name) is None:
        return None
    with _LOCK:
        try:
            w = _ensure_worker()
            if w is None:
                return None
            w.stdin.write(json.dumps({"src": str(wav_in), "out": str(wav_out)}) + "\n")
            w.stdin.flush()
            resp = _readline_timeout(w, 120)
            data = json.loads(resp or "{}")
            if data.get("ok") and Path(wav_out).exists():
                return wav_out
            _kill_worker()
        except Exception:
            _kill_worker()
    return None


def prewarm():
    """Start loading the worker in the background (when the custom voice is picked)."""
    def _go():
        with _LOCK:
            try:
                _ensure_worker()
            except Exception:
                pass
    threading.Thread(target=_go, daemon=True).start()


def play_wav(path):
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return True
    except Exception:
        return False


def stop_playback():
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass