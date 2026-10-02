"""
onboarding.py - First-run setup wizard for Sotto.

Shows automatically on first launch or when no API key is configured.
Walks the user through:
  1. Welcome
  2. AI key (BYOK) - provider picker + verify
  3. Permissions - plain-English explanation
  4. Mic test
  5. Done
"""

import os
import threading
import urllib.request
import urllib.error
from pathlib import Path

from PySide6.QtCore import QEventLoop, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient,
                            QPainter, QPen, QRadialGradient)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from config import DATA_DIR

# ── palette (matches app_qt.py)
_BG1    = "#0F0F1A"
_BG2    = "#0A0A12"
_VIOLET = "#8B5CF6"
_DEEP_V = "#6D28D9"
_BLUE   = "#3B82F6"
_CYAN   = "#22D3EE"
_PINK   = "#EC4899"
_TEXT   = "#FAFAFA"
_MUTED  = "#A1A1AA"
_BORDER = "rgba(255,255,255,0.10)"
_GREEN  = "#34D399"
_AMBER  = "#F59E0B"
_RED    = "#F87171"

_GLASS = (
    "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
    " stop:0 rgba(255,255,255,0.07), stop:0.5 rgba(24,24,36,0.80),"
    " stop:1 rgba(18,18,28,0.92));"
    f" border:1px solid {_BORDER}; border-radius:18px;"
)
_BTN_PRI = (
    f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
    f"stop:0 {_DEEP_V},stop:1 {_BLUE});"
    f"color:#fff;border:0;border-radius:14px;"
    f"padding:12px 28px;font-size:14px;font-weight:600;}}"
    f"QPushButton:hover{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
    f"stop:0 {_VIOLET},stop:1 {_CYAN});}}"
    f"QPushButton:disabled{{background:rgba(80,80,100,0.4);color:#666;}}"
)
_BTN_GHOST = (
    f"QPushButton{{background:rgba(255,255,255,0.05);color:{_MUTED};"
    f"border:1px solid {_BORDER};border-radius:14px;padding:12px 24px;font-size:13px;}}"
    f"QPushButton:hover{{background:rgba(255,255,255,0.10);color:{_TEXT};}}"
)
_INPUT = (
    f"QLineEdit{{background:rgba(255,255,255,0.06);color:{_TEXT};"
    f"border:1px solid {_BORDER};border-radius:12px;padding:11px 14px;font-size:14px;}}"
    f"QLineEdit:focus{{border:1px solid rgba(139,92,246,0.60);}}"
)
_COMBO = (
    f"QComboBox{{background:rgba(255,255,255,0.06);color:{_TEXT};"
    f"border:1px solid {_BORDER};border-radius:12px;padding:10px 14px;font-size:13px;}}"
    f"QComboBox::drop-down{{border:0;}}"
    f"QComboBox QAbstractItemView{{background:#1A1A2E;color:{_TEXT};"
    f"border:1px solid {_BORDER};selection-background-color:rgba(139,92,246,0.30);}}"
)


# ── tiny helpers
def _lbl(text, size=14, bold=False, color=_TEXT):
    l = QLabel(text)
    l.setWordWrap(True)
    f = QFont("Segoe UI Variable Text", size)
    if bold:
        f.setWeight(QFont.DemiBold)
    l.setFont(f)
    l.setStyleSheet(f"color:{color};background:transparent;")
    return l


def _big(text, size=26):
    l = QLabel(text)
    l.setWordWrap(True)
    l.setFont(QFont("Segoe UI Variable Display", size, QFont.DemiBold))
    l.setStyleSheet(f"color:{_TEXT};background:transparent;")
    return l


def _div():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{_BORDER};")
    return f


