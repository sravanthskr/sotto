"""
voice_convert.py - the plug-in point for a custom voice.

Right now this is a safe no-op: with no model installed it simply passes audio through, so
nothing breaks. Once you have an RVC-style model for a target voice (see VOICE_GUIDE.md),
drop it in `%LOCALAPPDATA%\\RealAssistant\\voices\\<name>\\` and set:

    "custom_voice": "<name>"

in settings.json. From then on, replies are spoken with the plain Windows voice, converted
locally into your target voice (CPU, no GPU, no API), and played back.
"""

import shutil
import winsound
from pathlib import Path

from config import CUSTOM_VOICE, VOICE_MODELS_DIR


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
        return True
    except ImportError:
        return False


def convert(wav_in, wav_out, name=None):
    """Convert a WAV into the target voice. Returns wav_out on success, else None."""
    directory = model_dir(name)
    if directory is None:
        return None
    if not runtime_ready():
        # no conversion runtime yet - pass the audio straight through
        try:
            shutil.copyfile(wav_in, wav_out)
            return wav_out
        except Exception:
            return None
    try:
        from rvc_python.infer import RVCInference
        RVCInference(models_dir=str(directory)).infer_file(str(wav_in), str(wav_out))
        return wav_out
    except Exception:
        return None


def play_wav(path):
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return True
    except Exception:
        return False
