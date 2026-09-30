"""semsearch.py - small local semantic search for the smart-find feature.

Light on purpose: fastembed (ONNX, CPU) + numpy, model loads only when used.
Index lives in %LOCALAPPDATA%\\RealAssistant\\semantic\\<key>.npz
"""

import hashlib
import json
import os
from pathlib import Path

import numpy as np

STORE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RealAssistant" / "semantic"
EXTS = {".txt", ".md", ".py", ".json", ".log", ".csv", ".ini", ".cfg", ".html", ".js", ".css"}
MAX_FILES = 300
MAX_CHARS_PER_FILE = 20000
CHUNK = 800

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return _model


def _key(folder):
    return hashlib.md5(str(Path(folder).resolve()).lower().encode()).hexdigest()[:12]


def _store_paths(folder):
    k = _key(folder)
    STORE.mkdir(parents=True, exist_ok=True)
    return STORE / f"{k}.npz", STORE / f"{k}.json"


def index_folder(folder):
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        return f"Error: {folder} is not a folder."
    files = []
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", "_shots"}]
        for n in names:
            p = Path(root) / n
            if p.suffix.lower() in EXTS:
                files.append(p)
            if len(files) >= MAX_FILES:
                break
        if len(files) >= MAX_FILES:
            break

    chunks, meta = [], []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:MAX_CHARS_PER_FILE]
        except Exception:
            continue
        for i in range(0, len(text), CHUNK):
            piece = text[i:i + CHUNK].strip()
            if len(piece) >= 60:
                chunks.append(piece)
                meta.append({"file": str(p), "pos": i})
    if not chunks:
        return f"No indexable text found in {folder}."

    model = _get_model()
    vectors = np.array(list(model.embed(chunks)), dtype=np.float32)
    npz, meta_path = _store_paths(folder)
    np.savez_compressed(npz, vec=vectors)
    meta_path.write_text(json.dumps({"folder": str(folder), "meta": meta}), encoding="utf-8")
    return f"Indexed {len(files)} files ({len(chunks)} chunks) from {folder}."


def search(query, folder=""):
    STORE.mkdir(parents=True, exist_ok=True)
    stores = [Path(folder)] if folder else []
    if not stores:
        for meta_path in STORE.glob("*.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                f = data.get("folder")
                if f and Path(f).is_dir():
                    stores.append(Path(f))
            except Exception:
                continue
    if not stores:
        return "No index built yet - run index_folder on a folder first."

    model = _get_model()
    qv = np.array(list(model.embed([query]))[0], dtype=np.float32)
    qv = qv / (np.linalg.norm(qv) + 1e-9)

    results = []
    for f in stores:
        npz, meta_path = _store_paths(f)
        if not npz.exists():
            continue
        try:
            vec = np.load(npz)["vec"]
            meta = json.loads(meta_path.read_text(encoding="utf-8"))["meta"]
        except Exception:
            continue
        norms = np.linalg.norm(vec, axis=1, keepdims=True) + 1e-9
        sims = (vec / norms) @ qv
        order = np.argsort(-sims)[:8]
        for idx in order:
            m = meta[idx]
            snippet = ""
            try:
                text = Path(m["file"]).read_text(encoding="utf-8", errors="replace")
                snippet = text[m["pos"]:m["pos"] + 160].replace("\n", " ").strip()
            except Exception:
                pass
            results.append((float(sims[idx]), m["file"], snippet))

    results.sort(key=lambda r: -r[0])
    if not results:
        return "Nothing found."
    lines = []
    for score, file, snippet in results[:6]:
        lines.append(f"- {file}  (match {score:.2f})\n  …{snippet[:140]}…")
    return "\n".join(lines)
