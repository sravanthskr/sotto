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
PILL_BOTTOM_MARGIN = 56

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


_ALWAYS_CACHE = {"t": 0.0, "v": False}


def _always_visible():
    """True when the user wants the pill present whenever Sotto isn't focused."""
    now = time.time()
    if now - _ALWAYS_CACHE["t"] < 3.0:
        return _ALWAYS_CACHE["v"]
    v = False
    try:
        from config import load_settings
        v = bool(load_settings().get("overlay_always_visible", False))
    except Exception:
        v = False
    _ALWAYS_CACHE["t"] = now
    _ALWAYS_CACHE["v"] = v
    return v


def _main_state():
    """focused | visible | minimized | hidden | none"""
    h = _main_hwnd()
    if not h:
        return "none"
    try:
        u = ctypes.windll.user32
        if not u.IsWindowVisible(h):
            return "hidden"
        if u.IsIconic(h):
            return "minimized"
        return "focused" if u.GetForegroundWindow() == h else "visible"
    except Exception:
        return "visible"


def _scale_for(hwnd):
    try:
        return max(1.0, ctypes.windll.user32.GetDpiForWindow(hwnd) / 96.0)
    except Exception:
        return 1.0


def _pill_xy(hwnd):
    """Where the pill should sit (logical coords), from settings.

    overlay_pill_pos: center (default), top_left / top_right / bottom_left /
    bottom_right / bottom_center, or "remember" (last dragged position).
    """
    from config import load_settings
    st = load_settings()
    pos = str(st.get("overlay_pill_pos") or "center").strip().lower()
    s = _scale_for(hwnd) or 1.0
    u = ctypes.windll.user32
    vx = u.GetSystemMetrics(76) / s
    vy = u.GetSystemMetrics(77) / s
    vw = u.GetSystemMetrics(78) / s
    vh = u.GetSystemMetrics(79) / s
    m = TOP_MARGIN
    x = y = None
    if pos == "remember":
        try:
            x = float(st.get("overlay_pill_x"))
            y = float(st.get("overlay_pill_y"))
        except Exception:
            x = y = None
    if x is None or y is None:
        if pos == "top_left":
            x, y = vx + m, vy + m
        elif pos == "top_right":
            x, y = vx + vw - WIN_W - m, vy + m
        elif pos == "bottom_left":
            x, y = vx + m, vy + vh - WIN_H - PILL_BOTTOM_MARGIN
        elif pos == "bottom_right":
            x, y = vx + vw - WIN_W - m, vy + vh - WIN_H - PILL_BOTTOM_MARGIN
        elif pos == "bottom_center":
            x, y = vx + (vw - WIN_W) / 2, vy + vh - WIN_H - PILL_BOTTOM_MARGIN
        else:  # center (default): top centre, exactly as before
            x, y = vx + (vw - WIN_W) / 2, vy + m
    x = min(max(x, vx + 4), vx + vw - WIN_W - 4)
    y = min(max(y, vy + 4), vy + vh - WIN_H - 4)
    return int(x), int(y)


_WINXY = {"err_logged": False}


def _win_xy(win):
    """Current window top-left in the same logical units win.move() takes."""
    try:
        return int(win.x), int(win.y)
    except Exception as e:
        if not _WINXY["err_logged"]:
            _WINXY["err_logged"] = True
            try:
                from ui_bridge import _log
                _log(f"overlay: win.x unreadable ({type(e).__name__}: {e}); using Win32 fallback")
            except Exception:
                pass
    try:
        h = _overlay_hwnd()
        r = _RC()
        if h and ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r)):
            s = _scale_for(h) or 1.0
            return int(round(r.l / s)), int(round(r.t / s))
    except Exception:
        pass
    return None


def _save_pill_pos(x, y):
    """Persist a dragged position; the pill now always returns here."""
    try:
        from config import load_settings as _lsp, save_setting as _ssp
        st = _lsp()
        x, y = int(x), int(y)
        if (str(st.get("overlay_pill_pos")) == "remember"
                and st.get("overlay_pill_x") == x and st.get("overlay_pill_y") == y):
            return False
        _ssp("overlay_pill_pos", "remember")
        _ssp("overlay_pill_x", x)
        _ssp("overlay_pill_y", y)
        return True
    except Exception:
        return False


def _position(win, hwnd):
    try:
        x, y = _pill_xy(hwnd)
        win.move(x, y)
    except Exception:
        pass


class _MARGINS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int),
                ("t", ctypes.c_int), ("b", ctypes.c_int)]


def _apply_dwm_glass(hwnd):
    """Extend DWM glass over the entire window so the compositor background
    is used instead of the WinForms Form.BackColor.  Combined with the
    WebView2 transparent background this gives true per-pixel see-through."""
    try:
        m = _MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))
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


