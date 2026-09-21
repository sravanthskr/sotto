"""
tools.py - the hands.

Every capability the assistant can actually perform lives here, registered with
@tool(...). The registry is what gets sent to the model as callable schema, and what
main.py dispatches to. Adding a new ability is: write the function, decorate it, done.

Security model: the cloud model NEVER runs anything itself. It can only ask for one of
these named tools with JSON arguments. Everything is validated and executed locally.
"""

import os
import re
import shutil
import subprocess
import webbrowser
import winreg
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from config import SCREENSHOT_DIR

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
    """Execute a registered tool safely. Returns a short string result."""
    entry = REGISTRY.get(name)
    if not entry:
        return f"Error: unknown tool '{name}'."
    if not isinstance(args, dict):
        args = {}
    try:
        return str(entry["func"](**args))
    except TypeError as e:
        return f"Error: bad arguments for {name}: {e}"
    except Exception as e:
        return f"Error: {name} failed: {e}"


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


def _launch(target):
    try:
        os.startfile(target)
        return True, ""
    except Exception as e1:
        try:
            subprocess.Popen(f'start "" "{target}"', shell=True)
            return True, ""
        except Exception:
            return False, str(e1)


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
