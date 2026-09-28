"""
app_qt.py - RealAssistant desktop app (PySide6 / Qt, pure Python).

Voice-first redesign per the design review:
  * layered, "alive" orb (core + inner glow + 3 auras + glowing eyes + specular)
  * fluid gradient waveform (smooth curve, not bars), one rotating particle ring when thinking
  * state-driven visibility - voice dominates; chat history is hidden by default
  * glass surfaces everywhere, floating input pill, staggered quick-action pills

    .\\run.bat ui                        (or: python app_qt.py)
    python app_qt.py --shot out.png      # offscreen render
    python app_qt.py --shot-live out.png # real-window render (fonts included)
"""

import math
import sys
import threading
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QKeySequence, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient, QShortcut)
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton,
                               QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

import tools
import voice
from audio import MicStream
from config import API_BASE_URL, MODEL_NAME
from core import Assistant

# ---------------------------------------------------------------- theme
BASE_TOP = QColor("#0F0F1A")
BASE_BOTTOM = QColor("#0A0A12")
VIOLET = QColor("#8B5CF6")
DEEP_VIOLET = QColor("#6D28D9")
BLUE = QColor("#3B82F6")
CYAN = QColor("#22D3EE")
PINK = QColor("#EC4899")
TEXT = "#FAFAFA"
MUTED = "#A1A1AA"
BORDER = "rgba(255,255,255,0.10)"
PROVIDER = "gemini" if API_BASE_URL else "groq"

GLASS = ("background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
         " stop:0 rgba(255,255,255,0.07), stop:0.4 rgba(24,24,32,0.72),"
         " stop:1 rgba(20,20,28,0.88));"
         " border:1px solid rgba(255,255,255,0.10); border-radius:24px;")
PILL = ("background: rgba(139,92,246,0.16); border:1px solid rgba(139,92,246,0.30);"
        " border-radius:20px;")
PILL_HOVER = ("background: rgba(139,92,246,0.28); border:1px solid rgba(139,92,246,0.55);"
              " border-radius:999px;")

CHIPS = ["Open notepad", "Remind me in 10 minutes", "What's my system status?",
         "Summarise my screen"]
GREETINGS = ["Hey, what's up?", "What's on your mind?", "I'm here — say the word."]


def _lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))


def _mix(c1: QColor, c2: QColor, t):
    t = max(0.0, min(1.0, t))
    return QColor(int(_lerp(c1.red(), c2.red(), t)),
                  int(_lerp(c1.green(), c2.green(), t)),
                  int(_lerp(c1.blue(), c2.blue(), t)))


