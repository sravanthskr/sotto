"""
tools.py - the hands.

Every capability the assistant can actually perform lives here, registered with
@tool(...). The registry is what gets sent to the model as callable schema, and what
main.py dispatches to. Adding a new ability is: write the function, decorate it, done.

Security model: the cloud model NEVER runs anything itself. It can only ask for one of
these named tools with JSON arguments. Everything is validated and executed locally.
"""

import ctypes
import os
import re
import shutil
import subprocess
import webbrowser
import winreg
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import audit
import briefing
import display
import fileops
import sysactions
import winctl
from config import SCREENSHOT_DIR, DOWNLOADS_DIR, DENIED_TOOLS

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
REGISTRY = {}


def tool(name=None, description="", parameters=None, danger=False):
    """Register a function as a callable tool."""
    def deco(func):
        REGISTRY[name or func.__name__] = {
            "func": func,
            "danger": danger,
            "schema": {
                "type": "function",
                "function": {
                    "name": name or func.__name__,
                    "description": description,
                    "parameters": parameters or {
                        "type": "object", "properties": {}, "required": [],
                    },
                },
            },
        }
        return func
    return deco


def schemas():
    """Tool schemas to hand to the model."""
    return [t["schema"] for t in REGISTRY.values()]


def is_dangerous(name):
    return bool(REGISTRY.get(name, {}).get("danger"))


def run(name, args):
    """Execute a registered tool safely, respecting settings, and log it."""
    entry = REGISTRY.get(name)
    if not isinstance(args, dict):
        args = {}
    if not entry:
        result = f"Error: unknown tool '{name}'."
        audit.log(name, args, result)
        return result
    if name in DENIED_TOOLS:
        result = f"Error: '{name}' is disabled in settings."
        audit.log(name, args, result, danger=entry["danger"])
        return result
    try:
        result = str(entry["func"](**args))
    except TypeError as e:
        result = f"Error: bad arguments for {name}: {e}"
    except Exception as e:
        result = f"Error: {name} failed: {e}"
    audit.log(name, args, result, danger=entry["danger"])
    return result


# ---------------------------------------------------------------------------
# App discovery: Start Menu + Desktop (user & public) + Taskbar + Registry
# ---------------------------------------------------------------------------
APP_INDEX = {}   # normalised display name -> shortcut path

CUSTOM_APP_PATHS = {
    # If an app still won't open, drop its .exe path here, e.g.:
    # "telegram": r"C:\Users\srava\AppData\Roaming\Telegram Desktop\Telegram.exe",
}


def _normalize(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _shortcut_sources():
    """(directory, recurse) pairs.

    Start Menu nests apps inside folders, so we recurse there. Desktop and the taskbar
    pin folder are flat lists of shortcuts - and the Desktop can contain huge project
    folders, so we must NOT recurse into it.
    """
    roaming = os.getenv("APPDATA", "")
    common = os.getenv("PROGRAMDATA", "")
    user = os.getenv("USERPROFILE", "")
    public = os.getenv("PUBLIC", "")
    sources = [
        (Path(roaming) / "Microsoft/Windows/Start Menu/Programs", True),
        (Path(common) / "Microsoft/Windows/Start Menu/Programs", True),
        (Path(roaming) / "Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar", False),
        (Path(user) / "Desktop", False),
        (Path(public) / "Desktop", False),
    ]
    return [(d, r) for d, r in sources if str(d) not in (".", "") and d.is_dir()]


def _shortcut_dirs():
    """Back-compat helper: just the directories (no recursion flag)."""
    return [d for d, _ in _shortcut_sources()]


def build_app_index(verbose=False):
    """Scan for app shortcuts once at startup. Call again if you install new apps."""
    APP_INDEX.clear()
    sources = _shortcut_sources()
    for d, recurse in sources:
        iterator = d.rglob("*.lnk") if recurse else d.glob("*.lnk")
        for p in iterator:
            name = _normalize(p.stem)
            if name:
                APP_INDEX.setdefault(name, str(p))
    if verbose:
        print(f"[apps] indexed {len(APP_INDEX)} shortcuts from {len(sources)} locations.")
    return APP_INDEX


# Kept for backward compatibility with the old debug/verify scripts.
def build_start_menu_cache():
    return build_app_index(verbose=True)


SYSTEM_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file manager": "explorer.exe",
    "file explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "settings": "ms-settings:",
    "snipping tool": "snippingtool.exe",
}


