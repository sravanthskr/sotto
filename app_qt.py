"""
app_qt.py - RealAssistant desktop app (PySide6 / Qt, pure Python).

Redesigned to the "Aura" spec: dark glassmorphism, neon violet->blue glow, an orb with
blinking eyes, a live waveform, a floating input bar, sidebar navigation (Home / Tasks /
Insights / Settings), quick-action chips and a compact mode.

    .\\run.bat ui                       (or: python app_qt.py)
    python app_qt.py --shot out.png     # offscreen render
    python app_qt.py --shot-live out.png# real-window render (fonts included)
"""

import math
import sys
import threading
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QKeySequence, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient, QShortcut)
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                               QTextEdit, QVBoxLayout, QWidget)

import tools
import voice
from audio import MicStream
from config import API_BASE_URL, MODEL_NAME
from core import Assistant

# ---------------------------------------------------------------- theme (Aura spec)
BASE = "#09090B"
SURFACE = "#18181B"
VIOLET = "#8B5CF6"
BLUE = "#3B82F6"
PINK = "#EC4899"
TEXT = "#FAFAFA"
MUTED = "#A1A1AA"
BORDER = "rgba(255,255,255,0.08)"
PROVIDER = "gemini" if API_BASE_URL else "groq"

GLASS = ("background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
         " stop:0 rgba(255,255,255,0.07), stop:0.35 rgba(24,24,27,0.72),"
         " stop:1 rgba(24,24,27,0.88));"
         f" border:1px solid rgba(255,255,255,0.10); border-radius:16px;")
PILL = ("background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        " stop:0 rgba(255,255,255,0.06), stop:1 rgba(24,24,27,0.80));"
        f" border:1px solid rgba(255,255,255,0.10); border-radius:999px;")
BG_GLOW = ("qradialgradient(cx:0.5, cy:0.22, radius:0.95,"
           " stop:0 rgba(139,92,246,0.20), stop:0.45 rgba(9,9,11,0.98),"
           " stop:1 #09090B)")

CHIPS = ["Summarise screen", "System status", "Remind me", "Open notepad"]


def _icon_path(kind, size=22):
    """Tiny monoline icons drawn as paths (no emoji, no external assets)."""
    p = QPainterPath()
    s = size
    if kind == "home":
        p.moveTo(s * 0.14, s * 0.52); p.lineTo(s * 0.50, s * 0.20)
        p.lineTo(s * 0.86, s * 0.52); p.lineTo(s * 0.86, s * 0.86)
        p.lineTo(s * 0.14, s * 0.86); p.closeSubpath()
    elif kind == "tasks":
        p.addRoundedRect(QRectF(s * 0.20, s * 0.14, s * 0.60, s * 0.72), 4, 4)
        p.moveTo(s * 0.34, s * 0.40); p.lineTo(s * 0.44, s * 0.50); p.lineTo(s * 0.66, s * 0.30)
    elif kind == "insights":
        for i, x in enumerate((0.24, 0.46, 0.68)):
            h = (0.30, 0.52, 0.70)[i]
            p.addRoundedRect(QRectF(s * x, s * (0.86 - h), s * 0.14, s * h), 3, 3)
    elif kind == "gear":
        p.addEllipse(QPointF(s / 2, s / 2), s * 0.20, s * 0.20)
        for i in range(8):
            a = i * math.pi / 4
            x1, y1 = s / 2 + math.cos(a) * s * 0.28, s / 2 + math.sin(a) * s * 0.28
            x2, y2 = s / 2 + math.cos(a) * s * 0.40, s / 2 + math.sin(a) * s * 0.40
            p.moveTo(x1, y1); p.lineTo(x2, y2)
    elif kind == "mic":
        p.addRoundedRect(QRectF(s * 0.36, s * 0.14, s * 0.28, s * 0.42), s * 0.14, s * 0.14)
        p.moveTo(s * 0.24, s * 0.50)
        p.arcTo(QRectF(s * 0.24, s * 0.30, s * 0.52, s * 0.42), 180, 180)
        p.moveTo(s * 0.50, s * 0.72); p.lineTo(s * 0.50, s * 0.86)
    elif kind == "send":
        p.moveTo(s * 0.16, s * 0.50); p.lineTo(s * 0.86, s * 0.22)
        p.lineTo(s * 0.56, s * 0.86); p.lineTo(s * 0.44, s * 0.58); p.closeSubpath()
    elif kind == "plus":
        p.moveTo(s * 0.50, s * 0.24); p.lineTo(s * 0.50, s * 0.76)
        p.moveTo(s * 0.24, s * 0.50); p.lineTo(s * 0.76, s * 0.50)
    elif kind == "shrink":
        p.moveTo(s * 0.24, s * 0.40); p.lineTo(s * 0.76, s * 0.40)
        p.moveTo(s * 0.24, s * 0.60); p.lineTo(s * 0.76, s * 0.60)
    return p