# ---------------------------------------------------------------- background
class Background(QWidget):
    """Gradient base + a few huge soft colour orbs (the 'blurred blobs' of the spec)."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, BASE_TOP)
        g.setColorAt(1, BASE_BOTTOM)
        p.fillRect(self.rect(), QBrush(g))
        for cx, cy, r, col, alpha in (
                (w * 0.22, h * 0.18, min(w, h) * 0.55, VIOLET, 0.20),
                (w * 0.85, h * 0.30, min(w, h) * 0.50, BLUE, 0.16),
                (w * 0.60, h * 0.95, min(w, h) * 0.55, PINK, 0.12)):
            grad = QRadialGradient(QPointF(cx, cy), r)
            c = QColor(col)
            c.setAlphaF(alpha)
            grad.setColorAt(0, c)
            edge = QColor(col)
            edge.setAlphaF(0.0)
            grad.setColorAt(1, edge)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.end()


# ---------------------------------------------------------------- orb
class Orb(QWidget):
    def __init__(self):
        super().__init__()
        self.mode = "idle"
        self.level = 0.0
        self.phase = 0.0
        self.blink = 0.0
        self.grow = 1.0
        self.setMinimumSize(280, 280)
        t = QTimer(self); t.timeout.connect(self._tick); t.start(16)

    def _tick(self):
        self.phase += 0.045
        beat = self.phase % 3.6
        self.blink = max(0.0, 1.0 - abs(beat - 0.2) / 0.14)
        target = {"idle": 1.0, "listening": 1.45, "processing": 1.20, "speaking": 1.32}[self.mode]
        self.grow = _lerp(self.grow, target, 0.06)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h * 0.52
        base = min(w, h) * 0.15 * self.grow

        live = self.level if self.mode == "listening" else (
            0.45 + 0.30 * (math.sin(self.phase * 1.7) + 1) / 2 if self.mode == "speaking"
            else (0.30 if self.mode == "processing" else 0.06 + 0.03 * math.sin(self.phase * 0.5)))

        # colour identity per state (thinking swirls violet -> pink -> blue)
        if self.mode == "processing":
            t = (math.sin(self.phase * 1.1) + 1) / 2
            c1, c2 = _mix(DEEP_VIOLET, PINK, t), _mix(VIOLET, CYAN, t)
        elif self.mode == "listening":
            c1, c2 = _mix(DEEP_VIOLET, BLUE, 0.7), CYAN
        else:
            c1, c2 = DEEP_VIOLET, BLUE

        # 1) outer aura - three rings, ripples while listening
        ring_specs = ((1.00, 0.40, c1), (1.15, 0.20, c2), (1.30, 0.10, PINK))
        for mult, alpha, col in ring_specs:
            if self.mode == "listening":
                for k in range(3):
                    prog = ((self.phase * 0.35 + k / 3.0) % 1.0)
                    r = base * (1.05 + prog * 0.55)
                    c = QColor(col)
                    c.setAlphaF(max(0.0, (1 - prog) * (0.25 + live * 0.45)))
                    p.setPen(QPen(c, 1.6))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(cx, cy), r, r)
            else:
                c = QColor(col)
                c.setAlphaF(alpha * (0.6 + live * 0.8))
                p.setPen(QPen(c, 1.4))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), base * mult, base * mult)

        # 2) light bleed - a soft radial falloff, never a flat disc
        glow_r = base * 2.5
        gc = QColor(c2 if self.mode == "listening" else c1)
        gc.setAlphaF(0.30 + live * 0.30)
        gmid = QColor(gc); gmid.setAlphaF(0.10)
        gedge = QColor(gc); gedge.setAlphaF(0.0)
        gg = QRadialGradient(QPointF(cx, cy), glow_r)
        gg.setColorAt(0.0, gc); gg.setColorAt(0.55, gmid); gg.setColorAt(1.0, gedge)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(gg))
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # 3) core sphere (+ inner shadow bottom-right for depth)
        grad = QRadialGradient(QPointF(cx - base * 0.32, cy - base * 0.36), base * 1.9)
        grad.setColorAt(0.0, _mix(QColor("#E9E4FF"), c1, 0.30))
        grad.setColorAt(0.50, c1)
        grad.setColorAt(1.0, _mix(c2, QColor("#0B0B18"), 0.45))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), base, base)
        shadow = QRadialGradient(QPointF(cx + base * 0.40, cy + base * 0.44), base * 1.25)
        s0 = QColor(0, 0, 0); s0.setAlphaF(0.0)
        s1 = QColor(0, 0, 0); s1.setAlphaF(0.30)
        shadow.setColorAt(0.45, s0); shadow.setColorAt(1.0, s1)
        p.setBrush(QBrush(shadow))
        p.drawEllipse(QPointF(cx, cy), base, base)

        # rim light (upper-left arc) - makes it read as lit glass
        rim = QColor(255, 255, 255); rim.setAlphaF(0.28 + live * 0.18)
        pen = QPen(rim, 2.0); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - base, cy - base, base * 2, base * 2), 100 * 16, 130 * 16)

        # specular highlight - top-left of the sphere, clear of the eyes
        spec = QColor(255, 255, 255); spec.setAlphaF(0.30)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(spec))
        p.drawEllipse(QRectF(cx - base * 0.58, cy - base * 0.66, base * 0.46, base * 0.26))
        spec2 = QColor(255, 255, 255); spec2.setAlphaF(0.18)
        p.setBrush(QBrush(spec2))
        p.drawEllipse(QRectF(cx - base * 0.44, cy - base * 0.50, base * 0.20, base * 0.12))

        # eyes - equal size, aligned, soft rim so they read as glassy
        eye_w, eye_h = base * 0.26, base * 0.40
        gap = base * 0.52
        open_ = max(0.08, 1.0 - self.blink)
        drift = math.sin(self.phase * 0.35) * base * 0.025 if self.mode == "idle" else 0.0
        rimc = QColor(10, 10, 20); rimc.setAlphaF(0.35)
        for sign in (-1, 1):
            ex = cx + sign * gap / 2 + drift
            p.setBrush(QBrush(rimc))
            p.drawRoundedRect(QRectF(ex - eye_w / 2 - 2, cy - eye_h * open_ / 2 - 2,
                                     eye_w + 4, eye_h * open_ + 4), eye_w / 2 + 2, eye_w / 2 + 2)
            glow = QColor(255, 255, 255); glow.setAlphaF(0.22)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(ex, cy), eye_w * 0.95, max(eye_h * 0.5, eye_h * open_))
            p.setBrush(QBrush(QColor(255, 255, 255, 245)))
            p.drawRoundedRect(QRectF(ex - eye_w / 2, cy - eye_h * open_ / 2,
                                     eye_w, eye_h * open_), eye_w / 2, eye_w / 2)
        p.end()


# ---------------------------------------------------------------- waveform
class Wave(QWidget):
    """One smooth, gradient-curved line (not bars). Rotating particle ring while thinking."""

    N = 90

    def __init__(self):
        super().__init__()
        self.mode = "idle"
        self.level = 0.0
        self.phase = 0.0
        self.amp = 0.0
        self.setFixedHeight(96)

    def _tick(self):
        self.phase += 0.06

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        mid = h / 2
        target = {"idle": 3.0, "listening": 10 + self.level * 46,
                  "processing": 10.0, "speaking": 12 + 0.5 * 34}[self.mode]
        self.amp = _lerp(self.amp, target, 0.18)

        if self.mode == "processing":
            # rotating ring of particles instead of a line
            for i in range(14):
                a = self.phase * 0.9 + i * (2 * math.pi / 14)
                r = min(w, h) * 0.30
                x, y = w / 2 + math.cos(a) * r, mid + math.sin(a) * r * 0.42
                size = 2.2 + 2.0 * ((math.sin(self.phase * 2 + i) + 1) / 2)
                c = _mix(VIOLET, CYAN, (math.sin(self.phase + i * 0.5) + 1) / 2)
                c.setAlphaF(0.85)
                p.setPen(Qt.NoPen); p.setBrush(QBrush(c))
                p.drawEllipse(QPointF(x, y), size, size)
            p.end()
            return

        pts = []
        for i in range(self.N):
            t = i / (self.N - 1)
            env = math.sin(math.pi * t) ** 0.9                     # softer centre
            wave = math.sin(t * math.pi * 3.2 + self.phase * 2.4) * 0.60 \
                + math.sin(t * math.pi * 7.1 - self.phase * 1.7) * 0.40
            pts.append(QPointF(12 + t * (w - 24), mid + wave * self.amp * env))

        path = QPainterPath(pts[0])
        for i in range(1, len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            path.quadTo(a, QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
        path.lineTo(pts[-1])

        grad = QLinearGradient(0, 0, w, 0)
        tr = QColor(VIOLET); tr.setAlphaF(0.0)
        tr2 = QColor(PINK); tr2.setAlphaF(0.0)
        mid_alpha = 0.75 + self.level * 0.25
        v = QColor(VIOLET); v.setAlphaF(mid_alpha)
        b = QColor(BLUE); b.setAlphaF(mid_alpha)
        cy_ = QColor(CYAN); cy_.setAlphaF(mid_alpha)
        pk = QColor(PINK); pk.setAlphaF(mid_alpha)
        grad.setColorAt(0.00, tr)
        grad.setColorAt(0.07, v)
        grad.setColorAt(0.38, b)
        grad.setColorAt(0.68, cy_)
        grad.setColorAt(0.93, pk)
        grad.setColorAt(1.00, tr2)

        # glow layers
        for width, alpha in ((14, 0.10), (9, 0.16), (5.5, 0.28)):
            c = QColor(BLUE); c.setAlphaF(alpha + self.level * 0.16)
            pen = QPen(c, width); pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        pen = QPen(QBrush(grad), 4.0 + self.level * 6.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawPath(path)
        p.end()


# ---------------------------------------------------------------- pills
class Pill(QPushButton):
    def __init__(self, text, onclick):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton{{{PILL} color:#E9E9EF; padding:10px 18px; font-size:13px;}}"
            f"QPushButton:hover{{{PILL_HOVER} color:#fff;}}")
        self.clicked.connect(onclick)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)

    def fade_in(self, delay_ms):
        from PySide6.QtCore import QPropertyAnimation
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        QTimer.singleShot(delay_ms, anim.start)


class MenuButton(QPushButton):
    """Three-line menu icon, drawn (no font glyph)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton{background:transparent;border:0;}")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(TEXT) if self.underMouse() else QColor("#C7C7CC")
        p.setPen(Qt.NoPen); p.setBrush(QBrush(col))
        w, x = 20.0, (self.width() - 20) / 2.0
        for y in (14.0, 19.5, 25.0):
            p.drawRoundedRect(QRectF(x, y, w, 2.2), 1.1, 1.1)
        p.end()


