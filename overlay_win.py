"""
overlay_win.py - the floating Sotto overlay window.

A small frameless, always-on-top pill that appears over every application
while Sotto is listening, thinking, working or speaking - then fades away
when the interaction is done. It renders ui/overlay.html, so it matches the
main app design language exactly.

No taskbar button, no focus stealing. Tap the orb to talk, the arrow to
bring the main window back, drag the pill along the top.
"""

import ctypes
import os
import threading
import time
from pathlib import Path

import webview

OVERLAY = Path(__file__).parent / "ui" / "overlay.html"
WIN_W, WIN_H = 452, 60
RADIUS = 28
TOP_MARGIN = 12


def _hwnd_by_title(title):
    try:
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, title)
        if not hwnd:
            return 0
        pid = ctypes.c_ulong(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != os.getpid():
            return 0
        return int(hwnd)
    except Exception:
        return 0


def _scale_for(hwnd):
    try:
        return max(1.0, ctypes.windll.user32.GetDpiForWindow(hwnd) / 96.0)
    except Exception:
        return 1.0


def _position(win, hwnd):
    try:
        u = ctypes.windll.user32
        sw = u.GetSystemMetrics(0)
        s = _scale_for(hwnd)
        win.move(int((sw / s - WIN_W) / 2), TOP_MARGIN)
    except Exception:
        pass


class _RC(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


class _PT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _apply_region(hwnd):
    """Clip the window to the webview client area, rounded into a pill.

    Everything outside the webview (window borders / padding) is cut away,
    so no frame can ever show around the capsule. Physical pixels.
    """
    try:
        u = ctypes.windll.user32
        s = _scale_for(hwnd)
        cl = _RC()
        if not u.GetClientRect(hwnd, ctypes.byref(cl)) or (cl.r - cl.l) <= 0:
            cl.l, cl.t = 0, 0
            cl.r, cl.b = int(WIN_W * s), int(WIN_H * s)
        # client origin in window coordinates
        pt = _PT(0, 0)
        u.ClientToScreen(hwnd, ctypes.byref(pt))
        wr = _RC()
        u.GetWindowRect(hwnd, ctypes.byref(wr))
        ox = pt.x - wr.l
        oy = pt.y - wr.t
        w = cl.r - cl.l
        h = cl.b - cl.t
        r = int(min(RADIUS * s * 2, h))
        gdi = ctypes.windll.gdi32
        rgn = gdi.CreateRoundRectRgn(ox, oy, ox + w + 1, oy + h + 1, r, r)
        u.SetWindowRgn(hwnd, rgn, True)
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020 | 0x0004)
    except Exception:
        pass


def _make_toolwindow(hwnd):
    """Remove from the taskbar and Alt-Tab (WS_EX_TOOLWINDOW)."""
    try:
        u = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
    except Exception:
        pass


def _setup_overlay(win):
    """Size + shape + position + taskbar-hide. Safe to call more than once."""
    hwnd = _hwnd_by_title("SottoOverlay")
    if not hwnd:
        return False
    try:
        win.resize(WIN_W, WIN_H)
    except Exception:
        pass
    _make_toolwindow(hwnd)
    _apply_region(hwnd)
    _position(win, hwnd)
    return True


def create_overlay_window(api):
    win = webview.create_window(
        "SottoOverlay",
        str(OVERLAY),
        js_api=api,
        width=WIN_W,
        height=WIN_H,
        frameless=True,
        easy_drag=False,
        draggable=True,
        resizable=False,
        on_top=True,
        transparent=False,
        shadow=False,
        focus=False,
        hidden=True,
        min_size=(90, 40),
        background_color="#14161A",
    )
    try:
        win.events.shown += lambda: _setup_overlay(win)
    except Exception:
        pass
    return win


def _main_foreground():
    try:
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, "Sotto")
        if not hwnd:
            return False
        pid = ctypes.c_ulong(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != os.getpid():
            return False
        if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return False
        return u.GetForegroundWindow() == hwnd
    except Exception:
        return False


def _show_noactivate(win):
    try:
        u = ctypes.windll.user32
        prev = u.GetForegroundWindow()
        win.show()
        cur = u.GetForegroundWindow()
        if cur and prev and cur != prev:
            u.SetForegroundWindow(prev)   # keep focus where the user was
    except Exception:
        try:
            win.show()
        except Exception:
            pass


def _fade_then_hide(win):
    try:
        win.evaluate_js("document.body.classList.add('bye')")
    except Exception:
        pass
    time.sleep(0.24)
    try:
        win.hide()
    except Exception:
        pass
    try:
        win.evaluate_js("document.body.classList.remove('bye')")
    except Exception:
        pass


def start_overlay_controller(api, overlay_win, main_win):
    """Watch the real assistant snapshot; show/hide the pill accordingly."""
    from ui_bridge import _log

    def setup_when_ready():
        for _ in range(80):
            if _setup_overlay(overlay_win):
                time.sleep(0.35)
                _setup_overlay(overlay_win)   # re-normalize after resize settles
                _log("overlay: window ready (shaped + positioned)")
                return
            time.sleep(0.25)

    threading.Thread(target=setup_when_ready, daemon=True).start()

    def run():
        visible = False
        while True:
            time.sleep(0.16)
            try:
                if api.overlay_expand_pending():
                    if visible:
                        _fade_then_hide(overlay_win)
                        visible = False
                    try:
                        main_win.restore()
                        main_win.show()
                        u = ctypes.windll.user32
                        hwnd = _hwnd_by_title("Sotto")
                        if hwnd:
                            u.keybd_event(0x12, 0, 0, 0)
                            u.keybd_event(0x12, 0, 2, 0)
                            u.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                    _log("overlay: expand -> main window restored")
                    continue

                if not api.overlay_on():
                    if visible:
                        _fade_then_hide(overlay_win)
                        visible = False
                    continue

                snap = api.overlay_state_raw()
                want = bool(snap.get("visible"))
                if want and _main_foreground():
                    want = False   # user is in the main window; pill is redundant
                if want and not visible:
                    _show_noactivate(overlay_win)
                    visible = True
                    _log("overlay: pill shown")
                elif not want and visible:
                    _fade_then_hide(overlay_win)
                    visible = False
                    _log("overlay: pill hidden")
            except Exception as e:
                _log(f"overlay controller error: {type(e).__name__}: {e}")
                time.sleep(1.5)

    threading.Thread(target=run, daemon=True).start()