def _match_score(q, name):
    if q == name:
        return 100
    nt = name.split()
    if nt and q == nt[0]:
        return 92                       # "chrome" == first word of "chrome remote desktop"
    if q in nt:
        return 82                       # exact word somewhere
    if name.startswith(q + " ") or name.startswith(q):
        return 72
    if q in name:
        return 60
    if set(q.split()) and set(q.split()) <= set(nt):
        return 70
    return 0


def _registry_lookup(q):
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for exe in (f"{q}.exe", q):
            try:
                key = winreg.OpenKey(
                    hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}")
                try:
                    path, _ = winreg.QueryValueEx(key, None)
                finally:
                    winreg.CloseKey(key)
                if path:
                    return path
            except FileNotFoundError:
                continue
            except OSError:
                continue
    return None


def resolve_app(query):
    """Turn a human app name into something launchable, or return None."""
    q = _normalize(query)
    if not q:
        return None
    if q in CUSTOM_APP_PATHS:
        return CUSTOM_APP_PATHS[q]
    if q in SYSTEM_APPS:
        return SYSTEM_APPS[q]
    if q in APP_INDEX:
        return APP_INDEX[q]

    # ranked fuzzy match: best score wins, ties broken by shortest name
    candidates = sorted(
        ((_match_score(q, name), len(name), path) for name, path in APP_INDEX.items()),
        key=lambda t: (-t[0], t[1]),
    )
    if candidates and candidates[0][0] >= 60:
        return candidates[0][2]

    reg = _registry_lookup(q)
    if reg:
        return reg
    exe = shutil.which(q) or shutil.which(q + ".exe")
    if exe:
        return exe
    return None


# Windows process-creation flags
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000


def _launch(target):
    """Launch something *detached*, so it can't hijack the assistant's console.

    Some apps (e.g. ampcast) dump their own stdout into whatever console launched
    them. We hand them no handles and detach, so the chat window stays clean.
    """
    target = str(target)
    flags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", target],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        return True, ""
    except Exception as e:
        try:
            os.startfile(target)
            return True, ""
        except Exception:
            return False, str(e)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@tool(
    name="open_application",
    description="Open an application on the user's computer, e.g. Chrome, Spotify, Notepad, Telegram.",
    parameters={
        "type": "object",
        "properties": {"app_name": {"type": "string", "description": "Name of the app to open."}},
        "required": ["app_name"],
    },
)
def open_application(app_name):
    target = resolve_app(app_name)
    if not target:
        return f"Error: couldn't find an app called '{app_name}'."
    ok, err = _launch(target)
    if ok:
        return f"Opened {app_name}."
    return f"Error: could not open {app_name}: {err}"


@tool(
    name="close_application",
    description="Close or quit a running application by name.",
    parameters={
        "type": "object",
        "properties": {"app_name": {"type": "string", "description": "App to close, e.g. Notepad."}},
        "required": ["app_name"],
    },
    danger=True,
)
def close_application(app_name):
    q = _normalize(app_name)
    target = resolve_app(app_name)
    exe = None
    if target and str(target).lower().endswith(".exe"):
        exe = Path(target).name
    if not exe:
        exe = q.replace(" ", "") + ".exe"
    try:
        r = subprocess.run(["taskkill", "/IM", exe], capture_output=True, text=True)
    except Exception as e:
        return f"Error: {e}"
    if r.returncode == 0:
        return f"Closed {app_name}."
    return f"Couldn't close {app_name} - it may not be running."


@tool(
    name="open_website",
    description="Open a website in the user's default browser.",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The website, e.g. youtube.com"}},
        "required": ["url"],
    },
)
def open_website(url):
    url = (url or "").strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}."


@tool(
    name="search_web",
    description="Search the web for a query by opening the search in the browser.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to search for."}},
        "required": ["query"],
    },
)
def search_web(query):
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    return f"Searched for '{query}'."