def _perm_card(icon, heading, body, parent_lay):
    row = QFrame()
    row.setStyleSheet(_GLASS)
    rl = QHBoxLayout(row)
    rl.setContentsMargins(16, 14, 16, 14)
    rl.setSpacing(14)
    ic = QLabel(icon)
    ic.setFont(QFont("Segoe UI Emoji", 22))
    ic.setFixedWidth(42)
    ic.setAlignment(Qt.AlignCenter)
    rl.addWidget(ic)
    txt = QVBoxLayout()
    txt.setSpacing(2)
    txt.addWidget(_lbl(heading, 13, True))
    txt.addWidget(_lbl(body, 12, color=_MUTED))
    rl.addLayout(txt, 1)
    parent_lay.addWidget(row)


# ── animated background
class BgWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if parent:
            self.setGeometry(parent.rect())
            self.lower()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor(_BG1))
        g.setColorAt(1, QColor(_BG2))
        p.fillRect(self.rect(), QBrush(g))
        for cx, cy, r, col, a in (
            (self.width() * .20, self.height() * .15, self.width() * .50, _VIOLET, .16),
            (self.width() * .85, self.height() * .30, self.width() * .40, _BLUE,   .12),
            (self.width() * .50, self.height() * 1.0, self.width() * .60, _PINK,   .10),
        ):
            gr = QRadialGradient(QPointF(cx, cy), r)
            c = QColor(col); c.setAlphaF(a)
            e = QColor(col); e.setAlphaF(0)
            gr.setColorAt(0, c); gr.setColorAt(1, e)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(gr))
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.end()


# ── step 1: welcome
class PageWelcome(QWidget):
    def __init__(self):
        super().__init__()
        self._bg = BgWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 60, 80, 40)
        lay.setSpacing(0)
        lay.addStretch(2)
        orb = QLabel("\u25ce")
        orb.setFont(QFont("Segoe UI Emoji", 72))
        orb.setAlignment(Qt.AlignCenter)
        orb.setStyleSheet(f"color:{_VIOLET};background:transparent;")
        lay.addWidget(orb)
        lay.addSpacing(24)
        t = _big("Hey, I'm Sotto.", 30)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addSpacing(12)
        sub = _lbl(
            "Your personal AI assistant for Windows \u2014 voice-first, "
            "local memory, fully on your PC.\n"
            "Let\u2019s get set up in about a minute.",
            14, color=_MUTED)
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)
        lay.addStretch(3)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg.setGeometry(self.rect())


