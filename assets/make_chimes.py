"""Generates Sotto's cue sounds (run: python make_chimes.py)."""
import os
import numpy as np
import wave


def chime(seq, name, peak=0.45):
    sr = 44100
    out = np.zeros(0, dtype=np.float32)
    for freq, dur in seq:
        n = int(sr * dur)
        t = np.arange(n) / sr
        env = np.minimum(1.0, t / 0.012) * np.exp(-t * (3.2 / max(dur, 0.05)))
        tone = (0.62 * np.sin(2 * np.pi * freq * t)
                + 0.30 * np.sin(2 * np.pi * freq * 2 * t)
                + 0.10 * np.sin(2 * np.pi * freq * 3 * t))
        out = np.concatenate([out, (tone * env).astype(np.float32),
                              np.zeros(int(sr * 0.05), dtype=np.float32)])
    out = out / np.max(np.abs(out)) * peak
    with wave.open(os.path.join(os.path.dirname(__file__), name), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())
    print("wrote", name)


if __name__ == "__main__":
    chime([(659.25, 0.085), (987.77, 0.19)], "chime_up.wav")       # activated / listening
    chime([(784.0, 0.075), (587.33, 0.17)], "chime_down.wav", peak=0.40)  # stopped