@tool(
    name="take_screenshot",
    description="Take a screenshot and save it to the user's Pictures folder.",
)
def take_screenshot():
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Error: Pillow isn't installed (run: pip install Pillow)."
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"shot_{datetime.now():%Y%m%d_%H%M%S}.png"
    ImageGrab.grab().save(path)
    return f"Screenshot saved to {path}."


# wired up by main.py so this tool can write to the persistent memory store
_MEMORY = None


def set_memory(mem):
    global _MEMORY
    _MEMORY = mem


@tool(
    name="remember",
    description="Store a durable fact about the user so it's remembered in future sessions.",
    parameters={
        "type": "object",
        "properties": {"fact": {"type": "string", "description": "The fact to remember."}},
        "required": ["fact"],
    },
)
def remember(fact):
    if _MEMORY is None:
        return "Error: memory isn't available right now."
    return _MEMORY.add_fact(fact)


# ---------------------------------------------------------------------------
# Folders, system info, media keys, clipboard
# ---------------------------------------------------------------------------
@tool(
    name="open_folder",
    description="Open a folder in File Explorer. Defaults to the user's home folder.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Folder path (optional)."}},
        "required": [],
    },
)
def open_folder(path=""):
    raw = (path or "").strip() or str(Path.home())
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not p.exists():
        return f"Error: there's no folder at '{raw}'."
    try:
        os.startfile(str(p))
        return f"Opened {p}."
    except Exception as e:
        return f"Error: {e}"


@tool(
    name="create_folder",
    description="Create a new folder at a given path.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Full path to create."}},
        "required": ["path"],
    },
)
def create_folder(path):
    p = Path(os.path.expandvars(os.path.expanduser(str(path).strip())))
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Created {p}."
    except Exception as e:
        return f"Error: {e}"


@tool(
    name="get_system_info",
    description="Quick system info: current time, free disk space, and battery level.",
)
def get_system_info():
    bits = [f"Time: {datetime.now():%Y-%m-%d %H:%M}"]
    try:
        total, used, free = shutil.disk_usage("C:\\")
        gb = 1024 ** 3
        bits.append(f"Disk C: {free / gb:.1f} GB free of {total / gb:.1f} GB")
    except Exception:
        pass
    try:
        class _POWER(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_byte),
                        ("BatteryFlag", ctypes.c_byte),
                        ("BatteryLifePercent", ctypes.c_byte),
                        ("SystemStatusFlag", ctypes.c_byte),
                        ("BatteryLifeTime", ctypes.c_ulong),
                        ("BatteryFullLifeTime", ctypes.c_ulong)]
        st = _POWER()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
            pct = st.BatteryLifePercent
            if 0 <= pct <= 100:
                bits.append(f"Battery: {pct}%")
    except Exception:
        pass
    return ". ".join(bits) + "."


# virtual-key codes for the media/volume keys
_MEDIA_KEYS = {
    "play pause": 0xB3, "play": 0xB3, "pause": 0xB3, "toggle": 0xB3,
    "next": 0xB0, "skip": 0xB0,
    "previous": 0xB1, "prev": 0xB1, "back": 0xB1,
    "stop": 0xB2,
    "mute": 0xAD, "unmute": 0xAD,
    "volume up": 0xAF, "louder": 0xAF,
    "volume down": 0xAE, "quieter": 0xAE,
}


@tool(
    name="control_media",
    description=("Control music/video and volume. action is one of: play_pause, next, "
                 "previous, stop, mute, volume_up, volume_down."),
    parameters={
        "type": "object",
        "properties": {"action": {"type": "string", "description": "The media action to perform."}},
        "required": ["action"],
    },
)
def control_media(action):
    key = _MEDIA_KEYS.get(_normalize(action))
    if key is None:
        return f"Error: don't know how to '{action}'."
    try:
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)  # 2 = key-up
        return f"Done: {action}."
    except Exception as e:
        return f"Error: {e}"


@tool(name="read_clipboard", description="Read the current clipboard text.")
def read_clipboard():
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                           capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW)
    except Exception as e:
        return f"Error: {e}"
    if r.returncode != 0:
        return "Error: couldn't read the clipboard."
    text = (r.stdout or "").strip()
    return text[:2000] if text else "(the clipboard is empty)"


