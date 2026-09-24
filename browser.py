"""
browser.py - Chrome profile awareness and launching.

Lets the assistant open Chrome with a specific account/profile, e.g.
"open Chrome with my work account".
"""

import json
import os
import subprocess
from pathlib import Path

_DETACHED = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_GROUP | NO_WINDOW


def _user_data_dir():
    return Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"


def list_chrome_profiles():
    """Return [{dir, name, email}, ...] for every Chrome profile, or []."""
    state_file = _user_data_dir() / "Local State"
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    info = (data.get("profile") or {}).get("info_cache") or {}
    profiles = []
    for dirname, meta in info.items():
        profiles.append({
            "dir": dirname,
            "name": (meta.get("name") or dirname),
            "email": (meta.get("user_name") or ""),
        })
    return sorted(profiles, key=lambda p: p["name"].lower())


def _find_chrome_exe():
    candidates = [
        Path(os.getenv("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def _match(name):
    q = (name or "").lower().strip()
    if not q:
        return None
    profiles = list_chrome_profiles()
    for p in profiles:
        if q in (p["name"].lower(), p["dir"].lower(), p["email"].lower()):
            return p
    for p in profiles:
        if q in p["name"].lower() or q in p["email"].lower() or q in p["dir"].lower():
            return p
    return None


def open_chrome_profile(name):
    profiles = list_chrome_profiles()
    if not profiles:
        return ("Error: couldn't read your Chrome profiles "
                "(is Chrome installed and set up?).")
    match = _match(name)
    if match is None:
        names = ", ".join(p["name"] for p in profiles)
        return f"No Chrome profile matching '{name}'. Available: {names}"
    exe = _find_chrome_exe()
    if not exe:
        return "Error: couldn't locate chrome.exe."
    try:
        subprocess.Popen([exe, f"--profile-directory={match['dir']}"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=_DETACHED, close_fds=True)
        return f"Opened Chrome with the '{match['name']}' profile."
    except Exception as e:
        return f"Error: couldn't open Chrome ({e})."