ICON_PATHS = {
    "mic": [(9, 3, 6, 11, 3), "arc", (12, 18, 12, 21)],
}


class IconButton(QPushButton):
    """Monoline vector icons drawn with QPainter (no emoji, no assets)."""

    def __init__(self, kind, tooltip="", accent=False, size=40):
        super().__init__()
        self.kind = kind
        self.accent = accent
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setStyleSheet("QPushButton{background:transparent;border:0;}")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        s = min(w, h) * 0.5
        if self.accent:
            g = QLinearGradient(0, 0, w, h)
            g.setColorAt(0, VIOLET); g.setColorAt(1, BLUE)
            p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(0, 0, w, h))
            col = QColor(255, 255, 255)
        else:
            col = QColor(TEXT) if self.underMouse() else QColor("#C7C7CC")
        pen = QPen(col, 1.7); pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        cx, cy = w / 2, h / 2
        if self.kind == "mic":
            p.drawRoundedRect(QRectF(cx - s * 0.22, cy - s * 0.62, s * 0.44, s * 0.72),
                              s * 0.22, s * 0.22)
            p.drawArc(QRectF(cx - s * 0.46, cy - s * 0.36, s * 0.92, s * 0.78), 180 * 16, 180 * 16)
            p.drawLine(QPointF(cx, cy + s * 0.42), QPointF(cx, cy + s * 0.66))
        elif self.kind == "send":
            p.drawPolygon([QPointF(cx - s * 0.55, cy), QPointF(cx + s * 0.62, cy - s * 0.42),
                           QPointF(cx + s * 0.16, cy + s * 0.58), QPointF(cx - s * 0.12, cy + s * 0.08)])
        else:  # plus
            p.drawLine(QPointF(cx, cy - s * 0.42), QPointF(cx, cy + s * 0.42))
            p.drawLine(QPointF(cx - s * 0.42, cy), QPointF(cx + s * 0.42, cy))
        p.end()