class IconButton(QPushButton):
    def __init__(self, kind, tooltip="", accent=False, size=44):
        super().__init__()
        self.kind = kind
        self.accent = accent
        self.active = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setStyleSheet("QPushButton{background:transparent;border:0;}")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if self.accent:
            g = QLinearGradient(0, 0, w, h)
            g.setColorAt(0, QColor(VIOLET)); g.setColorAt(1, QColor(BLUE))
            p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(0, 0, w, h))
            col = QColor("#ffffff")
        else:
            if self.active:
                g = QLinearGradient(0, 0, w, h)
                g.setColorAt(0, QColor(139, 92, 246, 165))
                g.setColorAt(1, QColor(59, 130, 246, 150))
                p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 13, 13)
            col = QColor("#ffffff") if self.active else \
                (QColor(TEXT) if self.underMouse() else QColor(MUTED))
        pen = QPen(col, 1.8)
        pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.translate(self.width() / 2 - 11, self.height() / 2 - 11)
        p.drawPath(_icon_path(self.kind))
        p.end()


# ------------------------------------------------------------------ the orb
class Orb(QWidget):
    BARS = 40

    def __init__(self):
        super().__init__()
        self.mode = "idle"
        self.level = 0.0
        self.phase = 0.0
        self.blink = 0.0
        self.setMinimumSize(300, 300)
        t = QTimer(self); t.timeout.connect(self._tick); t.start(16)

    def _tick(self):
        self.phase += 0.05
        # blink every ~3.5 s for ~0.16 s
        beat = self.phase % 3.9
        self.blink = max(0.0, 1.0 - abs(beat - 0.2) / 0.16)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h * 0.46
        base = min(w, h) * 0.17

        if self.mode == "listening":
            live, c1, c2 = self.level, QColor("#60A5FA"), QColor(BLUE)
            c1s, c2s = "#93C5FD", BLUE
        elif self.mode == "processing":
            live, c1, c2 = 0.35, QColor(VIOLET), QColor(PINK)
            c1s, c2s = VIOLET, PINK
        elif self.mode == "speaking":
            live, c1, c2 = 0.45 + 0.3 * (math.sin(self.phase * 1.8) + 1) / 2, QColor("#60A5FA"), QColor(BLUE)
            c1s, c2s = "#93C5FD", BLUE
        else:  # idle
            live, c1, c2 = 0.05 + 0.03 * math.sin(self.phase * 0.5), QColor(VIOLET), QColor(BLUE)
            c1s, c2s = VIOLET, BLUE

        # aura
        aura_r = base * (2.4 + live * 1.5)
        g = QRadialGradient(QPointF(cx, cy), aura_r)
        a0 = QColor(c1); a0.setAlphaF(min(0.65, 0.10 + live * 0.5))
        a1 = QColor(c2); a1.setAlphaF(0.0)
        g.setColorAt(0.0, a0); g.setColorAt(1.0, a1)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), aura_r, aura_r)

        # rotating ring while processing
        if self.mode == "processing":
            ang = (self.phase * 60) % 360
            pen = QPen(QColor(c2), 2.2); pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(cx - base * 1.55, cy - base * 1.55, base * 3.1, base * 3.1),
                      int(ang * 16), int(110 * 16))
        else:
            for i, mult in enumerate((1.85, 1.45, 1.10)):
                r = base * mult * (1 + live * 0.14 * (1 - i / 4))
                ring = QColor(c2)
                ring.setAlphaF(min(0.75, 0.10 + live * 0.55 * (1 - i / 5)))
                p.setPen(QPen(ring, 1.3)); p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), r, r)

        # core sphere
        core_r = base * (1.0 + live * 0.32)
        core = QRadialGradient(QPointF(cx - core_r * 0.28, cy - core_r * 0.32), core_r * 1.8)
        core.setColorAt(0.0, QColor("#C4B5FD" if self.mode != "listening" else "#BFDBFE"))
        core.setColorAt(0.55, QColor(VIOLET if self.mode != "listening" else BLUE))
        core.setColorAt(1.0, QColor("#312E81" if self.mode != "listening" else "#1E3A8A"))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # eyes
        eye_w, eye_h = core_r * 0.34, core_r * 0.46
        gap = core_r * 0.52
        open_ = max(0.08, 1.0 - self.blink)
        for sign in (-1, 1):
            rect = QRectF(cx + sign * gap / 2 - eye_w / 2, cy - eye_h * open_ / 2,
                          eye_w, eye_h * open_)
            p.setBrush(QBrush(QColor(255, 255, 255, 235)))
            p.drawRoundedRect(rect, eye_w / 2, eye_w / 2)

        # waveform
        n = self.BARS
        span = w * 0.78
        x0 = (w - span) / 2.0
        slot = span / n
        bw = max(2.0, slot * 0.5)
        wy = h * 0.86
        for i in range(n):
            t = i / (n - 1)
            center = math.sin(math.pi * t) ** 0.85
            if self.mode == "idle":
                amp = 4 + 8 * center * (0.5 + 0.5 * math.sin(self.phase * 0.9 + i * 0.4)); a = 0.30
            elif self.mode == "processing":
                amp = 4 + (10 + 40 * center) * (0.6 + 0.4 * math.sin(self.phase * 1.6 + i * 0.9)); a = 0.55
            else:
                amp = 4 + (10 + live * 90) * (0.35 + 0.65 * center) * \
                      (0.35 + 0.65 * (math.sin(self.phase * 2.2 + i * 0.55) + 1) / 2)
                a = min(1.0, 0.35 + 0.6 * center)
            c = QColor(c1 if self.mode == "listening" else c2)
            c.setAlphaF(a)
            p.setBrush(QBrush(c)); p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x0 + i * slot, wy - amp / 2, bw, amp), bw / 2, bw / 2)
        p.end()


