"""
sysactions.py - power / lock actions and safe deletes.

Everything here that changes or removes something is gated by confirm.py through
tools.run_confirmed(). Shutdown and restart additionally use Windows' own delayed
shutdown, which shows the OS countdown and can be aborted with `cancel_shutdown`
(Windows' `shutdown /a`).

Deletes go to the Recycle Bin, never a hard delete.
"""

import ctypes
import os
import subprocess
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000


def _clamp(seconds, lo=10, hi=3600):
    try:
        s = int(float(seconds))
    except (TypeError, ValueError):
        s = 60
    return max(lo, min(hi, s))


def shutdown(delay_seconds=60):
    d = _clamp(delay_seconds)
    r = subprocess.run(["shutdown", "/s", "/t", str(d)],
                       capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW)
    if r.returncode == 0:
        return (f"Shutting down in {d} seconds. Windows is showing its own countdown - "
                f"say 'cancel shutdown' to abort.")
    return f"Error: couldn't schedule the shutdown ({r.stderr.strip() or r.returncode})."


def restart(delay_seconds=60):
    d = _clamp(delay_seconds)
    r = subprocess.run(["shutdown", "/r", "/t", str(d)],
                       capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW)
    if r.returncode == 0:
        return f"Restarting in {d} seconds. Say 'cancel shutdown' to abort."
    return f"Error: couldn't schedule the restart ({r.stderr.strip() or r.returncode})."


def cancel_shutdown():
    r = subprocess.run(["shutdown", "/a"],
                       capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW)
    if r.returncode == 0:
        return "Cancelled the pending shutdown."
    return "There was no shutdown in progress."


def sleep():
    try:
        # SetSuspendState(bHibernate, bForce, bWakeupEventsDisabled)
        ctypes.windll.powrprof.SetSuspendState(False, True, False)
        return "Going to sleep."
    except Exception as e:
        return f"Error: {e}"


def lock():
    try:
        ctypes.windll.user32.LockWorkStation()
        return "Locked the PC."
    except Exception as e:
        return f"Error: {e}"


def delete_to_recycle_bin(path):
    """Move a file or folder to the Recycle Bin (recoverable)."""
    p = Path(os.path.expandvars(os.path.expanduser(str(path).strip())))
    if not p.exists():
        return f"Error: there's nothing at '{path}'."
    method = "DeleteDirectory" if p.is_dir() else "DeleteFile"
    script = (
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        f"[Microsoft.VisualBasic.FileIO.FileSystem]::{method}("
        f"'{p}', 'OnlyErrorDialogs', 'SendToRecycleBin')"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW)
    if r.returncode == 0:
        return f"Moved '{p.name}' to the Recycle Bin."
    return f"Error: couldn't remove it ({(r.stderr or '').strip()[:120]})."
