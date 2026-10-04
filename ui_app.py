"""
ui_app.py - launches the desktop app (pywebview).

    .\\run.bat ui

Main Sotto window is a normal desktop window.
When overlay is enabled in settings, a separate small tkinter pill process
floats on top whenever the main window loses focus.  The pill is a completely
independent process — it cannot crash or block the main app.
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import webview

from ui_bridge import Api
from overlay_win import create_overlay_window, start_overlay_controller

INDEX   = Path(__file__).parent / "ui" / "index.html"
STORAGE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RealAssistant" / "webview"
APP_ID  = "RealAssistant.Sotto"
IPC_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RealAssistant"

STATE_FILE = IPC_DIR / "pill_state.json"
SIG_FILE   = IPC_DIR / "pill_signal.json"


def _resource(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / "assets" / "icon" / name


def _apply_window_icon(window):
    def _set():
        try:
            ico = str(_resource("sotto.ico"))
            if not Path(ico).exists():
                return
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, window.title)
            if not hwnd:
                return
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != os.getpid():
                return
            LR_LOADFROMFILE = 0x00000010
            WM_SETICON = 0x0080
            big   = user32.LoadImageW(None, ico, 1, 0,  0,  LR_LOADFROMFILE | 0x40)
            small = user32.LoadImageW(None, ico, 1, 16, 16, LR_LOADFROMFILE)
            if big:   user32.SendMessageW(hwnd, WM_SETICON, 1, big)
            if small: user32.SendMessageW(hwnd, WM_SETICON, 0, small)
        except Exception as e:
            print(f"[icon] {e}")
    try:
        window.events.shown += _set
    except Exception:
        _set()


def _hwnd(window):
    try:
        user32 = ctypes.windll.user32
        hwnd   = user32.FindWindowW(None, window.title)
        if hwnd:
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == os.getpid():
                return int(hwnd)
    except Exception:
        pass
    return 0


def _set_foreground(hwnd):
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass










def main():
    IPC_DIR.mkdir(parents=True, exist_ok=True)
    # Clear stale IPC files
    for f in (STATE_FILE, SIG_FILE):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass

    api = Api()

    window = webview.create_window(
        "Sotto",
        str(INDEX),
        js_api=api,
        width=1180,
        height=780,
        min_size=(760, 580),
        background_color="#0a0a0b",
    )
    _apply_window_icon(window)

    api.set_window(window)
    try:
        api.start()
    except Exception:
        pass

    # Floating overlay: a small always-on-top pill (ui/overlay.html)
    overlay = create_overlay_window(api)
    api.set_overlay_window(overlay, window)
    try:
        window.events.closing += lambda: overlay.destroy()
    except Exception:
        pass
    start_overlay_controller(api, overlay, window)

    webview.start(private_mode=False, storage_path=str(STORAGE))

    # App closed.


if __name__ == "__main__":
    main()
