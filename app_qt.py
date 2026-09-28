"""
app_qt.py - the voice-first desktop app (PySide6 / Qt, pure Python).

Why Qt: real desktop widgets, a stable API, and a true custom-painted visualiser
(QPainter at 60 fps) that Flet simply can't draw. No browser, no JS, no bridge.

    .\\run.bat ui            (or: python app_qt.py)
    python app_qt.py --shot preview.png     # offscreen render, for a quick look
"""

import math
import sys
import threading
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QPushButton, QVBoxLayout, QWidget)

import tools
import voice
from audio import MicStream
from config import API_BASE_URL, MODEL_NAME
from core import Assistant

BG = "#0a0a0b"
CARD = "#16161a"
TEXT = "#f5f5f7"
MUTED = "#8e8e93"
LINE = "#2b2b30"
ACCENT = "#0a84ff"
ACCENT_2 = "#7cc0ff"
PROVIDER = "gemini" if API_BASE_URL else "groq"


# ---------------------------------------------------------------------------
# the visualiser
# ---------------------------------------------------------------------------
class Orb(QWidget):
    BARS = 44

    def __init__(self):
        super().__init__()
        self.mode = "idle"
        self.level = 0.0
        self.phase = 0.0
        self.setMinimumSize(360, 420)
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(16)                      # ~60 fps

    def _tick(self):
        self.phase += 0.055
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h * 0.40
        base = min(w, h) * 0.155
        live = self.level if self.mode == "listening" else (
            0.45 + 0.3 * (math.sin(self.phase * 1.6) + 1) / 2 if self.mode == "speaking"
            else (0.14 if self.mode == "thinking" else 0.05 + 0.03 * math.sin(self.phase * 0.35)))

        # --- glow ---
        glow_r = base * (2.6 + live * 1.6)
        grad = QRadialGradient(QPointF(cx, cy), glow_r)
        col = QColor(ACCENT)
        col.setAlphaF(min(0.85, 0.12 + live * 0.55))
        grad.setColorAt(0.0, col)
        edge = QColor(ACCENT)
        edge.setAlphaF(0.0)
        grad.setColorAt(1.0, edge)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # --- rings ---
        for i, mult in enumerate((2.05, 1.62, 1.28, 1.0)):
            r = base * mult * (1.0 + live * 0.20 * (1 - i / 5.0))
            alpha = min(0.9, 0.10 + live * 0.62 * (1 - i / 6.0))
            if self.mode == "thinking":
                c = QColor(ACCENT_2)
                alpha = 0.25 + 0.5 * (math.sin(self.phase * 1.4 - i * 0.8) + 1) / 2
            elif live > 0.08:
                c = QColor(ACCENT)
            else:
                c = QColor(255, 255, 255)
            c.setAlphaF(alpha)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(c, 1.4))
            p.drawEllipse(QPointF(cx, cy), r, r)

        # --- core ---
        core_r = base * (1.0 + live * 0.40)
        cg = QRadialGradient(QPointF(cx - core_r * 0.25, cy - core_r * 0.30), core_r * 1.7)
        cg.setColorAt(0.0, QColor(ACCENT_2))
        cg.setColorAt(1.0, QColor(ACCENT))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(cg))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # --- waveform ---
        n = self.BARS
        span = w * 0.74
        x0 = (w - span) / 2.0
        slot = span / n
        bw = max(2.0, slot * 0.52)
        wy = h * 0.80
        for i in range(n):
            t = i / (n - 1)
            center = 1 - abs(t - 0.5) * 2
            if self.mode == "idle":
                amp = 5 + 9 * center * (0.5 + 0.5 * math.sin(self.phase * 0.9 + i * 0.42))
                a = 0.22
            else:
                amp = 5 + (12 + live * 95) * (0.35 + 0.65 * center) * \
                      (0.35 + 0.65 * (math.sin(self.phase * 2.0 + i * 0.55) + 1) / 2)
                a = min(1.0, 0.30 + 0.65 * center)
            c = QColor(ACCENT if self.mode in ("listening", "thinking") else ACCENT_2)
            c.setAlphaF(a)
            p.setBrush(QBrush(c))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x0 + i * slot, wy - amp / 2, bw, amp), bw / 2, bw / 2)

        p.end()