# ── step 2: AI key (BYOK)
class PageApiKey(QWidget):
    key_saved = Signal()

    PROVIDERS = [
        ("Google Gemini  (free tier \u2014 easiest start)",
         "GEMINI_API_KEY",
         "https://aistudio.google.com/apikey"),
        ("Groq  (very fast, free tier)",
         "GROQ_API_KEY",
         "https://console.groq.com/keys"),
        ("OpenRouter  (100+ models, free credits)",
         "OPENROUTER_API_KEY",
         "https://openrouter.ai/settings/keys"),
        ("GitHub Models  (free with GitHub account)",
         "GITHUB_TOKEN",
         "https://github.com/settings/tokens"),
    ]

    def __init__(self):
        super().__init__()
        self._bg = BgWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(72, 40, 72, 30)
        lay.setSpacing(0)

        lay.addWidget(_big("Connect your AI brain", 22))
        lay.addSpacing(8)
        lay.addWidget(_lbl(
            "Sotto needs an API key to understand and respond to you.\n"
            "Your key is stored securely on this PC and never shared.",
            13, color=_MUTED))
        lay.addSpacing(22)

        lay.addWidget(_lbl("Choose a provider:", 13, True))
        lay.addSpacing(6)
        self._box = QComboBox()
        self._box.setStyleSheet(_COMBO)
        for name, _, _ in self.PROVIDERS:
            self._box.addItem(name)
        self._box.currentIndexChanged.connect(self._idx_changed)
        lay.addWidget(self._box)
        lay.addSpacing(6)

        self._link_btn = QPushButton("\U0001f517  Get a free key \u2192")
        self._link_btn.setStyleSheet(_BTN_GHOST)
        self._link_btn.setCursor(Qt.PointingHandCursor)
        self._link_btn.clicked.connect(self._open_link)
        lay.addWidget(self._link_btn)

        lay.addSpacing(20)
        lay.addWidget(_div())
        lay.addSpacing(20)

        lay.addWidget(_lbl("Paste your API key:", 13, True))
        lay.addSpacing(6)

        kr = QHBoxLayout()
        self._inp = QLineEdit()
        self._inp.setEchoMode(QLineEdit.Password)
        self._inp.setPlaceholderText("sk-\u2026  or  AIza\u2026  or  gsk_\u2026")
        self._inp.setStyleSheet(_INPUT)
        self._inp.textChanged.connect(
            lambda t: self._vbtn.setEnabled(bool(t.strip())))
        kr.addWidget(self._inp, 1)

        sb = QPushButton("\U0001f441")
        sb.setFixedSize(44, 44)
        sb.setCheckable(True)
        sb.setStyleSheet(
            _BTN_GHOST.replace("padding:12px 24px", "padding:0"))
        sb.setCursor(Qt.PointingHandCursor)
        sb.toggled.connect(lambda on: self._inp.setEchoMode(
            QLineEdit.Normal if on else QLineEdit.Password))
        kr.addWidget(sb)
        lay.addLayout(kr)
        lay.addSpacing(16)

        self._vbtn = QPushButton("\u2713  Verify and save key")
        self._vbtn.setStyleSheet(_BTN_PRI)
        self._vbtn.setCursor(Qt.PointingHandCursor)
        self._vbtn.setEnabled(False)
        self._vbtn.clicked.connect(self._verify)
        lay.addWidget(self._vbtn)

        lay.addSpacing(10)
        self._st = _lbl("", 12, color=_MUTED)
        self._st.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._st)
        lay.addStretch(1)

        lay.addWidget(_lbl(
            "Already added a key to the .env file?  You can skip this step.",
            11, color=_MUTED))

        self._link = ""
        self._idx_changed(0)

    def _idx_changed(self, i):
        self._link = self.PROVIDERS[i][2]

    def _open_link(self):
        import webbrowser
        webbrowser.open(self._link)

    def _verify(self):
        key = self._inp.text().strip()
        if not key:
            return
        idx = self._box.currentIndex()
        _, env, _ = self.PROVIDERS[idx]
        self._vbtn.setEnabled(False)
        self._vbtn.setText("Checking\u2026")
        self._set_st(_MUTED, "Connecting to the provider\u2026")
        threading.Thread(target=self._do, args=(env, key), daemon=True).start()

    def _do(self, env, key):
        ok, msg = _test_key(env, key)
        if ok:
            _save_key(env, key)
        QTimer.singleShot(0, lambda: self._done(ok, msg))

    def _done(self, ok, msg):
        if ok:
            self._set_st(_GREEN, "\u2713  Key works! Saved securely.")
            self._vbtn.setText("\u2713  Verified")
            self._vbtn.setStyleSheet(
                f"QPushButton{{background:rgba(52,211,153,.2);color:{_GREEN};"
                f"border:1px solid rgba(52,211,153,.4);border-radius:14px;"
                f"padding:12px 28px;font-size:14px;font-weight:600;}}")
            self.key_saved.emit()
        else:
            self._set_st(_RED, f"\u2717  {msg}")
            self._vbtn.setText("\u2713  Verify and save key")
            self._vbtn.setEnabled(True)

    def _set_st(self, col, text):
        self._st.setStyleSheet(f"color:{col};background:transparent;")
        self._st.setText(text)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg.setGeometry(self.rect())


