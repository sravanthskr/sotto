"""
audio.py - live microphone level + buffered recording, for the voice UI visualiser.

MicStream.start() begins capturing on a background thread and exposes `.level`
(0.0-1.0, smoothed for animation). stop() returns the path to a 16 kHz mono WAV.
"""

import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from config import MIC_DEVICE


_MIC_LOCK = threading.Lock()


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
            if down > 1:
                try:
                    sd.check_input_settings(device=self.device, samplerate=cap_sr, channels=1, dtype="int16")
                except Exception:
                    cap_sr, down = self.sr, 1
                    frame_b = int(cap_sr * 0.03) * 2
            with sd.RawInputStream(samplerate=cap_sr, channels=1, dtype="int16",
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


class VoiceCapture:
    """Precise utterance capture for hands-free listening.

    Uses the WebRTC voice-activity engine (webrtcvad) - the same family
    of VAD used by established local voice pipelines - with a
    noise-calibrated level detector as fallback. Records 16 kHz mono
    30 ms frames; speech starts after 3 voiced frames in a row and ends
    after `end_silence` seconds of unvoiced frames. No hard-coded
    amplitude assumptions, so it adapts to any microphone gain."""

    def __init__(self, device=None, samplerate=16000, end_silence=0.9,
                 no_speech_timeout=8.0, max_len=45.0, vad_mode=2):
        if device is None:
            try:
                from config import load_settings as _ls
                device = _ls().get("mic_device")
            except Exception:
                device = None
            if device is None:
                device = MIC_DEVICE
        self.device = device
        self.sr = samplerate
        self.end_silence = max(0.3, float(end_silence or 0.9))
        self.no_speech_timeout = float(no_speech_timeout or 8.0)
        self.max_len = float(max_len or 45.0)
        self.vad_mode = int(vad_mode if vad_mode is not None else 2)
        self.level = 0.0
        self.heard = False
        self.canceled = False
        self.error = None
        self.stats = {}
        self._frames = []
        self._done = threading.Event()
        self._should_stop = None
        self._thread = None
        self._force = False

    def start(self, should_stop=None):
        self._should_stop = should_stop
        self._done.clear()
        self._frames = []
        self.heard = False
        self.canceled = False
        self.error = None
        self.level = 0.0
        self._force = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        import queue
        from collections import deque
        cap_sr = self.sr
        down = 1
        if int(self.sr) == 16000:
            cap_sr, down = 48000, 3
        frame_b = int(cap_sr * 0.03) * 2          # 30 ms int16
        q = queue.Queue()

        def callback(indata, frames, tinfo, status):
            q.put(bytes(indata))

        try:
            import webrtcvad
            vad = webrtcvad.Vad(self.vad_mode)
        except Exception:
            vad = None
        preroll = deque(maxlen=10)
        frames = []
        started = False
        voiced = 0
        voiced2 = 0
        unvoiced = 0
        floor = None
        peak = 0.0
        gpeak = 0.0
        recv = 0
        t0 = time.time()
        try:
            if not _MIC_LOCK.acquire(timeout=8):
                raise RuntimeError("microphone busy")
            try:
                with sd.RawInputStream(samplerate=self.sr, channels=1, dtype="int16",
                                       blocksize=frame_b // 2, callback=callback,
                                       device=self.device):
                    while True:
                        if self._force:
                            if not started:
                                self.canceled = True
                            break
                        if self._should_stop and self._should_stop():
                            if not started:
                                self.canceled = True
                            break
                        el = time.time() - t0
                        try:
                            raw = q.get(timeout=0.1)
                        except queue.Empty:
                            raw = None
                        if raw is None:
                            if not started and el > self.no_speech_timeout:
                                break
                            if started and el > self.max_len:
                                break
                            continue
                        if len(raw) < frame_b:
                            continue
                        raw = raw[:frame_b]
                        if down > 1:
                            _a = np.frombuffer(raw, dtype="int16")
                            _a = _a[:(len(_a) // down) * down].reshape(-1, down).mean(axis=1).astype("int16")
                            raw = _a.tobytes()
                        recv += 1
                        smp = np.frombuffer(raw, dtype="int16").astype("float32") / 32768.0
                        rms = float(np.sqrt((smp ** 2).mean())) if smp.size else 0.0
                        if rms > gpeak:
                            gpeak = rms
                        elif gpeak > 0:
                            gpeak *= 0.9995
                        if rms > peak:
                            peak = rms
                        self.level = min(1.0, rms / 0.25)
                        if vad is not None:
                            try:
                                vad_speech = vad.is_speech(raw, self.sr)
                            except Exception:
                                vad_speech = False
                        else:
                            vad_speech = True
                        # noise floor: tracks the quietest level the mic shows
                        if floor is None:
                            floor = rms
                        elif rms < floor * 1.5:
                            floor = floor * 0.98 + rms * 0.02
                        else:
                            floor = floor * 1.001
                        gate = max(floor * 1.6, 0.015)
                        speech = bool(vad_speech and rms > gate)
                        speech2 = bool(vad_speech and rms > max(floor * 1.15, 0.010))
                        if not started:
                            preroll.append(raw)
                            voiced = voiced + 1 if speech else 0
                            voiced2 = voiced2 + 1 if speech2 else 0
                            if voiced >= 3 or voiced2 >= 14:
                                started = True
                                self.heard = True
                                frames = list(preroll)
                                self.stats["onset"] = round(el, 2)
                                self.stats["floor"] = round(floor, 4)
                        else:
                            frames.append(raw)
                            unvoiced = 0 if speech else unvoiced + 1
                            keep = int(max(3, round(self.end_silence / 0.03)))
                            if unvoiced >= keep:
                                break
                            if el > self.max_len:
                                break
                        if not started and el > self.no_speech_timeout:
                            break
            finally:
                _MIC_LOCK.release()
        except Exception as e:
            self.error = str(e)
        if self.error is None and recv == 0:
            self.error = "no mic frames (device stall)"
        self._frames = frames
        self.stats.update({
            "vad": "webrtc" if vad is not None else "level",
            "dur": round(len(frames) * 0.03, 2),
            "peak": round(peak, 4),
            "floor_final": round(floor or 0.0, 4),
            "cap_sr": cap_sr,
            "gain_peak": round(gpeak, 4),
            "recv": recv,
            "frames": len(frames),
        })
        self._done.set()

    def stop_now(self):
        """Ask the capture to end immediately (thread-safe)."""
        self._force = True
        self._done.wait(3.0)

    def wait(self, timeout=60.0):
        self._done.wait(timeout)
        return self._done.is_set()

    def stop(self):
        self._done.wait(60.0)
        if self._thread:
            self._thread.join(timeout=2)
        path = Path(tempfile.gettempdir()) / "ra_voice_turn.wav"
        frames = b"".join(self._frames)
        try:
            arr = np.frombuffer(frames, dtype="int16").astype("float32")
            pk = float(np.abs(arr).max()) if arr.size else 0.0
            if pk > 1:
                arr = arr * (0.55 * 32767.0 / pk)
                frames = arr.astype("int16").tobytes()
        except Exception:
            pass
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes(frames)
        return str(path)