# ---------------------------------------------------------------------------
# the window
# ---------------------------------------------------------------------------
class Window(QMainWindow):
    mode_sig = Signal(str, str)      # status, hint
    heard_sig = Signal(str)
    reply_sig = Signal(str)
    history_sig = Signal(str, str)
    level_sig = Signal(float)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RealAssistant")
        self.resize(500, 820)
        self.setStyleSheet(f"QMainWindow{{background:{BG};}} QWidget{{color:{TEXT};}}")

        self.assistant = Assistant(on_text=self._on_text, on_tool=self._on_tool,
                                    on_learned=lambda f: None)
        self.mic = None
        self.mode = "idle"
        self._spoken = []
        self._silence_since = None
        self._started = 0.0

        self.orb = Orb()
        self.status = QLabel("Tap to talk")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("Segoe UI Variable Display", 17, QFont.DemiBold))
        self.hint = QLabel("Press the orb, speak, then stop — I'll answer out loud")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setStyleSheet(f"color:{MUTED};")
        self.heard = QLabel("")
        self.heard.setAlignment(Qt.AlignCenter)
        self.heard.setStyleSheet(f"color:{ACCENT_2};")
        self.reply = QLabel("")
        self.reply.setAlignment(Qt.AlignCenter)
        self.reply.setWordWrap(True)
        self.reply.setStyleSheet("font-size:15px;")

        self.primary = QPushButton("Tap to talk")
        self.primary.setCursor(Qt.PointingHandCursor)
        self.primary.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:0;border-radius:24px;"
            f"padding:14px 40px;font-size:15px;font-weight:600;}}"
            f"QPushButton:hover{{background:#2b95ff;}}")
        self.primary.clicked.connect(self.toggle_talk)

        header = QHBoxLayout()
        title = QLabel("RealAssistant")
        title.setFont(QFont("Segoe UI Variable Display", 13, QFont.DemiBold))
        pill = QLabel(f"{PROVIDER} · {MODEL_NAME.split('/')[-1]}")
        pill.setStyleSheet(f"color:{MUTED};border:1px solid {LINE};border-radius:11px;padding:3px 10px;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(pill)

        self.history = QLabel("")
        self.history.setWordWrap(True)
        self.history.setStyleSheet(f"color:{TEXT};background:{CARD};border-radius:14px;padding:14px;")
        self.history.hide()

        self.typed = QLineEdit()
        self.typed.setPlaceholderText("Type a request and press Enter")
        self.typed.setStyleSheet(
            f"QLineEdit{{background:transparent;border:1px solid {LINE};border-radius:10px;"
            f"padding:10px 12px;color:{TEXT};}}")
        self.typed.returnPressed.connect(self._submit_typed)
        self.typed.hide()

        self.settings = QFrame()
        self.settings.setStyleSheet(f"QFrame{{background:{CARD};border-radius:14px;}}")
        sl = QVBoxLayout(self.settings)
        sl.addWidget(self._muted("Spoken voice"))
        self.voice_box = QComboBox()
        self.voice_box.addItems(voice.list_voices() or ["(none found)"])
        self.voice_box.currentTextChanged.connect(self._set_voice)
        sl.addWidget(self.voice_box)
        check = QPushButton("Check service")
        check.setStyleSheet(f"QPushButton{{background:transparent;color:{ACCENT_2};border:0;}}")
        check.setCursor(Qt.PointingHandCursor)
        check.clicked.connect(self._check_service)
        sl.addWidget(check)
        self.settings.hide()

        footer = QHBoxLayout()
        for label, fn in (("Type", self._toggle_type), ("History", self._toggle_history),
                          ("Settings", self._toggle_settings)):
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:transparent;color:{MUTED};border:0;padding:6px 10px;}}"
                            f"QPushButton:hover{{color:{TEXT};}}")
            b.clicked.connect(fn)
            footer.addWidget(b)

        root = QVBoxLayout()
        root.setContentsMargins(26, 22, 26, 18)
        root.addLayout(header)
        root.addWidget(self.orb, 1)
        root.addWidget(self.status)
        root.addWidget(self.hint)
        root.addWidget(self.heard)
        root.addWidget(self.reply)
        root.addSpacing(6)
        root.addWidget(self.primary, alignment=Qt.AlignHCenter)
        root.addSpacing(6)
        root.addWidget(self.history)
        root.addWidget(self.typed)
        root.addWidget(self.settings)
        root.addLayout(footer)

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

        self.mode_sig.connect(self._apply_mode)
        self.heard_sig.connect(lambda t: self.heard.setText(t))
        self.reply_sig.connect(lambda t: self.reply.setText(t))
        self.history_sig.connect(self._append_history)
        self.level_sig.connect(self._apply_level)
        self._history_lines = []

    def _muted(self, text):
        label = QLabel(text)
        label.setStyleSheet(f"color:{MUTED};")
        return label

    # ---------------------------------------------------------- slots
    def _apply_mode(self, mode, hint):
        self.mode = mode
        self.orb.mode = mode
        self.status.setText({"idle": "Tap to talk", "listening": "Listening…",
                             "thinking": "Thinking…", "speaking": "Speaking…",
                             "error": "Something went wrong"}.get(mode, "Tap to talk"))
        self.status.setStyleSheet(f"color:{ACCENT_2 if mode in ('listening','speaking') else TEXT};")
        if hint:
            self.hint.setText(hint)
        self.primary.setText("Stop" if mode == "listening" else "Tap to talk")

    def _apply_level(self, level):
        self.orb.level = level

    def _append_history(self, who, text):
        self._history_lines.append((who, text))
        self._history_lines = self._history_lines[-6:]
        self.history.setText("<br>".join(
            f"<span style='color:{MUTED}'>{who}</span> &nbsp; {t}" for who, t in self._history_lines))

    # ---------------------------------------------------------- actions
    def toggle_talk(self):
        if self.mode == "listening":
            self._finish_listening()
        elif self.mode in ("idle", "error"):
            self._start_listening()

    def _start_listening(self):
        self.heard_sig.emit("")
        self.reply_sig.emit("")
        self.mic = MicStream()
        self.mic.start()
        self._started = time.time()
        self._silence_since = None
        self.mode_sig.emit("listening", "Speak — I'll stop when you pause")
        threading.Thread(target=self._pump_and_watch, daemon=True).start()

    def _pump_and_watch(self):
        while self.mode == "listening":
            time.sleep(0.06)
            if self.mic is None:
                return
            if self.mic.error:
                self.mode_sig.emit("error", self.mic.error)
                return
            self.level_sig.emit(self.mic.level)
            now = time.time()
            if self.mic.level > 0.06:
                self._silence_since = None
            elif self._silence_since is None:
                self._silence_since = now
            elif now - self._silence_since > 1.2:
                self._finish_listening()
                return
            if now - self._started > 12:
                self._finish_listening()
                return

    def _finish_listening(self):
        mic, self.mic = self.mic, None
        self.mode_sig.emit("thinking", "")
        if mic is None:
            return
        wav = mic.stop()
        threading.Thread(target=self._transcribe, args=(wav,), daemon=True).start()

    def _transcribe(self, wav):
        text, err = voice.transcribe_wav(wav)
        if err:
            self.mode_sig.emit("error", err)
            return
        if not text:
            self.mode_sig.emit("idle", "Didn't catch that — try again")
            return
        self.heard_sig.emit(f"You: {text}")
        self.history_sig.emit("You", text)
        self._run_turn(text)

    def _run_turn(self, text):
        self._spoken = []
        self.mode_sig.emit("thinking", "")
        try:
            reply = self.assistant.ask(text)
        except Exception as e:
            self.mode_sig.emit("error", str(e)[:200])
            return
        reply = (reply or "").strip()
        if not reply:
            self.mode_sig.emit("idle", "")
            return
        self.reply_sig.emit(reply)
        self.history_sig.emit("RA", reply)
        self.mode_sig.emit("speaking", "")
        try:
            voice.speak(reply)
        except Exception:
            pass
        self.mode_sig.emit("idle", "Press the orb, speak, then stop — I'll answer out loud")

    # ---------------------------------------------------------- widgets
    def _toggle_type(self):
        self.typed.setVisible(not self.typed.isVisible())

    def _toggle_history(self):
        self.history.setVisible(not self.history.isVisible())

    def _toggle_settings(self):
        self.settings.setVisible(not self.settings.isVisible())

    def _submit_typed(self):
        text = self.typed.text().strip()
        if not text:
            return
        self.typed.clear()
        self.heard_sig.emit(f"You: {text}")
        self.history_sig.emit("You", text)
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()

    def _set_voice(self, name):
        from config import save_setting
        save_setting("voice_name", name)

    def _check_service(self):
        import api_check
        threading.Thread(target=api_check.main, daemon=True).start()

    # ---------------------------------------------------------- misc
    def _on_text(self, chunk):
        self._spoken.append(chunk)

    def _on_tool(self, name, args, result):
        self.hint.setText(f"running {name}…")