# ── step 3: permissions
class PagePermissions(QWidget):
    def __init__(self):
        super().__init__()
        self._bg = BgWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(72, 40, 72, 30)
        lay.setSpacing(0)

        lay.addWidget(_big("What Sotto can access", 22))
        lay.addSpacing(8)
        lay.addWidget(_lbl(
            "Sotto only uses these when you ask \u2014 "
            "nothing runs silently in the background.",
            13, color=_MUTED))
        lay.addSpacing(20)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setStyleSheet("QScrollArea{background:transparent;border:0;}")
        h = QWidget()
        h.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(h)
        vl.setSpacing(10)
        vl.setContentsMargins(0, 0, 6, 0)

        _perm_card("\U0001f3a4", "Microphone",
                   "Active only while you\u2019re talking \u2014 "
                   "never recorded in the background.", vl)
        _perm_card("\U0001f4c1", "Files and Folders",
                   "Open, read, move, or organise files you ask about.", vl)
        _perm_card("\U0001f680", "Launch and control apps",
                   "Open apps (Notepad, Chrome, Spotify\u2026) when you say so.", vl)
        _perm_card("\U0001f4f8", "Screen snapshot",
                   "Take a screenshot to answer questions about what\u2019s on screen.", vl)
        _perm_card("\U0001f310", "Internet lookups",
                   "Search the web or fetch news when you ask. "
                   "No background browsing.", vl)
        _perm_card("\U0001f4c5", "Reminders and timers",
                   "Store reminders you set, locally on this PC.", vl)
        _perm_card("\U0001f511", "Your AI key",
                   "Sent only to the AI provider you chose. "
                   "Never logged or shared.", vl)

        sc.setWidget(h)
        lay.addWidget(sc, 1)
        lay.addSpacing(10)
        lay.addWidget(_lbl(
            "Change or review permissions any time in  Settings \u2192 Permissions.",
            11, color=_MUTED))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg.setGeometry(self.rect())


# ── level bar for mic test
class LevelBar(QWidget):
    def __init__(self):
        super().__init__()
        self._v = 0.0

    def set_level(self, v):
        self._v = v
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 20))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        fw = int(w * min(1.0, self._v * 3.5))
        if fw > 4:
            g = QLinearGradient(0, 0, w, 0)
            g.setColorAt(0, QColor(_VIOLET))
            g.setColorAt(.5, QColor(_CYAN))
            g.setColorAt(1, QColor(_GREEN))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(0, 0, fw, h, h / 2, h / 2)
        p.end()


# ── step 4: mic test
class PageMicTest(QWidget):
    def __init__(self):
        super().__init__()
        self._bg = BgWidget(self)
        self._stream = None
        self._timer = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 50, 80, 40)
        lay.setSpacing(0)
        lay.addStretch(1)
        lay.addWidget(_big("Quick mic check", 22))
        lay.addSpacing(10)
        lay.addWidget(_lbl(
            "Say anything \u2014 if the bar below moves, your mic is working.",
            13, color=_MUTED))
        lay.addSpacing(28)
        self._bar = LevelBar()
        self._bar.setFixedHeight(52)
        lay.addWidget(self._bar)
        lay.addSpacing(18)
        self._st = _lbl("Starting mic\u2026", 13, color=_MUTED)
        self._st.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._st)
        lay.addStretch(2)

    def showEvent(self, e):
        super().showEvent(e)
        self._start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._stop()

    def _start(self):
        try:
            from audio import MicStream
            self._stream = MicStream()
            self._stream.start()
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(40)
            self._st.setText("Speak into your mic\u2026")
            self._st.setStyleSheet(f"color:{_MUTED};background:transparent;")
        except Exception as ex:
            self._st.setText(f"\u26a0 Mic unavailable: {ex}")
            self._st.setStyleSheet(f"color:{_AMBER};background:transparent;")

    def _stop(self):
        try:
            if self._timer:
                self._timer.stop()
            if self._stream:
                self._stream.stop()
                self._stream = None
        except Exception:
            pass

    def _tick(self):
        if self._stream:
            v = self._stream.level
            self._bar.set_level(v)
            if v > 0.07:
                self._st.setText("\u2713  Mic is working!")
                self._st.setStyleSheet(
                    f"color:{_GREEN};background:transparent;")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg.setGeometry(self.rect())


