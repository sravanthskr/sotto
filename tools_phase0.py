"""tools_phase0.py - Phase 0 quick wins.

Clipboard routing, PDF reading, file saving, screen OCR, window text (UIA),
terminal execution, typing, and named routines. Light by design:
- one-shot PowerShell helpers (built-in Windows OCR / UI Automation) - no new deps
- no resident processes, no heavy models
- routines run through tools.run() with danger tools blocked

Imported at the very end of tools.py (decorators register on import).
"""

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tools import tool

_CREATE_NO_WINDOW = 0x08000000
_BASE = Path(__file__).parent


def _ps(script_name, *args, timeout=30):
    """Run a helper PowerShell script, return stdout (or an error string)."""
    script = _BASE / script_name
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return "Error: helper timed out."
    except Exception as e:
        return f"Error: {e}"
    out = (r.stdout or "").strip()
    if r.returncode != 0 and not out:
        out = (r.stderr or "").strip() or "Error: helper failed."
    return out


# ---------------------------------------------------------------------------
# 0.2  Read a PDF (text layer) with pypdf
# ---------------------------------------------------------------------------
@tool(
    name="read_pdf",
    description=("Read a PDF document's text so you can summarize or answer questions about it. "
                 "Give the full path; if the user doesn't say which file, leave path empty and the "
                 "newest PDF in Downloads is used."),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to the PDF (optional)."},
            "chars": {"type": "integer", "description": "Max characters to return (default 16000)."},
        },
    },
)
def read_pdf(path="", chars=16000):
    from config import DOWNLOADS_DIR
    p = Path(path).expanduser() if path else None
    if not p or not p.exists():
        try:
            pdfs = sorted(DOWNLOADS_DIR.glob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
        except Exception:
            pdfs = []
        if not pdfs:
            return "Error: no PDF found - give me the full path to the file."
        p = pdfs[0]
    if p.suffix.lower() != ".pdf":
        return f"Error: {p} is not a PDF."
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        pages = len(reader.pages)
        text = []
        for i, page in enumerate(reader.pages):
            try:
                text.append(page.extract_text() or "")
            except Exception:
                text.append("")
            if sum(len(t) for t in text) > chars:
                break
        full = "\n".join(text).strip()
    except Exception as e:
        return f"Error: couldn't read the PDF ({e})."
    if not full:
        return (f"'{p.name}' has {pages} page(s) but no selectable text - it's probably a scan. "
                "(Scanned-PDF OCR is coming in the next pass.)")
    out = full[:chars]
    note = f" (first {chars} of {len(full)} chars)" if len(full) > chars else ""
    return f"PDF: {p.name} - {pages} page(s){note}\n\n{out}"


# ---------------------------------------------------------------------------
# 0.4  Save text / markdown / CSV to a file
# ---------------------------------------------------------------------------
@tool(
    name="save_text_file",
    description=("Save text content to a file on disk (txt, md, or csv). Use for 'save this as a "
                 "note', 'make me a file with this', 'export this as CSV'. Returns the full path."),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "File name (extension optional; .txt default)."},
            "content": {"type": "string", "description": "The text to save."},
            "folder": {"type": "string", "description": "Desktop (default), Downloads, or Documents."},
        },
        "required": ["name", "content"],
    },
)
def save_text_file(name, content, folder="Desktop"):
    home = Path.home()
    targets = {
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "documents": home / "Documents",
    }
    dest_dir = targets.get((folder or "desktop").lower(), home / "Desktop")
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = Path(name).name.strip() or "note.txt"
        if not Path(fname).suffix:
            fname += ".txt"
        full = dest_dir / fname
        full.write_text(str(content), encoding="utf-8")
        return f"Saved to {full} ({len(str(content))} chars)."
    except Exception as e:
        return f"Error: couldn't save the file ({e})."


# ---------------------------------------------------------------------------
# 0.5  Screen text via Windows OCR
# ---------------------------------------------------------------------------
@tool(
    name="read_screen",
    description=("Read the text on the screen right now (OCR). Use for 'what does this error say?', "
                 "'read this page/error/popup'. Returns the visible text."),
    parameters={"type": "object", "properties": {}},
)
def read_screen():
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        tmp = Path(tempfile.gettempdir()) / "realassistant_screen.png"
        img.save(str(tmp))
    except Exception as e:
        return f"Error: couldn't capture the screen ({e})."
    text = _ps("ocr_screen.ps1", str(tmp), timeout=25)
    if text.startswith("Error"):
        return text
    if not text or text == "[ocr:no-text]":
        return "(I couldn't find any text on the screen.)"
    return text[:4000]