def main():
    app = QApplication(sys.argv)
    win = Window()
    win.assistant.start()
    win.assistant.start_watcher()
    win.show()
    sys.exit(app.exec())


def shot(path):
    """Offscreen render so the visualiser can be checked without a screen."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    win = Window()
    win.orb.mode = "listening"
    win.orb.level = 0.55
    win.heard.setText("You: open notepad")
    win.reply.setText("Notepad's open.")
    win.history_sig.emit("You", "open notepad")
    win.history_sig.emit("RA", "Notepad's open.")
    win.show()
    for _ in range(50):           # let the animation advance a few frames
        win.orb.phase += 0.055
        app.processEvents()
    win.grab().save(path)
    print("saved", path)


def shot_live(path):
    """Render a real window briefly (fonts included) and save a screenshot."""
    app = QApplication(sys.argv)
    win = Window()
    win.orb.mode = "listening"
    win.orb.level = 0.55
    win.heard.setText("You: open notepad")
    win.reply.setText("Notepad's open.")
    win.history_sig.emit("You", "open notepad")
    win.history_sig.emit("RA", "Notepad's open.")
    win.history.setVisible(True)
    win.show()

    def grab():
        win.grab().save(path)
        print("saved", path)
        app.quit()

    QTimer.singleShot(1500, grab)
    app.exec()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--shot":
        shot(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "--shot-live":
        shot_live(sys.argv[2])
    else:
        main()
