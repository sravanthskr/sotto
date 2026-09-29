"""rvc_worker.py - persistent RVC voice-conversion worker.

Spun up on demand by voice_convert.py when the custom voice is selected.
Loads the model once, then converts one wav per line:

    {"src": "in.wav", "out": "out.wav"}   ->   {"ok": true, "ms": 1234}

Library chatter is redirected to stderr, so stdout carries only protocol JSON.
"""
import json
import os
import sys
import time

_PROTO = sys.__stdout__
sys.stdout = sys.stderr  # rvc_python prints to stdout; keep the protocol pipe clean


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)

    import torch
    torch.set_num_threads(max(4, min(8, os.cpu_count() or 4)))

    import voice_convert
    from rvc_python.infer import RVCInference

    models_dir = str(voice_convert.voices_dir())
    name = os.environ.get("RVC_NAME") or voice_convert.configured_voice() or "scarlett"
    f0 = os.environ.get("RVC_F0", "rmvpe")
    idx_rate = float(os.environ.get("RVC_INDEX", "0.5"))

    t0 = time.time()
    rvc = RVCInference(models_dir=models_dir, device="cpu:0")
    rvc.load_model(name)
    print(json.dumps({"ready": True, "load_s": round(time.time() - t0, 1)}), file=_PROTO, flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line == "__quit__":
            break
        try:
            task = json.loads(line)
            t0 = time.time()
            rvc.set_params(f0method=f0, index_rate=idx_rate, protect=0.33, rms_mix_rate=0.25)
            rvc.infer_file(task["src"], task["out"])
            print(json.dumps({"ok": True, "ms": int((time.time() - t0) * 1000)}), file=_PROTO, flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)[:300]}), file=_PROTO, flush=True)


if __name__ == "__main__":
    main()