@tool(
    name="write_clipboard",
    description="Copy the given text to the clipboard.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to copy."}},
        "required": ["text"],
    },
)
def write_clipboard(text):
    cmd = "$in = [Console]::In.ReadToEnd(); Set-Clipboard -Value $in"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           input=str(text), capture_output=True, text=True,
                           creationflags=_CREATE_NO_WINDOW)
    except Exception as e:
        return f"Error: {e}"
    return "Copied to the clipboard." if r.returncode == 0 else "Error: couldn't copy."


# ---------------------------------------------------------------------------
# Reminders  (the manager itself is created in main.py and injected here)
# ---------------------------------------------------------------------------
_REMINDERS = None
_NOTES = None


def set_reminders(manager):
    global _REMINDERS
    _REMINDERS = manager


def set_notes(store):
    global _NOTES
    _NOTES = store


def _parse_when(minutes, at):
    """Work out a due datetime from 'in N minutes' or a clock time."""
    now = datetime.now()
    if minutes not in (None, "", 0, "0"):
        try:
            return now + timedelta(minutes=float(minutes))
        except (TypeError, ValueError):
            pass
    if at:
        s = str(at).strip()
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I%p", "%I:%M%p"):
            try:
                t = datetime.strptime(s, fmt)
            except ValueError:
                continue
            due = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            if due <= now:
                due += timedelta(days=1)
            return due
    return None


@tool(
    name="set_reminder",
    description=("Set a reminder. Give either 'minutes' (e.g. 20 for 'in 20 minutes') "
                 "or 'at' (a clock time like '18:30' or '7:00 PM')."),
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "What to remind the user about."},
            "minutes": {"type": "number", "description": "Delay in minutes from now."},
            "at": {"type": "string", "description": "Clock time, e.g. '18:30' or '7:00 PM'."},
        },
        "required": ["message"],
    },
)
def set_reminder(message, minutes=None, at=None):
    if _REMINDERS is None:
        return "Error: reminders aren't available right now."
    due = _parse_when(minutes, at)
    if due is None:
        return "Error: I need a time - tell me how many minutes, or what time of day."
    _REMINDERS.add(message, due)
    return f"Reminder set for {due:%H:%M}: {message}"


@tool(name="list_reminders", description="List pending reminders.")
def list_reminders():
    if _REMINDERS is None:
        return "Error: reminders aren't available right now."
    items = _REMINDERS.list()
    if not items:
        return "No reminders set."
    return "; ".join(
        f"[{r['id']}] {r['message']} at {datetime.fromisoformat(r['due']):%Y-%m-%d %H:%M}"
        for r in items
    )


@tool(
    name="cancel_reminder",
    description="Cancel a reminder by its id.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "string", "description": "Reminder id from list_reminders."}},
        "required": ["id"],
    },
)
def cancel_reminder(id):
    if _REMINDERS is None:
        return "Error: reminders aren't available right now."
    removed = _REMINDERS.cancel(id)
    return "Cancelled." if removed else f"Error: no reminder with id '{id}'."


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
@tool(
    name="add_note",
    description="Save a short note the user can ask for later.",
    parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
)
def add_note(text):
    if _NOTES is None:
        return "Error: notes aren't available right now."
    return _NOTES.add(text)


@tool(name="list_notes", description="List the most recent notes.")
def list_notes():
    if _NOTES is None:
        return "Error: notes aren't available right now."
    items = _NOTES.list()
    if not items:
        return "No notes yet."
    return " | ".join(n["text"] for n in items)


