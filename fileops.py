"""
fileops.py - file organising (mainly the Downloads folder).

`organize_downloads()` sorts loose files into category subfolders and records the
moves so `undo_organize()` can put everything back.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from config import DOWNLOADS_DIR, ORGANIZE_LOG

CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tif",
               ".tiff", ".heic", ".ico"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
               ".mpg", ".mpeg"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".opus"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx",
                  ".csv", ".ppt", ".pptx", ".md", ".epub"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".apk", ".appx"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".c", ".cpp",
             ".cs", ".go", ".rs", ".sh", ".bat", ".ps1"},
}


def category_for(suffix):
    s = (suffix or "").lower()
    for cat, exts in CATEGORIES.items():
        if s in exts:
            return cat
    return "Other"


def list_folder(path, limit=40):
    """Return (subfolder_names, file_names) or (None, None) if not a folder."""
    p = Path(path)
    if not p.is_dir():
        return None, None
    entries = sorted(p.iterdir(), key=lambda x: x.name.lower())
    dirs = [e.name for e in entries if e.is_dir()][:limit]
    files = [e.name for e in entries if e.is_file()][:limit]
    return dirs, files


def organize_downloads(path=None):
    root = Path(path) if path else DOWNLOADS_DIR
    if not root.is_dir():
        return f"Error: there's no folder at {root}."

    moves = []
    for item in sorted(root.iterdir()):
        if not item.is_file():
            continue
        dest_dir = root / category_for(item.suffix)
        dest = dest_dir / item.name
        if dest.exists():
            dest = dest_dir / f"{item.stem}_{datetime.now():%H%M%S}{item.suffix}"
        try:
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(dest))
            moves.append({"src": str(item), "dst": str(dest)})
        except Exception:
            continue  # file in use / locked - leave it alone

    if not moves:
        return "Nothing to organise - that folder is already tidy."

    ORGANIZE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ORGANIZE_LOG, "w", encoding="utf-8") as f:
        json.dump({"when": datetime.now().isoformat(timespec="seconds"),
                   "root": str(root), "moves": moves}, f, indent=2)

    counts = {}
    for m in moves:
        cat = Path(m["dst"]).parent.name
        counts[cat] = counts.get(cat, 0) + 1
    summary = ", ".join(f"{v} {k.lower()}" for k, v in sorted(counts.items()))
    return f"Moved {len(moves)} files ({summary}). Say 'undo' to put them back."


def undo_organize():
    if not ORGANIZE_LOG.exists():
        return "Nothing to undo."
    try:
        data = json.loads(ORGANIZE_LOG.read_text(encoding="utf-8"))
    except Exception as e:
        return f"Error: couldn't read the undo log ({e})."

    restored = 0
    for m in data.get("moves", []):
        src, dst = Path(m["dst"]), Path(m["src"])
        try:
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                restored += 1
        except Exception:
            continue
    try:
        ORGANIZE_LOG.unlink()
    except OSError:
        pass
    return f"Put {restored} files back where they were."


# ---------------------------------------------------------------------------
# Move / copy / rename
# ---------------------------------------------------------------------------
def _expand(p):
    return Path(os.path.expandvars(os.path.expanduser(str(p).strip())))


def _dest_path(src, dst):
    """Work out the final destination (into a folder, and never overwrite)."""
    if dst.is_dir():
        dst = dst / src.name
    if dst.exists():
        dst = dst.with_name(f"{dst.stem}_{datetime.now():%H%M%S}{dst.suffix}")
    return dst


def move_path(src, dst):
    s, d = _expand(src), _expand(dst)
    if not s.exists():
        return f"Error: there's nothing at '{src}'."
    d = _dest_path(s, d)
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return f"Moved '{s.name}' to {d}."
    except Exception as e:
        return f"Error: couldn't move it ({e})."


def copy_path(src, dst):
    s, d = _expand(src), _expand(dst)
    if not s.exists():
        return f"Error: there's nothing at '{src}'."
    d = _dest_path(s, d)
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(str(s), str(d))
        else:
            shutil.copy2(str(s), str(d))
        return f"Copied '{s.name}' to {d}."
    except Exception as e:
        return f"Error: couldn't copy it ({e})."


def rename_path(path, new_name):
    p = _expand(path)
    if not p.exists():
        return f"Error: there's nothing at '{path}'."
    new_name = str(new_name).strip()
    if not new_name:
        return "Error: I need a new name."
    target = p.with_name(new_name if Path(new_name).suffix else new_name + p.suffix)
    if target.exists():
        return f"Error: '{target.name}' already exists."
    try:
        p.rename(target)
        return f"Renamed '{p.name}' to '{target.name}'."
    except Exception as e:
        return f"Error: couldn't rename it ({e})."