# ---------------------------------------------------------------------------
# 0.7  Read a window's text via UI Automation
# ---------------------------------------------------------------------------
@tool(
    name="read_window_text",
    description=("Read the text content of a window (UI Automation). Leave title empty for the window "
                 "currently in front. Use to read emails/documents/forms visible in apps when asked "
                 "what's in them."),
    parameters={
        "type": "object",
        "properties": {"title": {"type": "string", "description": "Part of the window title (optional)."}},
    },
)
def read_window_text(title=""):
    text = _ps("uia_read.ps1", (title or ""), timeout=30)
    if text.startswith("Error"):
        return text
    if not text or text == "[uia:no-text]":
        return "(I couldn't read text from that window.)"
    return text[:4000]


# ---------------------------------------------------------------------------
# 0.9  Terminal execution
# ---------------------------------------------------------------------------
@tool(
    name="run_command",
    description=("Run a terminal command (cmd) and get its output - exit code, stdout, stderr. "
                 "Use for developer tasks: git, python, pip, tests, file processing. Keep commands "
                 "non-interactive."),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command line to run."},
            "cwd": {"type": "string", "description": "Working directory (optional)."},
            "timeout": {"type": "integer", "description": "Seconds before giving up (default 20, max 120)."},
        },
        "required": ["command"],
    },
)
def run_command(command, cwd="", timeout=20):
    try:
        timeout = max(1, min(120, int(timeout)))
    except Exception:
        timeout = 20
    workdir = cwd if cwd and Path(cwd).is_dir() else None
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout,
            cwd=workdir, creationflags=_CREATE_NO_WINDOW,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        parts = [f"exit code: {r.returncode}"]
        if out:
            parts.append("output:\n" + out[:6000])
        if err:
            parts.append("stderr:\n" + err[:2000])
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s and was stopped."
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# 0.10  Type text / press keys (SendInput)
# ---------------------------------------------------------------------------
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004

_VK = {
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "pageup": 0x21, "pagedown": 0x22,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p))


class _INPUTunion(ctypes.Union):
    _fields_ = (("ki", _KEYBDINPUT), ("pad", ctypes.c_byte * 24))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", ctypes.c_ulong), ("u", _INPUTunion))


def _send(vk=0, scan=0, flags=0, count=1):
    inp = _INPUT(type=1, u=_INPUTunion(ki=_KEYBDINPUT(vk, scan, flags, 0, None)))
    ctypes.windll.user32.SendInput(count, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _type_char(ch):
    if ch == "\n":
        _send(vk=0x0D)
        _send(vk=0x0D, flags=_KEYEVENTF_KEYUP)
        return
    scan = ord(ch)
    _send(scan=scan, flags=_KEYEVENTF_UNICODE)
    _send(scan=scan, flags=_KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP)


@tool(
    name="type_text",
    description=("Type text into whatever window is currently focused (keyboard input). Use to fill "
                 "fields or write into an app after focusing it with focus_window."),
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "The text to type."}},
        "required": ["text"],
    },
)
def type_text(text):
    text = str(text)[:2000]
    if not text:
        return "Error: nothing to type."
    try:
        for ch in text:
            _type_char(ch)
            time.sleep(0.004)
        return f"Typed {len(text)} characters into the focused window."
    except Exception as e:
        return f"Error: couldn't type ({e})."


@tool(
    name="press_keys",
    description=("Press a key or shortcut in the focused window, e.g. 'enter', 'ctrl+s', 'alt+tab', "
                 "'ctrl+shift+t', 'f5'."),
    parameters={
        "type": "object",
        "properties": {"keys": {"type": "string", "description": "Key combo like 'ctrl+s' or 'enter'."}},
        "required": ["keys"],
    },
)
def press_keys(keys):
    combo = [p.strip().lower() for p in str(keys).split("+") if p.strip()]
    if not combo:
        return "Error: no keys given."
    vks = []
    for part in combo:
        if part in _VK:
            vks.append(_VK[part])
        elif len(part) == 1 and part.isalnum():
            vks.append(ord(part.upper()))
        else:
            return f"Error: unknown key '{part}'."
    try:
        for vk in vks:
            _send(vk=vk)
        for vk in reversed(vks):
            _send(vk=vk, flags=_KEYEVENTF_KEYUP)
        return f"Pressed {keys}."
    except Exception as e:
        return f"Error: couldn't press keys ({e})."