def _round_region(hwnd):
    try:
        u = ctypes.windll.user32
        g = ctypes.windll.gdi32
        s = _scale_for(hwnd)
        # the pill now fills the whole window, so clip the full rect to a
        # stadium (radius = half the height) - only the curved pill shows and
        # there is no square backdrop left to render as a black border
        w = int(round(WIN_W * s)) + 1
        h = int(round(WIN_H * s)) + 1
        r = int(round((WIN_H / 2) * s))
        g.CreateRoundRectRgn.restype = ctypes.c_void_p   # GDI handles are 64-bit
        # SetWindowRgn truncates the 64-bit HRGN unless we declare the arg types
        u.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        rgn = g.CreateRoundRectRgn(0, 0, w, h, r, r)
        if rgn:
            u.SetWindowRgn(hwnd, rgn, True)
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
    _apply_dwm_glass(hwnd)
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
        str(OVERLAY) + "?v=" + str(int(OVERLAY.stat().st_mtime)),
        js_api=api,
        width=WIN_W,
        height=WIN_H,
        frameless=True,
        easy_drag=False,
        draggable=True,
        resizable=False,
        on_top=True,
        transparent=True,
        shadow=False,
        focus=False,
        hidden=True,
        min_size=(90, 40),
        background_color="#FFFFFF",
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
    time.sleep(0.16)
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

    Position: the pill can be dragged anywhere; the new spot is remembered
    (settings overlay_pill_pos="remember") so it always comes back there.
    """
    from ui_bridge import _log

    pos_state = {"last": None, "dirty_at": 0.0, "target": None, "no_read_logged": False}

    def save_pos(cur, why):
        if _save_pill_pos(cur[0], cur[1]):
            pos_state["target"] = cur
            _log(f"overlay: pill position saved ({cur[0]},{cur[1]}) ({why})")
            try:
                api._push({"type": "settings_changed", "key": "overlay_pill_pos",
                           "value": "remember"})
            except Exception:
                pass

    def remember_if_moved(why):
        try:
            cur = _win_xy(overlay_win)
            tgt = pos_state["target"]
            if not cur or not tgt:
                return
            if abs(cur[0] - tgt[0]) <= 5 and abs(cur[1] - tgt[1]) <= 5:
                return
            save_pos(cur, why)
        except Exception:
            pass

    def setup_when_ready():
        for _ in range(80):
            if _setup_overlay(overlay_win, hide_after=False):
                try:
                    _STATE["loaded"] = False
                    overlay_win.load_url(str(OVERLAY) + '?v=' + str(int(OVERLAY.stat().st_mtime)))
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
        suppress_until = 0.0
        t0 = time.time()
        while True:
            time.sleep(0.16)
            try:
                # expand clicked on the pill -> bring the main window back
                if api.overlay_expand_pending():
                    if visible:
                        remember_if_moved("expand")
                        _fade_then_hide(overlay_win)
                        visible = False
                    try:
                        _mh = _main_hwnd()
                        if _mh and ctypes.windll.user32.IsIconic(_mh):
                            main_win.restore()   # un-minimise only; never un-maximise
                        main_win.show()
                        u = ctypes.windll.user32
                        hwnd = _main_hwnd()
                        if hwnd:
                            u.keybd_event(0x12, 0, 0, 0)
                            u.keybd_event(0x12, 0, 2, 0)
                            u.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                    suppress_until = time.time() + 2.0
                    confirmed = "focused"
                    last_ms = "focused"
                    stable = 3
                    _log("overlay: expand -> main window restored")
                    continue

                if not api.overlay_on():
                    if visible:
                        remember_if_moved("overlay-off")
                        _fade_then_hide(overlay_win)
                        visible = False
                    continue

                if not _STATE["loaded"]:
                    continue

                ms = _main_state()
                # smooth presence: appear only after the switch has settled,
                # hide a little quicker; separate tick thresholds
                if ms == last_ms:
                    stable += 1
                else:
                    last_ms = ms
                    stable = 1
                if ms == "focused":
                    if stable >= 1:
                        confirmed = ms
                elif stable >= 7:
                    confirmed = ms
                ms = confirmed
                grace = (time.time() - t0) < 8.0
                snap = api.overlay_state_raw()
                snap_active = bool(snap.get("visible"))
                if ms == "focused":
                    seen_focus = True
                    want = False
                elif ms == "visible":
                    # the app is still on screen: speak up when the
                    # assistant is doing something, or when the user asked
                    # for the pill to always be available
                    want = snap_active or _always_visible()
                elif ms in ("minimized", "hidden"):
                    # out of sight: quiet presence + live state
                    want = bool(seen_focus)
                else:  # none - app window is gone (closing)
                    want = False
                if want and grace:
                    want = False
                if want and time.time() < suppress_until:
                    want = False

                if want and not visible:
                    # position may have changed in Settings: apply before each show
                    try:
                        h0 = _overlay_hwnd()
                        if h0:
                            _position(overlay_win, h0)
                            pos_state["target"] = _pill_xy(h0)
                    except Exception:
                        pos_state["target"] = None
                    _show_noactivate(overlay_win)
                    visible = True
                    pos_state["last"] = None
                    pos_state["dirty_at"] = 0.0
                    _log("overlay: pill shown")
                elif not want and visible:
                    remember_if_moved("hide")
                    _fade_then_hide(overlay_win)
                    visible = False
                    suppress_until = time.time() + 1.2
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

                # --- the pill stays where the user drags it ---------------
                if visible:
                    cur = _win_xy(overlay_win)
                    if not cur and not pos_state.get("no_read_logged"):
                        pos_state["no_read_logged"] = True
                        _log("overlay: pill position unreadable this tick (retrying)")
                    if cur:
                        if not pos_state["target"]:
                            pos_state["target"] = cur
                        tgt = pos_state["target"]
                        if abs(cur[0] - tgt[0]) <= 5 and abs(cur[1] - tgt[1]) <= 5:
                            pos_state["last"] = cur
                            pos_state["dirty_at"] = 0.0
                        elif cur != pos_state["last"]:
                            if pos_state["last"]:
                                _log(f"overlay: pill moved to ({cur[0]},{cur[1]}) while visible")
                            pos_state["last"] = cur
                            pos_state["dirty_at"] = time.time()
                        elif pos_state["dirty_at"] and (time.time() - pos_state["dirty_at"]) >= 1.3:
                            pos_state["dirty_at"] = 0.0
                            save_pos(cur, "drag")
            except Exception as e:
                _log(f"overlay controller error: {type(e).__name__}: {e}")
                time.sleep(1.5)

    threading.Thread(target=run, daemon=True).start()
