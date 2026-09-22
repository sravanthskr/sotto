"""
winctl.py - window control through the Win32 API.

No extra dependencies (pure ctypes). Lets the assistant list open windows and
focus, minimise, or maximise one by (partial) title.
"""

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32

SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9

_EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def _windows():
    """Return [(hwnd, title), ...] for visible, titled top-level windows."""
    found = []

    def _cb(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd):
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                _user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title:
                    found.append((hwnd, title))
        return True

    _user32.EnumWindows(_EnumProc(_cb), 0)
    return found


def list_windows():
    """Titles of all visible windows (deduplicated, order preserved)."""
    seen = set()
    titles = []
    for _hwnd, title in _windows():
        if title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


def _find(title):
    """Best-matching (hwnd, title) for a partial title, or (None, None)."""
    q = (title or "").lower().strip()
    if not q:
        return None, None
    best = None  # (score, -len, hwnd, title)
    for hwnd, t in _windows():
        tl = t.lower()
        if q == tl:
            score = 100
        elif tl.startswith(q):
            score = 90
        elif q in tl:
            score = 70
        else:
            continue
        cand = (score, -len(t), hwnd, t)
        if best is None or cand[:2] > best[:2]:
            best = cand
    if best is None:
        return None, None
    return best[2], best[3]


def focus(title):
    hwnd, found = _find(title)
    if hwnd is None:
        return None
    _user32.ShowWindow(hwnd, SW_RESTORE)
    _user32.SetForegroundWindow(hwnd)
    return found


def minimize(title):
    hwnd, found = _find(title)
    if hwnd is None:
        return None
    _user32.ShowWindow(hwnd, SW_MINIMIZE)
    return found


def maximize(title):
    hwnd, found = _find(title)
    if hwnd is None:
        return None
    _user32.ShowWindow(hwnd, SW_MAXIMIZE)
    return found


# ---------------------------------------------------------------------------
# Snapping
# ---------------------------------------------------------------------------
SPI_GETWORKAREA = 0x0030


def _work_area():
    """(left, top, right, bottom) of the usable desktop (excludes the taskbar)."""
    rect = wintypes.RECT()
    ok = _user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    if not ok:
        return 0, 0, _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
    return rect.left, rect.top, rect.right, rect.bottom


def snap(title, position):
    """Snap a window to a screen position.

    position: left / right / top / bottom / center / maximize / restore.
    """
    hwnd, found = _find(title)
    if hwnd is None:
        return None
    pos = (position or "").lower().strip()
    left, top, right, bottom = _work_area()
    w, h = right - left, bottom - top

    if pos in ("maximize", "maximise", "max", "full"):
        _user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return found
    if pos in ("restore", "normal"):
        _user32.ShowWindow(hwnd, SW_RESTORE)
        return found
    if pos in ("left", "left half"):
        geom = (left, top, w // 2, h)
    elif pos in ("right", "right half"):
        geom = (left + w // 2, top, w - w // 2, h)
    elif pos in ("top", "top half"):
        geom = (left, top, w, h // 2)
    elif pos in ("bottom", "bottom half"):
        geom = (left, top + h // 2, w, h - h // 2)
    elif pos in ("center", "centre", "middle"):
        cw, ch = int(w * 0.6), int(h * 0.7)
        geom = (left + (w - cw) // 2, top + (h - ch) // 2, cw, ch)
    else:
        return None

    _user32.ShowWindow(hwnd, SW_RESTORE)
    _user32.MoveWindow(hwnd, geom[0], geom[1], geom[2], geom[3], True)
    return found