# ── step 5: done
class PageDone(QWidget):
    def __init__(self):
        super().__init__()
        self._bg = BgWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 60, 80, 40)
        lay.setSpacing(0)
        lay.addStretch(2)
        ck = QLabel("\u2713")
        ck.setFont(QFont("Segoe UI Emoji", 72))
        ck.setAlignment(Qt.AlignCenter)
        ck.setStyleSheet(f"color:{_GREEN};background:transparent;")
        lay.addWidget(ck)
        lay.addSpacing(22)
        t = _big("You\u2019re all set!", 28)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addSpacing(16)
        for tip in [
            "\U0001f4ac  Press Space or the mic button to start talking.",
            "\u2328\ufe0f   Ctrl+Shift+S from anywhere wakes Sotto up.",
            "\u2699\ufe0f   Settings are in the \u2261 menu \u2014 change anything any time.",
            "\U0001f515  Say \u2018stop\u2019 while Sotto is speaking to interrupt it.",
        ]:
            ll = _lbl(tip, 13, color=_MUTED)
            ll.setAlignment(Qt.AlignCenter)
            lay.addWidget(ll)
            lay.addSpacing(4)
        lay.addStretch(3)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg.setGeometry(self.rect())


# ── progress dot bar
class DotBar(QWidget):
    _LABELS = ["Welcome", "AI Key", "Permissions", "Mic check", "Done"]

    def __init__(self, n):
        super().__init__()
        self._n = n
        self._a = 0
        self.setFixedHeight(44)
        self.setStyleSheet(
            f"background:#0D0D18;border-bottom:1px solid {_BORDER};")

    def set_active(self, i):
        self._a = i
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        dr, sp = 5, 14
        total = self._n * (dr * 2) + (self._n - 1) * sp
        x0 = (w - total) / 2
        cy = h / 2 - 5
        for i in range(self._n):
            cx = x0 + i * (dr * 2 + sp) + dr
            if i == self._a:
                c = QColor(_CYAN)
                r = float(dr)
            elif i < self._a:
                c = QColor(_VIOLET)
                r = float(dr - 1)
            else:
                c = QColor(70, 70, 95)
                r = float(dr - 1)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(cx, cy), r, r)
        lbl = self._LABELS[self._a] if self._a < len(self._LABELS) else ""
        p.setPen(QColor(_MUTED))
        p.setFont(QFont("Segoe UI Variable Text", 11))
        p.drawText(0, int(cy + 18), w, 16, Qt.AlignCenter, lbl)
        p.end()


# ── wizard shell
class OnboardingWizard(QMainWindow):
    finished = Signal(bool)   # True = completed, False = closed early

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sotto \u2014 Setup")
        self.setMinimumSize(700, 640)
        self.resize(800, 700)
        self._done = False

        root = QWidget()
        self.setCentralWidget(root)
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        self._dots = DotBar(5)
        rl.addWidget(self._dots)

        self._pages = [
            PageWelcome(),
            PageApiKey(),
            PagePermissions(),
            PageMicTest(),
            PageDone(),
        ]
        ph = QWidget()
        ph.setStyleSheet(f"background:{_BG1};")
        pl = QVBoxLayout(ph)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        for page in self._pages:
            pl.addWidget(page)
            page.hide()
        rl.addWidget(ph, 1)

        nav = QFrame()
        nav.setStyleSheet(
            f"background:#0D0D18;border-top:1px solid {_BORDER};")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(32, 16, 32, 16)
        nl.setSpacing(12)

        self._back = QPushButton("\u2190 Back")
        self._back.setStyleSheet(_BTN_GHOST)
        self._back.setCursor(Qt.PointingHandCursor)
        self._back.clicked.connect(self._go_back)
        nl.addWidget(self._back)

        self._skip = QPushButton("Skip this step")
        self._skip.setStyleSheet(_BTN_GHOST)
        self._skip.setCursor(Qt.PointingHandCursor)
        self._skip.clicked.connect(self._next)
        nl.addWidget(self._skip)

        nl.addStretch(1)

        self._nxt = QPushButton("Get started \u2192")
        self._nxt.setStyleSheet(_BTN_PRI)
        self._nxt.setCursor(Qt.PointingHandCursor)
        self._nxt.clicked.connect(self._next)
        nl.addWidget(self._nxt)

        rl.addWidget(nav)

        self._cur = 0
        self._show(0)

    def _show(self, i):
        for j, page in enumerate(self._pages):
            page.setVisible(j == i)
        self._cur = i
        self._dots.set_active(i)
        self._back.setVisible(i > 0)
        self._skip.setVisible(i == 1)  # only on key step
        self._nxt.setText(
            "Open Sotto \u2192" if i == 4 else
            "Get started \u2192" if i == 0 else
            "Continue \u2192"
        )

    def _next(self):
        if self._cur == 4:
            self._done = True
            _mark_done()
            self.close()
        else:
            self._show(self._cur + 1)

    def _go_back(self):
        if self._cur > 0:
            self._show(self._cur - 1)

    def closeEvent(self, e):
        try:
            self._pages[3]._stop()
        except Exception:
            pass
        self.finished.emit(self._done)
        e.accept()