# ---------------------------------------------------------------- window
class Window(QMainWindow):
    mode_sig = Signal(str, str)
    transcript_sig = Signal(str)
    reply_sig = Signal(str)
    level_sig = Signal(float)
    stream_sig = Signal(str)
    history_sig = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RealAssistant")
        self.resize(980, 760); self.setMinimumSize(760, 620)
        self.assistant = Assistant(on_text=self._on_text, on_tool=self._on_tool,
                                    on_learned=lambda f: None)
        self.mic = None
        self.mode = "idle"
        self._spoken = []
        self._silence_since = None
        self._started = 0.0
        self.history = []
        self._build()
        self.mode_sig.connect(self._apply_mode)
        self.transcript_sig.connect(self._set_transcript)
        self.reply_sig.connect(self._set_reply)
        self.level_sig.connect(self._set_level)
        self.stream_sig.connect(self._stream)
        self.history_sig.connect(self._log_history)
        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self._toggle_visible)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._open_menu)

    # ------------------------------------------------------ build
    def _build(self):
        stage = Background()
        self.setCentralWidget(stage)
        root = QVBoxLayout(stage)
        root.setContentsMargins(26, 18, 26, 18)
        root.setSpacing(10)

        # top bar: menu + status
        top = QHBoxLayout()
        self.menu_btn = MenuButton()
        self.menu_btn.setToolTip("Menu (Ctrl+K)")
        self.menu_btn.clicked.connect(self._open_menu)
        top.addWidget(self.menu_btn)
        top.addStretch(1)
        chip = QLabel(f"{PROVIDER} · {MODEL_NAME.split('/')[-1]}")
        chip.setStyleSheet(f"color:#DCDCE4;border:1px solid {BORDER};border-radius:11px;"
                           f"padding:4px 12px;font-size:12px;")
        top.addWidget(chip)
        root.addLayout(top)

        # stage stack (home / tasks / insights / settings / conversation)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._home())
        self.stack.addWidget(self._tasks())
        self.stack.addWidget(self._insights())
        self.stack.addWidget(self._settings())
        self.stack.addWidget(self._conversation())
        root.addWidget(self.stack, 1)

        # chips
        self.chips_row = QHBoxLayout(); self.chips_row.setSpacing(10)
        self.chips_row.addStretch(1)
        for text in CHIPS:
            pill = Pill(text, lambda _=False, t=text: self._send_text(t))
            pill.setVisible(False)
            self.chips_row.insertWidget(self.chips_row.count() - 1, pill)
        self.chips_row.addStretch(1)
        root.addLayout(self.chips_row)

        # floating input pill
        self.bar = QFrame(); self.bar.setStyleSheet(f"QFrame{{{GLASS} border-radius:28px;}}")
        bl = QHBoxLayout(self.bar); bl.setContentsMargins(14, 8, 14, 8); bl.setSpacing(10)
        self.attach = IconButton("plus", "Attach (coming soon)", size=36)
        bl.addWidget(self.attach)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Ask anything…")
        self.entry.setStyleSheet("QLineEdit{background:transparent;border:0;color:#FAFAFA;"
                                 "font-size:15px;font-style:italic;}")
        self.entry.textChanged.connect(self._on_text_changed)
        self.entry.returnPressed.connect(lambda: self._send_text(self.entry.text()))
        bl.addWidget(self.entry, 1)
        self.send = IconButton("send", "Send", size=36)
        self.send.setVisible(False)
        self.send.clicked.connect(lambda: self._send_text(self.entry.text()))
        bl.addWidget(self.send)
        self.mic_btn = IconButton("mic", "Talk", accent=True, size=44)
        self.mic_btn.clicked.connect(self.toggle_talk)
        bl.addWidget(self.mic_btn)
        root.addWidget(self.bar)
        self.bar.installEventFilter(self)

        hint = QLabel("hold Space to talk   ·   Ctrl+Space show / hide   ·   Ctrl+K menu")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#CFCFD8;font-size:12.5px;")
        root.addWidget(hint)
        self._set_visibility("idle")

    def _home(self):
        page = Background()
        lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)

        self.orb = Orb()
        self.wave = Wave()
        timer = QTimer(self); timer.timeout.connect(self.wave._tick); timer.start(16)

        self.state_label = QLabel(GREETINGS[0])
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setFont(QFont("Segoe UI Variable Display", 17, QFont.DemiBold))
        self.state_label.setStyleSheet(f"color:{TEXT};")

        self.reply_label = QLabel("")
        self.reply_label.setAlignment(Qt.AlignCenter)
        self.reply_label.setWordWrap(True)
        self.reply_label.setFont(QFont("Segoe UI Variable Text", 16))
        self.reply_label.setStyleSheet(f"color:{TEXT};")
        self.reply_label.setMaximumWidth(680)

        self.transcript = QLabel("")
        self.transcript.setAlignment(Qt.AlignCenter)
        self.transcript.setStyleSheet(
            "background: rgba(139,92,246,0.20); border:1px solid rgba(139,92,246,0.38);"
            "border-radius:22px; padding:12px 28px; color:#F2F2F6; font-size:15px;")
        self.transcript.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        twrap = QHBoxLayout(); twrap.addStretch(1); twrap.addWidget(self.transcript); twrap.addStretch(1)

        lay.addStretch(2)
        lay.addWidget(self.orb, 5)
        lay.addWidget(self.wave, 1)
        lay.addSpacing(6)
        lay.addWidget(self.state_label)
        lay.addLayout(twrap)
        lay.addWidget(self.reply_label, 0, Qt.AlignHCenter)
        lay.addStretch(2)
        return page

    def _tasks(self):
        page = Background(); lay = QVBoxLayout(page); lay.setContentsMargins(80, 24, 80, 24)
        title = QLabel("Tasks"); title.setFont(QFont("Segoe UI Variable Display", 20, QFont.DemiBold))
        title.setStyleSheet(f"color:{TEXT};")
        lay.addWidget(title)
        self.tasks_body = QLabel("")
        self.tasks_body.setWordWrap(True); self.tasks_body.setStyleSheet("color:#C7C7CC;font-size:14px;")
        card = QFrame(); card.setStyleSheet(f"QFrame{{{GLASS}}}")
        cl = QVBoxLayout(card); cl.addWidget(self.tasks_body)
        lay.addWidget(card); lay.addStretch(1)
        return page

    def _insights(self):
        page = Background(); lay = QVBoxLayout(page); lay.setContentsMargins(80, 24, 80, 24)
        title = QLabel("Insights"); title.setFont(QFont("Segoe UI Variable Display", 20, QFont.DemiBold))
        title.setStyleSheet(f"color:{TEXT};")
        lay.addWidget(title)
        self.insight_body = QLabel("")
        self.insight_body.setWordWrap(True); self.insight_body.setStyleSheet("color:#C7C7CC;font-size:14px;")
        card = QFrame(); card.setStyleSheet(f"QFrame{{{GLASS}}}")
        cl = QVBoxLayout(card); cl.addWidget(self.insight_body)
        lay.addWidget(card); lay.addStretch(1)
        return page

    def _settings(self):
        page = Background(); lay = QVBoxLayout(page); lay.setContentsMargins(80, 24, 80, 24)
        title = QLabel("Settings"); title.setFont(QFont("Segoe UI Variable Display", 20, QFont.DemiBold))
        title.setStyleSheet(f"color:{TEXT};")
        lay.addWidget(title)
        card = QFrame(); card.setStyleSheet(f"QFrame{{{GLASS}}}")
        cl = QVBoxLayout(card); cl.setSpacing(10)
        lbl = QLabel("Spoken voice"); lbl.setStyleSheet("color:#C7C7CC;font-size:13px;")
        cl.addWidget(lbl)
        self.voice_box = QComboBox()
        self.voice_box.addItems(voice.list_voices() or ["(none found)"])
        self.voice_box.currentTextChanged.connect(self._set_voice)
        self.voice_box.setStyleSheet("QComboBox{background:transparent;color:#FAFAFA;"
                                     f"border:1px solid {BORDER};border-radius:12px;padding:7px 12px;}}")
        cl.addWidget(self.voice_box)
        info = QLabel(f"Provider: {PROVIDER}   ·   model: {MODEL_NAME}")
        info.setStyleSheet("color:#C7C7CC;font-size:13px;")
        cl.addWidget(info)
        check = QPushButton("Check service")
        check.setCursor(Qt.PointingHandCursor)
        check.setStyleSheet(f"QPushButton{{{PILL} color:#EDEDF3; padding:9px 18px;}}"
                            f"QPushButton:hover{{{PILL_HOVER}}}")
        check.clicked.connect(self._check_service)
        cl.addWidget(check, Qt.AlignLeft)
        lay.addWidget(card); lay.addStretch(1)
        return page

    def _conversation(self):
        page = Background(); lay = QVBoxLayout(page); lay.setContentsMargins(80, 24, 80, 24)
        title = QLabel("Conversation"); title.setFont(QFont("Segoe UI Variable Display", 20, QFont.DemiBold))
        title.setStyleSheet(f"color:{TEXT};")
        lay.addWidget(title)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:0;}")
        holder = Background()
        self.log_lay = QVBoxLayout(holder); self.log_lay.setContentsMargins(0, 0, 0, 0)
        self.log_lay.setSpacing(10); self.log_lay.addStretch(1)
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll, 1)
        note = QLabel("Hidden by default — voice first. Ctrl+K → Conversation to see it.")
        note.setStyleSheet("color:#9A9AA5;font-size:12px;")
        lay.addWidget(note)
        return page

    # ------------------------------------------------------ menu / pages
    def _open_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu{background:#17171F;color:#EDEDF3;border:1px solid rgba(255,255,255,0.10);"
                           "border-radius:12px;padding:6px;} QMenu::item{padding:7px 18px;border-radius:8px;}"
                           "QMenu::item:selected{background:rgba(139,92,246,0.28);}")
        for label, idx in (("Home", 0), ("Tasks", 1), ("Insights", 2),
                           ("Settings", 3), ("Conversation", 4)):
            menu.addAction(label, lambda i=idx: self._goto(i))
        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def _goto(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 1:
            self._refresh_tasks()
        elif idx == 2:
            self._refresh_insights()

    def _refresh_tasks(self):
        rows = self.assistant.reminders.list()
        self.tasks_body.setText("<br>".join(
            f"• {r['message']} — {str(r['due']).replace('T', ' ')}" for r in rows)
            or "No reminders yet. Try: “Remind me in 10 minutes to stretch”.")

    def _refresh_insights(self):
        import audit
        rows = audit.recent(200)
        counts = {}
        for r in rows:
            counts[r.get("tool", "?")] = counts.get(r.get("tool", "?"), 0) + 1
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lines = [f"<b>{len(rows)}</b> actions logged."]
        if top:
            lines.append("<br><br>Most used:<br>" +
                         "<br>".join(f"• {n} — {c}" for n, c in top))
        self.insight_body.setText("".join(lines))

    # ------------------------------------------------------ visibility
    def _set_visibility(self, mode, hint=""):
        listening = mode == "listening"
        processing = mode == "processing"
        speaking = mode == "speaking"

        self.transcript.setVisible(listening and bool(hint))
        self.wave.setVisible(mode in ("listening", "speaking", "processing"))
        self.reply_label.setVisible(speaking or bool(self.reply_label.text()))
        self.bar.setVisible(not listening)
        self.state_label.setVisible(not listening)
        if listening:
            self.state_label.setText("")
        elif processing:
            self.state_label.setText("Thinking…")
        elif speaking:
            self.state_label.setText("")
        else:
            self.state_label.setText(GREETINGS[int(self.orb.phase) % len(GREETINGS)])
        if not (listening or processing):
            pass
        for i in range(self.chips_row.count()):
            w = self.chips_row.itemAt(i).widget()
            if isinstance(w, Pill):
                show = mode == "idle" and bool(self.history)
                w.setVisible(show)
                if show and w.graphicsEffect().opacity() < 0.05:
                    w.fade_in(120 * i)
        self._apply_menu_cursor()

    def _apply_menu_cursor(self):
        pass

    # ------------------------------------------------------ chat
    def _on_text_changed(self, text):
        self.send.setVisible(bool(text.strip()))

    def _send_text(self, text):
        text = (text or "").strip()
        if not text:
            return
        self.entry.clear()
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()

    def _run_turn(self, text):
        self.history_sig.emit("You", text)
        self._spoken = []
        self.mode_sig.emit("processing", "")
        try:
            reply = self.assistant.ask(text)
        except Exception as e:
            self.mode_sig.emit("idle", "")
            self.transcript_sig.emit("")
            self.reply_label.setText(f"⚠ {str(e)[:180]}")
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

    def _log_history(self, who, text):
        self.history.append((who, text))
        self.history = self.history[-40:]
        row = QLabel(f"<span style='color:#9A9AA5'>{who}</span>&nbsp;&nbsp;{text}")
        row.setWordWrap(True)
        row.setStyleSheet(f"color:{TEXT};background:rgba(255,255,255,0.05);"
                          "border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:11px 14px;")
        self.log_lay.insertWidget(self.log_lay.count() - 1, row)

    def _stream(self, chunk):
        self.reply_label.setText(self.reply_label.text() + chunk)

    def _set_reply(self, text):
        if not self.reply_label.text().strip():
            self.reply_label.setText(text)

    def _set_transcript(self, text):
        self.transcript.setText(text or "")
        self.transcript.setVisible(bool(text))

    def _set_level(self, level):
        self.orb.level = level
        self.wave.level = level

    # ------------------------------------------------------ voice
    def toggle_talk(self):
        if self.mode == "listening":
            self._finish_listening()
        elif self.mode in ("idle", "error"):
            self._start_listening()

    def _start_listening(self):
        self.reply_label.setText("")
        self.mic = MicStream(); self.mic.start()
        self._started = time.time(); self._silence_since = None
        self.mode_sig.emit("listening", "listening…")
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        while self.mode == "listening":
            time.sleep(0.06)
            if self.mic is None:
                return
            if self.mic.error:
                self.mode_sig.emit("idle", "")
                self.reply_label.setText(f"⚠ microphone: {self.mic.error}")
                return
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
        self.transcript_sig.emit("…")
        self.mode_sig.emit("processing", "")
        if mic is None:
            return
        wav = mic.stop()
        threading.Thread(target=self._transcribe, args=(wav,), daemon=True).start()

    def _transcribe(self, wav):
        text, err = voice.transcribe_wav(wav)
        if err or not text:
            self.mode_sig.emit("idle", "")
            self.transcript_sig.emit("")
            return
        self.transcript_sig.emit(f"“{text}”")
        self._run_turn(text)

    # ------------------------------------------------------ slots
    def _apply_mode(self, mode, hint):
        self.mode = mode
        self.orb.mode = mode
        self.wave.mode = mode
        if mode == "listening":
            self.transcript_sig.emit(hint or "listening…")
        if mode in ("listening", "processing"):
            self.reply_label.setText("")
        self._set_visibility(mode, hint)
        if mode == "idle" and self.history:
            for i in range(self.chips_row.count()):
                w = self.chips_row.itemAt(i).widget()
                if isinstance(w, Pill):
                    w.setVisible(True)
                    w.fade_in(140 * i)

    def _toggle_visible(self):
        self.hide() if self.isVisible() else self.show()

    def _set_voice(self, name):
        from config import save_setting
        save_setting("voice_name", name)

    def _check_service(self):
        import api_check
        threading.Thread(target=api_check.main, daemon=True).start()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and not self.entry.hasFocus():
            self.toggle_talk()
        else:
            super().keyPressEvent(e)

    def _on_text(self, chunk):
        self._spoken.append(chunk)
        self.stream_sig.emit(chunk)

    def _on_tool(self, name, args, result):
        pass


def main():
    app = QApplication(sys.argv)
    win = Window(); win.assistant.start(); win.assistant.start_watcher(); win.show()
    sys.exit(app.exec())


def _prep(win, mode="listening"):
    win.orb.mode = mode; win.wave.mode = mode
    win.orb.level = 0.55; win.wave.level = 0.55
    win.transcript_sig.emit("“open notepad”")
    win.reply_label.setText("")
    win.history_sig.emit("You", "open notepad")
    win.history_sig.emit("RA", "Notepad's open — anything else?")
    win._set_visibility(mode, "listening…")
    if mode == "idle":
        win.reply_label.setText("Notepad's open — anything else?")
        for i in range(win.chips_row.count()):
            w = win.chips_row.itemAt(i).widget()
            if isinstance(w, Pill):
                w.setVisible(True)
                w.graphicsEffect().setOpacity(1.0)


def shot(path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    win = Window(); _prep(win); win.show()
    for _ in range(60):
        win.orb.phase += 0.05; win.wave.phase += 0.06
        app.processEvents()
    win.grab().save(path); print("saved", path)


def shot_live(path):
    app = QApplication(sys.argv)
    win = Window(); _prep(win); win.show()
    def grab():
        win.grab().save(path); print("saved", path); app.quit()
    QTimer.singleShot(1700, grab)
    app.exec()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--shot":
        shot(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "--shot-live":
        shot_live(sys.argv[2])
    else:
        main()