@tool(
    name="search_notes",
    description="Search saved notes for a word or phrase.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)
def search_notes(query):
    if _NOTES is None:
        return "Error: notes aren't available right now."
    hits = _NOTES.search(query)
    if not hits:
        return f"No notes mentioning '{query}'."
    return " | ".join(n["text"] for n in hits)


# ---------------------------------------------------------------------------
# Window control
# ---------------------------------------------------------------------------
@tool(name="list_windows", description="List the titles of currently open windows.")
def list_windows():
    titles = winctl.list_windows()
    return " | ".join(titles) if titles else "No visible windows."


@tool(
    name="focus_window",
    description="Bring an open window to the front by (partial) title.",
    parameters={"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
)
def focus_window(title):
    found = winctl.focus(title)
    return f"Focused '{found}'." if found else f"Error: no window matching '{title}'."


@tool(
    name="minimize_window",
    description="Minimise an open window by (partial) title.",
    parameters={"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
)
def minimize_window(title):
    found = winctl.minimize(title)
    return f"Minimised '{found}'." if found else f"Error: no window matching '{title}'."


@tool(
    name="maximize_window",
    description="Maximise an open window by (partial) title.",
    parameters={"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
)
def maximize_window(title):
    found = winctl.maximize(title)
    return f"Maximised '{found}'." if found else f"Error: no window matching '{title}'."


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
@tool(
    name="list_folder",
    description="List what's inside a folder. Defaults to the Downloads folder.",
    parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": []},
)
def list_folder(path=""):
    raw = (path or "").strip()
    p = DOWNLOADS_DIR if not raw else Path(os.path.expandvars(os.path.expanduser(raw)))
    dirs, files = fileops.list_folder(p)
    if dirs is None:
        return f"Error: there's no folder at {p}."
    return f"{p}: {len(dirs)} folders, {len(files)} files. Files: {', '.join(files) or '(none)'}"


@tool(
    name="organize_downloads",
    description=("Sort the loose files in the Downloads folder into category subfolders "
                 "(Images, Documents, Videos, etc). Can be undone."),
    danger=True,
)
def organize_downloads():
    return fileops.organize_downloads()


@tool(
    name="undo_organize",
    description="Undo the last organize_downloads, moving the files back.",
    danger=True,
)
def undo_organize():
    return fileops.undo_organize()


# ---------------------------------------------------------------------------
# Confirmation for risky actions
# ---------------------------------------------------------------------------
_DANGER_LABELS = {
    "close_application": lambda a: f"Close '{a.get('app_name')}'?",
    "organize_downloads": lambda a: "Move the loose files in Downloads into category folders?",
    "undo_organize": lambda a: "Move the organised files back where they were?",
    "shutdown_pc": lambda a: f"Shut down the PC in {a.get('delay_seconds', 60)} seconds?",
    "restart_pc": lambda a: f"Restart the PC in {a.get('delay_seconds', 60)} seconds?",
    "sleep_pc": lambda a: "Put the PC to sleep?",
    "lock_pc": lambda a: "Lock the PC?",
    "delete_path": lambda a: f"Move '{a.get('path')}' to the Recycle Bin?",
}


def run_confirmed(name, args):
    """Ask the user (native dialog) before running a dangerous tool, then run it."""
    from confirm import ask
    if not isinstance(args, dict):
        args = {}
    label = _DANGER_LABELS.get(name)
    question = label(args) if label else f"Run '{name}'?"
    if not ask(question, "This can't be undone from here, so make sure it's what you want."):
        return "Cancelled by the user."
    return run(name, args)


# ---------------------------------------------------------------------------
# System actions (power, lock, safe delete)
# ---------------------------------------------------------------------------
@tool(
    name="shutdown_pc",
    description=("Shut the computer down after a short delay. Windows shows its own "
                 "countdown, and it can be cancelled."),
    parameters={"type": "object", "properties": {
        "delay_seconds": {"type": "integer",
                          "description": "Seconds before shutdown (default 60, min 10)."}},
        "required": []},
    danger=True,
)
def shutdown_pc(delay_seconds=60):
    return sysactions.shutdown(delay_seconds)


@tool(
    name="restart_pc",
    description="Restart the computer after a short delay. Can be cancelled.",
    parameters={"type": "object", "properties": {
        "delay_seconds": {"type": "integer",
                          "description": "Seconds before restart (default 60, min 10)."}},
        "required": []},
    danger=True,
)
def restart_pc(delay_seconds=60):
    return sysactions.restart(delay_seconds)


@tool(name="cancel_shutdown", description="Cancel a pending shutdown or restart.")
def cancel_shutdown():
    return sysactions.cancel_shutdown()


@tool(name="sleep_pc", description="Put the computer to sleep.", danger=True)
def sleep_pc():
    return sysactions.sleep()


@tool(name="lock_pc", description="Lock the computer.", danger=True)
def lock_pc():
    return sysactions.lock()


@tool(
    name="delete_path",
    description=("Move a file or folder to the Recycle Bin (recoverable - not a permanent "
                 "delete)."),
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "File or folder to remove."}},
        "required": ["path"]},
    danger=True,
)
def delete_path(path):
    return sysactions.delete_to_recycle_bin(path)


# ---------------------------------------------------------------------------
# Web answers
# ---------------------------------------------------------------------------
@tool(
    name="look_up",
    description=("Search the web and read back a short summary of the top results. Use this "
                 "to answer questions that need current information."),
    parameters={"type": "object", "properties": {
        "query": {"type": "string", "description": "What to look up."}},
        "required": ["query"]},
)
def look_up(query):
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return "Error: the search library isn't installed (run: pip install ddgs)."
    try:
        with DDGS() as d:
            results = list(d.text(query, max_results=4))
    except Exception as e:
        return f"Error: the web search failed ({e})."
    if not results:
        return f"No results for '{query}'."
    return " || ".join(
        f"{r.get('title', '')}: {r.get('body', '')}".strip() for r in results
    )


# ---------------------------------------------------------------------------
# Memory (what the assistant knows about the user)
# ---------------------------------------------------------------------------
@tool(name="list_facts", description="List everything the assistant remembers about the user.")
def list_facts():
    if _MEMORY is None:
        return "Error: memory isn't available right now."
    facts = _MEMORY.facts()
    return "; ".join(facts) if facts else "I don't know anything about you yet."


@tool(
    name="forget_fact",
    description="Forget something previously remembered about the user.",
    parameters={"type": "object", "properties": {
        "fact": {"type": "string", "description": "A word or phrase to forget."}},
        "required": ["fact"]},
)
def forget_fact(fact):
    if _MEMORY is None:
        return "Error: memory isn't available right now."
    return _MEMORY.remove_fact(fact)


# ---------------------------------------------------------------------------
# Files: read & search
# ---------------------------------------------------------------------------
_TEXT_EXT = {
    ".txt", ".md", ".py", ".json", ".csv", ".log", ".ini", ".cfg", ".yaml",
    ".yml", ".xml", ".html", ".htm", ".js", ".ts", ".css", ".java", ".c",
    ".cpp", ".cs", ".go", ".rs", ".sh", ".bat", ".ps1", ".sql", ".toml",
}

_SKIP_DIRS = {"appdata", "node_modules", ".git", "__pycache__", "windows",
              "$recycle.bin", "program files", "program files (x86)"}


@tool(
    name="read_file",
    description="Read a file and return its text (txt, md, code, .pdf, .docx).",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "File to read."},
        "max_chars": {"type": "integer", "description": "Max characters (default 6000)."}},
        "required": ["path"]},
)
def read_file(path, max_chars=6000):
    p = Path(os.path.expandvars(os.path.expanduser(str(path).strip())))
    if not p.is_file():
        return f"Error: there's no file at '{path}'."
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                return "Error: reading PDFs needs pypdf (run: pip install pypdf)."
            reader = PdfReader(str(p))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:20])
        elif ext == ".docx":
            try:
                import docx
            except ImportError:
                return "Error: reading .docx needs python-docx (run: pip install python-docx)."
            text = "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
        elif ext in _TEXT_EXT or ext == "":
            text = p.read_text(encoding="utf-8", errors="replace")
        else:
            return f"Error: I can't read '{ext}' files yet."
    except Exception as e:
        return f"Error: couldn't read the file ({e})."
    text = text.strip()
    if not text:
        return f"'{p.name}' looks empty."
    max_chars = int(max_chars or 6000)
    if len(text) > max_chars:
        return f"Contents of {p.name}:\n{text[:max_chars]}\n...(truncated)"
    return f"Contents of {p.name}:\n{text}"


