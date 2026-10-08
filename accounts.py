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


def clear_oauth(provider):
    data = load()
    (data.get("oauth") or {}).pop(provider, None)
    save(data)


def clear_ics():
    data = load()
    data.pop("calendar_ics", None)
    save(data)


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


def set_provider_key(env_name, key):
    """Store (or clear) a BYOK provider key, DPAPI-encrypted. Never plain text."""
    k = str(env_name or "").strip()
    if not k:
        return False
    data = load()
    provs = dict(data.get("providers") or {})
    if str(key or "").strip():
        provs[k] = enc(str(key).strip())
    else:
        provs.pop(k, None)
    data["providers"] = provs
    save(data)
    return True


def get_provider_keys():
    """{env_name: True/False} - booleans only; keys never leave the vault."""
    data = load()
    provs = data.get("providers") or {}
    out = {}
    for k, v in provs.items():
        try:
            out[k] = bool(str(dec(v) or "").strip())
        except Exception:
            out[k] = False
    return out


def apply_provider_keys():
    """Load stored BYOK keys into the process environment. Returns count."""
    data = load()
    provs = data.get("providers") or {}
    n = 0
    for k, v in provs.items():
        try:
            text = str(dec(v) or "").strip()
            if text:
                os.environ[str(k)] = text
                n += 1
        except Exception:
            continue
    return n
