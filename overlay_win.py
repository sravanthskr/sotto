"""
overlay_win.py - the floating Sotto overlay window.

A small frameless, always-on-top pill. It is hidden while you are inside
Sotto; the moment you minimise Sotto or switch to another app (or the
desktop), it appears and keeps showing what Sotto is doing - listening,
thinking, working, speaking, done, or just quietly ready. It renders
ui/overlay.html so it matches the app design language exactly.

No taskbar button, no focus stealing. Tap the orb to talk, the arrow to
bring the main window back.
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

_STATE = {"loaded": False}   # overlay page finished loading


class _RC(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


class _PT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _top_windows():
    """All top-level windows of this process: [(hwnd, title), ...]"""
    out = []
    try:
        u = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(h, l):
            pid = ctypes.c_ulong(0)
            u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value == os.getpid():
                ln = u.GetWindowTextLengthW(h)
                buf = ctypes.create_unicode_buffer(int(ln) + 2)
                u.GetWindowTextW(h, buf, int(ln) + 2)
                out.append((int(h), buf.value))
            return True

        u.EnumWindows(WNDENUMPROC(cb), None)
    except Exception:
        pass
    return out


_MAIN = {"h": 0}
_OVL = {"h": 0}


def _overlay_hwnd():
    h = _OVL["h"]
    if h:
        try:
            if ctypes.windll.user32.IsWindow(h):
                return h
        except Exception:
            pass
    h = 0
    for hh, t in _top_windows():
        if t.startswith("SottoOverlay"):
            h = hh
            break
    _OVL["h"] = h
    return h


def _main_hwnd():
    h = _MAIN["h"]
    if h:
        try:
            if ctypes.windll.user32.IsWindow(h):
                return h
        except Exception:
            pass
    h = 0
    for hh, t in _top_windows():
        if t.startswith("Sotto") and not t.startswith("SottoOverlay"):
            h = hh
            break
    _MAIN["h"] = h
    return h


def _main_state():
    """none | focused | unfocused"""
    h = _main_hwnd()
    if not h:
        return "none"
    try:
        u = ctypes.windll.user32
        if not u.IsWindowVisible(h) or u.IsIconic(h):
            return "unfocused"
        return "focused" if u.GetForegroundWindow() == h else "unfocused"
    except Exception:
        return "unfocused"


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


def _apply_region(hwnd):
    """Clip the window to the webview client area, rounded into a pill."""
    try:
        u = ctypes.windll.user32
        s = _scale_for(hwnd)
        cl = _RC()
        if not u.GetClientRect(hwnd, ctypes.byref(cl)) or (cl.r - cl.l) <= 0:
            cl.l, cl.t = 0, 0
            cl.r, cl.b = int(WIN_W * s), int(WIN_H * s)
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


def _setup_overlay(win, hide_after=False):
    """Size + shape + position + taskbar-hide for the pill window."""
    hwnd = _overlay_hwnd()
    if not hwnd:
        return False
    try:
        win.resize(WIN_W, WIN_H)
    except Exception:
        pass
    _make_toolwindow(hwnd)
    _apply_region(hwnd)
    _position(win, hwnd)
    if hide_after:
        try:
            win.hide()
        except Exception:
            pass
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
        win.events.loaded += lambda: _STATE.update(loaded=True)
    except Exception:
        pass
    return win


def _show_noactivate(win):
    try:
        u = ctypes.windll.user32
        prev = u.GetForegroundWindow()
        win.show()
        cur = u.GetForegroundWindow()
        if cur and prev and cur != prev:
            u.SetForegroundWindow(prev)
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
    """Presence logic:

    - in the Sotto app (focused)         -> pill hidden
    - minimised / switched to other app  -> pill visible (shows live state,
      or a quiet 'Sotto' presence when idle)
    - app not launched yet / closing     -> pill hidden
    """
    from ui_bridge import _log

    def setup_when_ready():
        for _ in range(80):
            if _setup_overlay(overlay_win, hide_after=False):
                try:
                    _STATE["loaded"] = False
                    overlay_win.load_url(str(OVERLAY))
                except Exception:
                    pass
                time.sleep(0.45)
                _setup_overlay(overlay_win, hide_after=True)
                _log("overlay: window ready (shaped + positioned)")
                return
            time.sleep(0.25)

    threading.Thread(target=setup_when_ready, daemon=True).start()

    def run():
        visible = False
        seen_focus = False
        last_ms = None
        confirmed = None
        stable = 0
        while True:
            time.sleep(0.16)
            try:
                # expand clicked on the pill -> bring the main window back
                if api.overlay_expand_pending():
                    if visible:
                        _fade_then_hide(overlay_win)
                        visible = False
                    try:
                        main_win.restore()
                        main_win.show()
                        u = ctypes.windll.user32
                        hwnd = _main_hwnd()
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

                if not _STATE["loaded"]:
                    continue

                ms = _main_state()
                # debounce: only trust a state that held for ~0.5s
                if ms == last_ms:
                    stable += 1
                else:
                    last_ms = ms
                    stable = 1
                if stable >= 3:
                    confirmed = ms
                ms = confirmed
                if ms == "focused":
                    seen_focus = True
                    want = False
                elif ms == "unfocused":
                    want = True if seen_focus else False
                else:  # none - app window is gone (closing)
                    want = False

                if want and not visible:
                    _show_noactivate(overlay_win)
                    visible = True
                    _log("overlay: pill shown")
                elif not want and visible:
                    _fade_then_hide(overlay_win)
                    visible = False
                    _log("overlay: pill hidden")
                elif not want and not visible:
                    # resync: make sure a stray visible window can never stick
                    h = _overlay_hwnd()
                    if h and ctypes.windll.user32.IsWindowVisible(h):
                        try:
                            overlay_win.hide()
                        except Exception:
                            pass
                        _log("overlay: pill hidden (resync)")
            except Exception as e:
                _log(f"overlay controller error: {type(e).__name__}: {e}")
                time.sleep(1.5)

    threading.Thread(target=run, daemon=True).start()