@tool(
    name="find_files",
    description="Find files by name under a folder (default: your home folder).",
    parameters={"type": "object", "properties": {
        "name": {"type": "string", "description": "Part of the file name to match."},
        "root": {"type": "string", "description": "Folder to search (optional)."},
        "limit": {"type": "integer"}},
        "required": ["name"]},
)
def find_files(name, root="", limit=25):
    base = Path(os.path.expandvars(os.path.expanduser(root))) if root else Path.home()
    if not base.is_dir():
        return f"Error: there's no folder at '{base}'."
    needle = str(name).lower()
    limit = int(limit or 25)
    hits = []
    deadline = datetime.now().timestamp() + 15
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIRS]
        for fn in filenames:
            if needle in fn.lower():
                hits.append(str(Path(dirpath) / fn))
                if len(hits) >= limit:
                    return "Found:\n" + "\n".join(hits)
        if datetime.now().timestamp() > deadline:
            break
    return ("Found:\n" + "\n".join(hits)) if hits else f"No files matching '{name}' under {base}."


@tool(
    name="find_in_files",
    description="Search inside text files for a word or phrase.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "Text to look for."},
        "root": {"type": "string", "description": "Folder to search (optional)."},
        "limit": {"type": "integer"}},
        "required": ["text"]},
)
def find_in_files(text, root="", limit=15):
    base = Path(os.path.expandvars(os.path.expanduser(root))) if root else (Path.home() / "Documents")
    if not base.is_dir():
        base = Path.home()
    needle = str(text).lower()
    limit = int(limit or 15)
    hits = []
    deadline = datetime.now().timestamp() + 15
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in _SKIP_DIRS]
        for fn in filenames:
            if Path(fn).suffix.lower() not in _TEXT_EXT:
                continue
            try:
                content = (Path(dirpath) / fn).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if needle in content.lower():
                hits.append(str(Path(dirpath) / fn))
                if len(hits) >= limit:
                    return "Matched:\n" + "\n".join(hits)
        if datetime.now().timestamp() > deadline:
            break
    return ("Matched:\n" + "\n".join(hits)) if hits else f"No files containing '{text}'."


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
@tool(
    name="show_audit",
    description="Show a log of the recent actions the assistant took.",
    parameters={"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []},
)
def show_audit(limit=15):
    rows = audit.recent(int(limit or 15))
    if not rows:
        return "Nothing logged yet."
    return "\n".join(
        f"{r['ts']}  {r['tool']}  {r['args']} -> {r['result'][:80]}" for r in rows
    )


# ---------------------------------------------------------------------------
# Display & windows
# ---------------------------------------------------------------------------
@tool(
    name="snap_window",
    description=("Snap a window to a position: left, right, top, bottom, center, "
                 "maximize, or restore."),
    parameters={"type": "object", "properties": {
        "title": {"type": "string", "description": "Window title (partial ok)."},
        "position": {"type": "string",
                     "description": "left/right/top/bottom/center/maximize/restore"}},
        "required": ["title", "position"]},
)
def snap_window(title, position):
    found = winctl.snap(title, position)
    if found:
        return f"Snapped '{found}' to the {position}."
    return f"Error: couldn't find a window matching '{title}'."


@tool(
    name="set_brightness",
    description="Set the screen brightness to a percentage (0-100).",
    parameters={"type": "object", "properties": {"percent": {"type": "integer"}},
                "required": ["percent"]},
)
def set_brightness(percent):
    return display.set_brightness(percent)


@tool(name="get_brightness", description="Get the current screen brightness percentage.")
def get_brightness():
    value = display.get_brightness()
    if value is None:
        return "This display won't report brightness."
    return f"Brightness is {value}%."


@tool(
    name="set_volume",
    description="Set the system volume to an exact percentage (0-100).",
    parameters={"type": "object", "properties": {"percent": {"type": "integer"}},
                "required": ["percent"]},
)
def set_volume(percent):
    return display.set_volume(percent)


@tool(name="get_volume", description="Get the current system volume percentage.")
def get_volume():
    value = display.get_volume()
    return f"Volume is {value}%." if value is not None else "Couldn't read the volume."


@tool(
    name="get_weather",
    description="Get a short weather line for a city (or the user's current location).",
    parameters={"type": "object", "properties": {
        "city": {"type": "string", "description": "City name (optional)."}}, "required": []},
)
def get_weather(city=""):
    return briefing.get_weather(city)


@tool(
    name="daily_briefing",
    description="A quick briefing: greeting, date/time, weather, reminders, disk space.",
    parameters={"type": "object", "properties": {
        "city": {"type": "string", "description": "City for the weather (optional)."}},
        "required": []},
)
def daily_briefing(city=""):
    return briefing.daily_briefing(city, reminders=_REMINDERS)