# ── API key verification
def _test_key(env_var: str, key: str) -> tuple:
    os.environ[env_var] = key
    try:
        if env_var == "GEMINI_API_KEY":
            url = (f"https://generativelanguage.googleapis.com"
                   f"/v1beta/models?key={key}&pageSize=1")
            req = urllib.request.Request(
                url, headers={"Accept": "application/json"})
        elif env_var == "GROQ_API_KEY":
            url = "https://api.groq.com/openai/v1/models"
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {key}",
                               "Accept": "application/json"})
        elif env_var == "OPENROUTER_API_KEY":
            url = "https://openrouter.ai/api/v1/models"
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {key}",
                               "Accept": "application/json"})
        elif env_var == "GITHUB_TOKEN":
            url = "https://api.github.com/user"
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {key}",
                               "Accept": "application/vnd.github+json"})
        else:
            return True, "Saved"
        with urllib.request.urlopen(req, timeout=12):
            return True, "Connected"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid key \u2014 check you copied the full key."
        if e.code == 403:
            return False, "Key doesn\u2019t have the right permissions."
        return False, f"HTTP {e.code} from the provider."
    except Exception as ex:
        return False, f"Couldn\u2019t reach the server ({ex})"


def _save_key(env_var: str, key: str):
    env_path = Path(__file__).parent / ".env"
    lines = (env_path.read_text("utf-8").splitlines()
             if env_path.exists() else [])
    found = False
    for i, ln in enumerate(lines):
        if ln.startswith(env_var + "="):
            lines[i] = f"{env_var}={key}"
            found = True
            break
    if not found:
        lines.append(f"{env_var}={key}")
    env_path.write_text("\n".join(lines) + "\n", "utf-8")
    os.environ[env_var] = key
    try:
        from config import save_setting
        mapping = {
            "GEMINI_API_KEY":     "gemini_api_key",
            "GROQ_API_KEY":       "groq_api_key",
            "OPENROUTER_API_KEY": "openrouter_api_key",
            "GITHUB_TOKEN":       "github_token",
        }
        if env_var in mapping:
            save_setting(mapping[env_var], key)
    except Exception:
        pass


# ── first-run detection
_FLAG = DATA_DIR / "onboarded.flag"


def needs_onboarding() -> bool:
    """True if this is a first run or no API key is set."""
    if not _FLAG.exists():
        return True
    return not any(
        os.environ.get(v)
        for v in ("GEMINI_API_KEY", "GROQ_API_KEY",
                  "OPENROUTER_API_KEY", "GITHUB_TOKEN")
    )


def _mark_done():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _FLAG.write_text("1", "utf-8")


# ── public entry point
def run_if_needed(app: "QApplication") -> bool:
    """
    Show the wizard if this is a first run (no API key etc.).
    Blocks until the wizard closes.
    Returns True when the user completed setup (or it wasn't needed).
    """
    if not needs_onboarding():
        return True

    result = {"v": False}
    wizard = OnboardingWizard()
    wizard.finished.connect(lambda ok: result.update(v=ok))
    wizard.show()

    loop = QEventLoop()
    wizard.finished.connect(loop.quit)
    loop.exec()

    return result["v"]
