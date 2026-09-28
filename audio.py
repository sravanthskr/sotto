"""
audio.py - live microphone level + buffered recording, for the voice UI visualiser.

MicStream.start() begins capturing on a background thread and exposes `.level`
(0.0-1.0, smoothed for animation). stop() returns the path to a 16 kHz mono WAV.
"""

import tempfile
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from config import MIC_DEVICE


class MicStream:
    def __init__(self, device=None, samplerate=16000):
        self.device = MIC_DEVICE if device is None else device
        self.sr = samplerate
        self.level = 0.0
        self.error = None
        self._frames = []
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._frames = []
        self.error = None
        self.level = 0.0
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        def callback(indata, frames, time_info, status):
            raw = bytes(indata)
            self._frames.append(raw)
            samples = np.frombuffer(raw, dtype="int16")
            if samples.size:
                rms = float(np.sqrt((samples.astype("float32") ** 2).mean()))
                self.level = min(1.0, rms / 3000.0)

        try:
            with sd.RawInputStream(samplerate=self.sr, channels=1, dtype="int16",
                                   blocksize=1024, callback=callback, device=self.device):
                while not self._stop.is_set():
                    sd.sleep(25)
        except Exception as e:      # mic busy / no device / bad rate
            self.error = str(e)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        return self._write()

    def _write(self):
        path = Path(tempfile.gettempdir()) / "ra_voice_ui.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes(b"".join(self._frames))
        return str(path)