# ------------------------------------------------------------------ bubbles
class Bubble(QFrame):
    def __init__(self, text, role):
        super().__init__()
        self.role = role
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setStyleSheet(f"color:{TEXT};font-size:14px;background:transparent;")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 11, 14, 11)
        row.addWidget(self.label, 1)
        if role == "user":
            self.setStyleSheet("QFrame{background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                               "stop:0 rgba(139,92,246,0.30), stop:1 rgba(59,130,246,0.28));"
                               "border:1px solid rgba(139,92,246,0.45);border-radius:16px;}")
        else:
            self.setStyleSheet("QFrame{background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                               "stop:0 rgba(255,255,255,0.07), stop:1 rgba(24,24,27,0.88));"
                               "border:1px solid rgba(255,255,255,0.10);border-radius:16px;}")
        self.setMaximumWidth(580)

    def append(self, chunk):
        self.label.setText(self.label.text() + chunk)


# ------------------------------------------------------------------ window
class Window(QMainWindow):
    mode_sig = Signal(str, str)
    heard_sig = Signal(str)
    reply_sig = Signal(str)
    level_sig = Signal(float)
    add_bubble = Signal(str, str)
    stream_sig = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RealAssistant")
        self.resize(1080, 720)
        self.setMinimumSize(880, 620)
        self.setStyleSheet(f"QMainWindow{{background:{BG_GLOW};}}")
        self.assistant = Assistant(on_text=self._on_text, on_tool=self._on_tool,
                                    on_learned=lambda f: None)
        self.mic = None
        self.mode = "idle"
        self._spoken = []
        self._silence_since = None
        self._started = 0.0
        self._dragging = None
        self._current = None
        self._build()
        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self._toggle_visible)

    # ------------------------------------------------------------ build
    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # sidebar
        self.side = QFrame()
        self.side.setFixedWidth(72)
        self.side.setStyleSheet(f"QFrame{{background:rgba(9,9,11,0.55);"
                                f"border-right:1px solid rgba(255,255,255,0.08);}}")
        sl = QVBoxLayout(self.side); sl.setContentsMargins(16, 18, 16, 18); sl.setSpacing(14)
        self.nav_buttons = {}
        for key, tip in (("home", "Home"), ("tasks", "Tasks"), ("insights", "Insights")):
            b = IconButton(key, tip)
            b.clicked.connect(lambda _=False, k=key: self._page(k))
            sl.addWidget(b, alignment=Qt.AlignHCenter)
            self.nav_buttons[key] = b
        sl.addStretch(1)
        line = QFrame(); line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,0.09);")
        sl.addWidget(line)
        self.compact_btn = IconButton("shrink", "Compact mode")
        self.compact_btn.clicked.connect(self._toggle_compact)
        sl.addWidget(self.compact_btn, alignment=Qt.AlignHCenter)
        gear = IconButton("gear", "Settings")
        gear.clicked.connect(lambda: self._page("settings"))
        sl.addWidget(gear, alignment=Qt.AlignHCenter)
        self.nav_buttons["settings"] = gear
        outer.addWidget(self.side)

        # pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._home_page())
        self.stack.addWidget(self._tasks_page())
        self.stack.addWidget(self._insights_page())
        self.stack.addWidget(self._settings_page())
        outer.addWidget(self.stack, 1)
        self._page("home")
        self.mode_sig.connect(self._apply_mode)
        self.level_sig.connect(self._apply_level)
        self.heard_sig.connect(lambda t: (self.overlay.setText(t), self.overlay.setVisible(bool(t))))
        self.reply_sig.connect(self._set_reply)
        self.add_bubble.connect(self._add_bubble)
        self.stream_sig.connect(self._stream_chunk)

    def _home_page(self):
        page = QWidget()
        lay = QVBoxLayout(page); lay.setContentsMargins(28, 16, 28, 16); lay.setSpacing(10)

        self.orb = Orb()
        lay.addWidget(self.orb, 2)

        self.status = QLabel("Tap to talk")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("Segoe UI Variable Display", 16, QFont.DemiBold))
        self.status.setStyleSheet(f"color:{TEXT};")
        lay.addWidget(self.status)

        self.overlay = QLabel("")
        self.overlay.setAlignment(Qt.AlignCenter)
        self.overlay.setStyleSheet(f"{PILL} color:{TEXT}; padding:6px 16px;")
        self.overlay.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        wrap = QHBoxLayout(); wrap.addStretch(1); wrap.addWidget(self.overlay); wrap.addStretch(1)
        lay.addLayout(wrap)
        self.overlay.hide()

        # transcript
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:0;}")
        holder = QWidget(); holder.setStyleSheet("background:transparent;")
        self.msg_lay = QVBoxLayout(holder); self.msg_lay.setContentsMargins(0, 0, 0, 0)
        self.msg_lay.setSpacing(10); self.msg_lay.addStretch(1)
        self.scroll.setWidget(holder)
        self.scroll.setMinimumHeight(150)
        lay.addWidget(self.scroll, 2)

        # quick chips
        self.chips_row = QHBoxLayout(); self.chips_row.setSpacing(8)
        for text in CHIPS:
            c = QPushButton(text)
            c.setCursor(Qt.PointingHandCursor)
            c.setStyleSheet(f"QPushButton{{{PILL} color:#C7C7CC; padding:9px 16px; font-size:12px;}}"
                            f"QPushButton:hover{{color:{TEXT};border:1px solid rgba(139,92,246,0.65);}}")
            c.clicked.connect(lambda _=False, t=text: self._send_text(t))
            self.chips_row.addWidget(c)
        self.chips_row.addStretch(1)
        lay.addLayout(self.chips_row)

        # floating input bar
        bar = QFrame(); bar.setStyleSheet(f"QFrame{{{GLASS}}}")
        bl = QHBoxLayout(bar); bl.setContentsMargins(12, 9, 12, 9); bl.setSpacing(10)
        bl.addWidget(IconButton("plus", "Attach (coming soon)"))
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Ask me anything…")
        self.entry.setStyleSheet(f"QLineEdit{{background:transparent;border:0;color:{TEXT};font-size:14px;}}")
        self.entry.returnPressed.connect(lambda: self._send_text(self.entry.text()))
        bl.addWidget(self.entry, 1)
        self.mic_btn = IconButton("mic", "Talk", accent=True, size=44)
        self.mic_btn.clicked.connect(self.toggle_talk)
        bl.addWidget(self.mic_btn)
        send = IconButton("send", "Send")
        send.setStyleSheet("QPushButton{background:transparent;border:0;}")
        send.clicked.connect(lambda: self._send_text(self.entry.text()))
        bl.addWidget(send)
        lay.addWidget(bar)

        footer = QHBoxLayout()
        footer.addStretch(1)
        hint = QLabel("hold Space to talk  ·  Ctrl+Space show/hide")
        hint.setStyleSheet(f"color:#C7C7CC;font-size:12px;")
        footer.addWidget(hint)
        lay.addLayout(footer)
        return page

    def _tasks_page(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(28, 24, 28, 24)
        title = QLabel("Tasks & reminders"); title.setFont(QFont("Segoe UI Variable Display", 18, QFont.DemiBold))
        lay.addWidget(title)
        self.tasks_body = QLabel("")
        self.tasks_body.setWordWrap(True); self.tasks_body.setStyleSheet(f"color:{MUTED};")
        card = QFrame(); card.setStyleSheet(f"QFrame{{{GLASS}}}")
        cl = QVBoxLayout(card); cl.addWidget(self.tasks_body)
        lay.addWidget(card)
        refresh = QPushButton("Refresh")
        refresh.setStyleSheet(f"QPushButton{{{PILL} color:{TEXT}; padding:8px 16px;}}")
        refresh.clicked.connect(self._refresh_tasks)
        lay.addWidget(refresh, alignment=Qt.AlignLeft)
        lay.addStretch(1)
        return page

    def _insights_page(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(28, 24, 28, 24)
        title = QLabel("Insights"); title.setFont(QFont("Segoe UI Variable Display", 18, QFont.DemiBold))
        lay.addWidget(title)
        self.insight_body = QLabel("")
        self.insight_body.setWordWrap(True); self.insight_body.setStyleSheet(f"color:{MUTED};")
        card = QFrame(); card.setStyleSheet(f"QFrame{{{GLASS}}}")
        cl = QVBoxLayout(card); cl.addWidget(self.insight_body)
        lay.addWidget(card)
        refresh = QPushButton("Refresh")
        refresh.setStyleSheet(f"QPushButton{{{PILL} color:{TEXT}; padding:8px 16px;}}")
        refresh.clicked.connect(self._refresh_insights)
        lay.addWidget(refresh, alignment=Qt.AlignLeft)
        lay.addStretch(1)
        return page

    def _settings_page(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(28, 24, 28, 24)
        title = QLabel("Settings"); title.setFont(QFont("Segoe UI Variable Display", 18, QFont.DemiBold))
        lay.addWidget(title)
        card = QFrame(); card.setStyleSheet(f"QFrame{{{GLASS}}}")
        cl = QVBoxLayout(card); cl.setSpacing(10)
        cl.addWidget(self._muted("Spoken voice"))
        self.voice_box = QComboBox()
        self.voice_box.addItems(voice.list_voices() or ["(none found)"])
        self.voice_box.currentTextChanged.connect(self._set_voice)
        self.voice_box.setStyleSheet(f"QComboBox{{background:transparent;color:{TEXT};border:1px solid {BORDER};"
                                     f"border-radius:10px;padding:6px 10px;}}")
        cl.addWidget(self.voice_box)
        cl.addWidget(self._muted(f"Provider: {PROVIDER} · model: {MODEL_NAME}"))
        check = QPushButton("Check service")
        check.setStyleSheet(f"QPushButton{{{PILL} color:{TEXT}; padding:8px 16px;}}")
        check.clicked.connect(self._check_service)
        cl.addWidget(check, alignment=Qt.AlignLeft)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _muted(self, text):
        label = QLabel(text); label.setStyleSheet(f"color:{MUTED};font-size:12px;")
        return label

    # ------------------------------------------------------------ pages
    def _page(self, key):
        self.stack.setCurrentIndex({"home": 0, "tasks": 1, "insights": 2, "settings": 3}[key])
        for name, btn in self.nav_buttons.items():
            btn.active = (name == key)
            btn.update()
        if key == "tasks":
            self._refresh_tasks()
        elif key == "insights":
            self._refresh_insights()

    def _refresh_tasks(self):
        rows = self.assistant.reminders.list()
        if rows:
            self.tasks_body.setText("<br>".join(
                f"• {r['message']} — {str(r['due']).replace('T', ' ')}" for r in rows))
        else:
            self.tasks_body.setText("No reminders yet. Say “remind me in 10 minutes…”.")

    def _refresh_insights(self):
        import audit
        rows = audit.recent(200)
        counts = {}
        for r in rows:
            counts[r.get("tool", "?")] = counts.get(r.get("tool", "?"), 0) + 1
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lines = [f"<b>{len(rows)}</b> actions logged."]
        if top:
            lines.append("<br><br>Most used:")
            lines += [f"<br>• {name} — {count}" for name, count in top]
        recent = [f"{r['ts'][11:16]} {r['tool']}" for r in rows[-5:]]
        if recent:
            lines.append("<br><br>Recent: " + ", ".join(reversed(recent)))
        self.insight_body.setText("".join(lines))

    # ------------------------------------------------------------ chat
    def _add_bubble(self, role, text):
        b = Bubble(text, role)
        hb = QHBoxLayout()
        if role == "user":
            hb.addStretch(1); hb.addWidget(b)
        else:
            hb.addWidget(b); hb.addStretch(1)
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, hb)
        self._current = b
        QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _stream_chunk(self, chunk):
        if self._current is not None and self._current.role == "assistant":
            self._current.append(chunk)

    def _set_reply(self, text):
        if self._current is not None and self._current.role == "assistant":
            if not self._current.label.text().strip():
                self._current.label.setText(text)
        else:
            self._add_bubble("assistant", text)

    # ------------------------------------------------------------ actions
    def _send_text(self, text):
        text = (text or "").strip()
        if not text:
            return
        self.entry.clear()
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()

    def _run_turn(self, text):
        self.add_bubble.emit("user", text)
        self.add_bubble.emit("assistant", "")
        self._spoken = []
        self.mode_sig.emit("processing", "")
        try:
            reply = self.assistant.ask(text)
        except Exception as e:
            self.mode_sig.emit("idle", "")
            self.add_bubble.emit("assistant", f"⚠ {str(e)[:200]}")
            return
        reply = (reply or "").strip()
        if not reply:
            self.mode_sig.emit("idle", "")
            return
        self.reply_sig.emit(reply)
        self.mode_sig.emit("speaking", "")
        try:
            voice.speak(reply)
        except Exception:
            pass
        self.mode_sig.emit("idle", "")

    def toggle_talk(self):
        if self.mode == "listening":
            self._finish_listening()
        elif self.mode in ("idle", "error"):
            self._start_listening()

    def _start_listening(self):
        self.heard_sig.emit("")
        self.mic = MicStream(); self.mic.start()
        self._started = time.time(); self._silence_since = None
        self.mode_sig.emit("listening", "")
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        while self.mode == "listening":
            time.sleep(0.06)
            if self.mic is None:
                return
            if self.mic.error:
                self.mode_sig.emit("error", self.mic.error); return
            self.level_sig.emit(self.mic.level)
            now = time.time()
            if self.mic.level > 0.06:
                self._silence_since = None
            elif self._silence_since is None:
                self._silence_since = now
            elif now - self._silence_since > 1.2:
                self._finish_listening(); return
            if now - self._started > 12:
                self._finish_listening(); return

    def _finish_listening(self):
        mic, self.mic = self.mic, None
        self.mode_sig.emit("processing", "")
        if mic is None:
            return
        wav = mic.stop()
        threading.Thread(target=self._transcribe, args=(wav,), daemon=True).start()

    def _transcribe(self, wav):
        text, err = voice.transcribe_wav(wav)
        if err or not text:
            self.mode_sig.emit("idle", "")
            return
        self.heard_sig.emit("")
        self._run_turn(text)

    # ------------------------------------------------------------ slots
    def _apply_mode(self, mode, hint):
        self.mode = mode
        self.orb.mode = {"processing": "processing"}.get(mode, mode)
        self.status.setText({"idle": "Tap to talk", "listening": "Listening…",
                             "processing": "Thinking…", "speaking": "Speaking…",
                             "error": "Something went wrong"}.get(mode, "Tap to talk"))
        if mode in ("listening", "processing"):
            self.overlay.setVisible(True)
            self.overlay.setText(hint or ("Listening…" if mode == "listening" else "Thinking…"))

    def _apply_level(self, level):
        self.orb.level = level

    # ------------------------------------------------------------ misc
    def _set_voice(self, name):
        from config import save_setting
        save_setting("voice_name", name)

    def _check_service(self):
        import api_check
        threading.Thread(target=api_check.main, daemon=True).start()

    def _toggle_compact(self):
        if self.width() > 700:
            self.side.hide(); self.stack.setFixedHeight(340)
            self.resize(460, 420)
        else:
            self.side.show(); self.stack.setFixedHeight(16777215)
            self.resize(1080, 720)

    def _toggle_visible(self):
        self.hide() if self.isVisible() else self.show()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and not self.entry.hasFocus():
            self.toggle_talk()
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------ assistant
    def _on_text(self, chunk):
        self._spoken.append(chunk)
        self.stream_sig.emit(chunk)

    def _on_tool(self, name, args, result):
        pass


def main():
    app = QApplication(sys.argv)
    win = Window(); win.assistant.start(); win.assistant.start_watcher(); win.show()
    sys.exit(app.exec())


def _prep(win):
    win.orb.mode = "listening"; win.orb.level = 0.55
    win.status.setText("Listening…")
    win.overlay.setText("listening…")
    win._add_bubble("user", "open notepad")
    win._add_bubble("assistant", "Notepad's open — anything else?")
    win.orb.repaint()


def shot(path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    win = Window(); _prep(win); win.show()
    for _ in range(50):
        win.orb.phase += 0.05; app.processEvents()
    win.grab().save(path); print("saved", path)


def shot_live(path):
    app = QApplication(sys.argv)
    win = Window(); _prep(win); win.show()
    def grab():
        win.grab().save(path); print("saved", path); app.quit()
    QTimer.singleShot(1600, grab)
    app.exec()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--shot":
        shot(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "--shot-live":
        shot_live(sys.argv[2])
    else:
        main()