# ---------------------------------------------------------------------------
# 0.6  Named routines
# ---------------------------------------------------------------------------
def _routines():
    try:
        from config import load_settings
        data = load_settings() or {}
        r = data.get("routines", {})
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}


@tool(
    name="save_routine",
    description=("Save a named routine - a chain of tool actions run together, e.g. 'start my work'. "
                 "Actions is a JSON list like [{\"tool\":\"open_application\",\"args\":{\"app_name\":\"chrome\"}}, "
                 "{\"tool\":\"set_volume\",\"args\":{\"level\":30}}]. Dangerous tools are not allowed in routines."),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Routine name, e.g. 'start my work'."},
            "actions": {"type": "string", "description": "JSON list of {tool, args} actions."},
        },
        "required": ["name", "actions"],
    },
)
def save_routine(name, actions):
    import tools as _tools
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except Exception as e:
            return f"Error: actions must be valid JSON ({e})."
    if not isinstance(actions, list) or not actions:
        return "Error: give at least one action."
    clean = []
    for a in actions:
        if not isinstance(a, dict) or "tool" not in a:
            return "Error: each action needs a 'tool' name."
        tool_name = str(a["tool"])
        if tool_name not in _tools.REGISTRY:
            return f"Error: unknown tool '{tool_name}'."
        if _tools.is_dangerous(tool_name):
            return f"Error: '{tool_name}' is a dangerous tool - not allowed in routines."
        clean.append({"tool": tool_name, "args": a.get("args") or {}})
    try:
        from config import load_settings, save_setting
        data = load_settings() or {}
        routs = data.get("routines", {}) if isinstance(data.get("routines", {}), dict) else {}
        routs[name.strip().lower()] = clean
        save_setting("routines", routs)
        return f"Saved routine '{name}' with {len(clean)} step(s)."
    except Exception as e:
        return f"Error: couldn't save routine ({e})."


@tool(name="list_routines", description="List saved routines.")
def list_routines():
    r = _routines()
    if not r:
        return "(no routines saved yet)"
    return "\n".join(f"- {k} ({len(v)} steps)" for k, v in r.items())


@tool(
    name="run_routine",
    description="Run a saved routine by name, e.g. 'start my work'.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Routine name."}},
        "required": ["name"],
    },
)
def run_routine(name):
    import tools as _tools
    r = _routines()
    key = str(name).strip().lower()
    if key not in r:
        return f"Error: no routine called '{name}'. Saved: {', '.join(r) or 'none'}."
    lines = []
    for step in r[key]:
        tname = step.get("tool")
        targs = step.get("args") or {}
        if _tools.is_dangerous(tname):
            lines.append(f"- {tname}: skipped (dangerous)")
            continue
        result = _tools.run(tname, targs)
        lines.append(f"- {tname}: {str(result)[:140]}")
    return f"Ran '{key}':\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# 0.8  Semantic file search (lazy - only loads the model when used)
# ---------------------------------------------------------------------------
@tool(
    name="index_folder",
    description=("Build or refresh the smart-search index for a folder so 'find the file about X' can "
                 "search by meaning, not just names. Light: text files only (.txt .md .py .json .log .csv)."),
    parameters={
        "type": "object",
        "properties": {"folder": {"type": "string", "description": "Folder path to index."}},
        "required": ["folder"],
    },
)
def index_folder(folder):
    try:
        import semsearch
        return semsearch.index_folder(folder)
    except ImportError:
        return "Error: semantic search isn't installed yet (needs: pip install fastembed)."
    except Exception as e:
        return f"Error: indexing failed ({e})."


@tool(
    name="smart_find",
    description=("Find files by meaning - e.g. 'the file about voice conversion'. Searches the smart "
                 "index (build one first with index_folder)."),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What you're looking for."},
            "folder": {"type": "string", "description": "Limit to one indexed folder (optional)."},
        },
        "required": ["query"],
    },
)
def smart_find(query, folder=""):
    try:
        import semsearch
        return semsearch.search(query, folder)
    except ImportError:
        return "Error: semantic search isn't installed yet (needs: pip install fastembed)."
    except Exception as e:
        return f"Error: search failed ({e})."
