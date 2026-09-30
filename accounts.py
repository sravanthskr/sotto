"""accounts.py - connected accounts + secret storage.

Secrets (app passwords, tokens) are encrypted with Windows DPAPI through the
built-in PowerShell cmdlets (user-scoped) - they never sit in plain text on disk.
"""

import json
import os
import subprocess
import time
from pathlib import Path

DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RealAssistant"
ACCOUNTS_FILE = DATA / "accounts.json"
_CREATE_NO_WINDOW = 0x08000000


def _ps(script: str, stdin_text: str, timeout: int = 20) -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        input=stdin_text, capture_output=True, text=True, timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )
    if r.returncode != 0:
        raise OSError((r.stderr or "powershell failed").strip()[:200])
    return r.stdout.strip()


def enc(text: str) -> str:
    script = ("$s = [Console]::In.ReadToEnd(); "
              "$sec = ConvertTo-SecureString -String $s -AsPlainText -Force; "
              "ConvertFrom-SecureString $sec")
    out = _ps(script, text)
    if not out:
        raise OSError("encryption returned nothing")
    return out


def dec(token: str) -> str:
    script = ("$h = [Console]::In.ReadToEnd().Trim(); "
              "$sec = ConvertTo-SecureString -String $h; "
              "$cred = New-Object System.Management.Automation.PSCredential('x', $sec); "
              "$cred.GetNetworkCredential().Password")
    return _ps(script, token)


# ---------------- store ----------------
def load() -> dict:
    try:
        return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(data: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------- email account ----------------
def get_email_account():
    return load().get("email")


def set_email_account(provider, address, password):
    data = load()
    data["email"] = {"provider": provider, "address": address.lower(),
                     "secret": enc(password), "since": time.time()}
    save(data)
    return data["email"]


def email_password(acc=None):
    acc = acc or get_email_account()
    try:
        return dec(acc["secret"]) if acc else None
    except Exception:
        return None


def clear_email_account():
    data = load()
    data.pop("email", None)
    save(data)


# ---------------- calendar ----------------
def set_ics(url):
    data = load()
    data["calendar_ics"] = {"url": url, "since": time.time()}
    save(data)
    return data["calendar_ics"]


def get_ics():
    return load().get("calendar_ics")


# ---------------- oauth ----------------
def set_oauth(provider, payload):
    data = load()
    data.setdefault("oauth", {})[provider] = payload
    save(data)


def get_oauth(provider):
    return load().get("oauth", {}).get(provider)


# ---------------- status ----------------
def status_lines():
    data = load()
    out = []
    e = data.get("email")
    if e:
        out.append(f"email: {e['address']}")
    if data.get("calendar_ics"):
        out.append("calendar: linked (read-only link)")
    for p, v in (data.get("oauth") or {}).items():
        out.append(f"{p}: {v.get('email') or 'connected'}")
    return out or ["nothing connected yet"]
