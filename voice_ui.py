"""
voice_ui.py - the voice-first desktop app (Flet, pure Python).

A large reactive orb plus a live waveform: both move with your voice while listening,
while it thinks, and while it speaks. Minimal chrome, real state, and a short history.

    .\\run.bat ui        (or: python voice_ui.py)
"""

import math
import threading
import time

import flet as ft

import tools
import voice
from audio import MicStream
from config import MODEL_NAME, API_BASE_URL
from core import Assistant

# palette - deep black canvas, single blue accent (Apple dark chapter)
BG = "#0a0a0b"
CARD = "#141416"
TEXT = "#f5f5f7"
MUTED = "#8e8e93"
LINE = "#2a2a2e"
ACCENT = "#0a84ff"
ACCENT_2 = "#64b5ff"


def _op(color, alpha):
    try:
        return ft.Colors.with_opacity(alpha, color)
    except Exception:
        return color


PROVIDER = "gemini" if API_BASE_URL else "groq"


class VoiceUI:
    BARS = 44

    def __init__(self, page: ft.Page):
        self.page = page
        self.assistant = Assistant(on_text=self._on_text, on_tool=self._on_tool,
                                    on_learned=self._on_learned)
        self.mic = None
        self.mode = "idle"
        self.level = 0.0
        self._spoken = []
        self._phase = 0.0
        self._stop = threading.Event()
        self._silence_since = None
        self._listen_started = 0.0
        self._history = []
        self.settings_note = ft.Text("", size=12, color=MUTED)
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self):
        p = self.page
        p.title = "RealAssistant"
        p.bgcolor = BG
        p.padding = 0
        for attr, val in (("width", 520), ("height", 820), ("min_width", 460), ("min_height", 720)):
            try:
                setattr(p.window, attr, val)
            except Exception:
                pass

        # --- glow halo (blurred, sits behind the rings) ---
        self.halo = ft.Container(
            width=250, height=250, border_radius=125,
            bgcolor=_op(ACCENT, 0.35), blur=70, scale=1.0,
        )

        # --- concentric rings ---
        self.rings = []
        for i, size in enumerate((330, 280, 232, 186)):
            ring = ft.Container(
                width=size, height=size, border_radius=size,
                border=ft.Border.all(1.4, _op(ft.Colors.WHITE, 0.16)),
                scale=1.0, opacity=0.9,
            )
            self.rings.append(ring)

        # --- core ---
        self.core = ft.Container(
            width=126, height=126, border_radius=63,
            gradient=ft.RadialGradient(
                colors=[ACCENT_2, ACCENT], radius=0.9,
                center=ft.Alignment(-0.2, -0.3)),
            shadow=ft.BoxShadow(blur_radius=44, color=_op(ACCENT, 0.75)),
            scale=1.0,
        )

        self.orb = ft.GestureDetector(
            on_tap=lambda e: self.toggle_talk(),
            content=ft.Stack(
                width=360, height=360, alignment=ft.Alignment.CENTER,
                controls=[self.halo] + self.rings + [self.core]),
        )

        # --- live waveform ---
        self.bars = []
        for i in range(self.BARS):
            bar = ft.Container(width=4, height=8, border_radius=2,
                               bgcolor=_op(ACCENT, 0.45))
            self.bars.append(bar)
        self.wave = ft.Container(
            content=ft.Row(self.bars, spacing=4, alignment=ft.MainAxisAlignment.CENTER,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=96, alignment=ft.Alignment.CENTER,
        )

        self.status = ft.Text("Tap to talk", size=20, color=TEXT,
                              weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER)
        self.hint = ft.Text("Press the orb, speak, then stop — I'll answer out loud",
                            size=12, color=MUTED, text_align=ft.TextAlign.CENTER)
        self.heard = ft.Text("", size=13, color=ACCENT_2, text_align=ft.TextAlign.CENTER,
                             animate_opacity=200, opacity=0)
        self.reply = ft.Text("", size=15, color=TEXT, text_align=ft.TextAlign.CENTER,
                             animate_opacity=200, opacity=0)

        self.primary = ft.Container(
            content=ft.Text("Tap to talk", size=15, weight=ft.FontWeight.W_600, color="#ffffff"),
            bgcolor=ACCENT, border_radius=980, ink=True,
            padding=ft.Padding.symmetric(vertical=17, horizontal=38),
            on_click=lambda e: self.toggle_talk(),
        )

        self.history_box = ft.Column(spacing=6, visible=False)
        self.history_card = ft.Container(
            content=ft.Column([
                ft.Text("Recent", size=12, color=MUTED),
                self.history_box,
            ], spacing=8),
            bgcolor=CARD, border_radius=16, padding=16, visible=False,
        )

        self.typed = ft.TextField(
            hint_text="Type a request and press Enter", visible=False,
            on_submit=self._submit_typed, color=TEXT, text_size=15,
            hint_style=ft.TextStyle(color=MUTED),
            border=ft.OutlineInputBorder(side=ft.BorderSide(width=1, color=_op(ft.Colors.WHITE, 0.14))),
        )

        self.settings = ft.Column(visible=False, spacing=10,
                                  horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        self._build_settings()

        header = ft.Row(
            controls=[
                ft.Text("RealAssistant", size=15, weight=ft.FontWeight.W_600, color=TEXT),
                ft.Container(
                    content=ft.Text(f"{PROVIDER} · {MODEL_NAME.split('/')[-1]}",
                                    size=11, color=MUTED),
                    border=ft.Border.all(1, LINE), border_radius=980,
                    padding=ft.Padding.symmetric(vertical=5, horizontal=12)),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        footer = ft.Row(controls=[
            ft.TextButton("Type", on_click=lambda e: self._toggle_type(), style=ft.ButtonStyle(color=MUTED)),
            ft.TextButton("History", on_click=lambda e: self._toggle_history(), style=ft.ButtonStyle(color=MUTED)),
            ft.TextButton("Settings", on_click=lambda e: self._toggle_settings(), style=ft.ButtonStyle(color=MUTED)),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=2)

        p.add(ft.Container(
            expand=True, bgcolor=BG,
            padding=ft.Padding.symmetric(vertical=22, horizontal=26),
            content=ft.Column(
                spacing=6, expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    header,
                    ft.Container(content=self.orb, alignment=ft.Alignment.CENTER, expand=True),
                    self.status,
                    self.hint,
                    ft.Container(height=6),
                    self.wave,
                    self.heard,
                    self.reply,
                    ft.Container(height=10),
                    ft.Row([self.primary], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Container(height=8),
                    self.history_card,
                    self.typed,
                    self.settings,
                    footer,
                ],
            ),
        ))

    def _build_settings(self):
        voices = voice.list_voices() or ["(none found)"]
        self.voice_dd = ft.Dropdown(
            value=voice.default_voice() or voices[0], width=280,
            options=[ft.dropdown.Option(v) for v in voices],
            on_select=self._set_voice, color=TEXT, text_size=14,
            border=ft.OutlineInputBorder(side=ft.BorderSide(width=1, color=_op(ft.Colors.WHITE, 0.14))),
        )
        self.settings.controls = [
            ft.Text("Spoken voice", size=12, color=MUTED),
            self.voice_dd,
            ft.Container(
                content=ft.Row([
                    ft.Text(f"provider: {PROVIDER}", size=12, color=MUTED),
                    ft.TextButton("Check service", on_click=lambda e: self._check_service(),
                                  style=ft.ButtonStyle(color=ACCENT_2)),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=CARD, border_radius=12, padding=ft.Padding.symmetric(vertical=6, horizontal=14)),
            self.settings_note,
        ]

    # --------------------------------------------------------- lifecycle
    def start(self):
        self.assistant.start()
        self.assistant.start_watcher()
        threading.Thread(target=self._animate, daemon=True).start()

    def _animate(self):
        while not self._stop.is_set():
            try:
                self._frame()
            except Exception:
                pass
            time.sleep(1 / 30)

    def _frame(self):
        self._phase += 0.10
        target = self.mic.level if (self.mic and self.mode == "listening") else 0.0
        self.level += (target - self.level) * 0.30

        if self.mode == "listening":
            live, color, boost = self.level, ACCENT, 1.0
        elif self.mode == "speaking":
            live, color, boost = 0.45 + 0.35 * (math.sin(self._phase * 1.6) + 1) / 2, ACCENT_2, 0.9
        elif self.mode == "thinking":
            live, color, boost = 0.16, _op(ACCENT_2, 0.8), 0.35
        else:
            live, color, boost = 0.06 + 0.03 * math.sin(self._phase * 0.35), _op(ACCENT, 0.7), 0.25

        # halo breath
        self.halo.scale = 0.85 + live * 0.9 + 0.05 * math.sin(self._phase * 0.5)
        self.halo.bgcolor = _op(ACCENT, 0.18 + live * 0.45)
        self.halo.blur = 60 + live * 45

        # rings
        for i, ring in enumerate(self.rings):
            depth = (i + 1) / len(self.rings)
            if self.mode == "thinking":
                wave = (math.sin(self._phase * 1.2 - i * 0.8) + 1) / 2
                ring.scale = 1.0 + 0.05 * wave
                ring.opacity = 0.35 + 0.5 * wave
                ring.border = ft.Border.all(1.6, _op(ACCENT_2, 0.7))
            else:
                ring.scale = 1.0 + live * (0.30 * depth)
                ring.opacity = 0.25 + live * (0.85 * depth)
                ring.border = ft.Border.all(1.4, color if live > 0.10 else _op(ft.Colors.WHITE, 0.18))

        # core
        self.core.scale = 1.0 + live * 0.42
        self.core.shadow = ft.BoxShadow(blur_radius=30 + live * 70, color=_op(ACCENT, 0.45 + live * 0.4))

        # waveform
        n = len(self.bars)
        mid = (n - 1) / 2
        for i, bar in enumerate(self.bars):
            center = 1 - abs(i - mid) / mid
            variation = (math.sin(self._phase * 2.1 + i * 0.55) + 1) / 2
            if self.mode == "idle":
                height = 6 + 10 * center * (0.4 + 0.6 * variation)
                alpha = 0.25
            else:
                height = 6 + (14 + live * 78) * (0.35 + 0.65 * center) * (0.35 + 0.65 * variation)
                alpha = 0.35 + 0.55 * center
            bar.height = max(5.0, height)
            bar.bgcolor = _op(color if self.mode != "idle" else ACCENT, alpha)
        self.page.update()

    # ------------------------------------------------------------- state
    def _set_mode(self, mode, status=None, hint=None):
        self.mode = mode
        if status:
            self.status.value = status
            self.status.color = ACCENT_2 if mode in ("listening", "speaking") else TEXT
        if hint is not None:
            self.hint.value = hint
        self.primary.content.value = "Stop" if mode == "listening" else "Tap to talk"
        self.page.update()

    def _show(self, heard=None, reply=None):
        if heard is not None:
            self.heard.value = heard
            self.heard.opacity = 1 if heard else 0
        if reply is not None:
            self.reply.value = reply
            self.reply.opacity = 1 if reply else 0
        self.page.update()

    def _add_history(self, who, text):
        self._history.append((who, text))
        self._history = self._history[-6:]
        self.history_box.controls = [
            ft.Row([
                ft.Text(who, size=11, color=ACCENT_2 if who == "RA" else MUTED, width=24),
                ft.Text(text, size=13, color=TEXT, selectable=True, expand=True),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)
            for who, text in self._history
        ]

    # -------------------------------------------------------------- talk
    def toggle_talk(self):
        if self.mode == "listening":
            self._finish_listening()
        elif self.mode in ("idle", "error"):
            self._start_listening()

    def _start_listening(self):
        self._show(heard="", reply="")
        self.mic = MicStream()
        self.mic.start()
        self._listen_started = time.time()
        self._silence_since = None
        self._set_mode("listening", "Listening…", "Speak — I'll stop when you pause")
        threading.Thread(target=self._watch_silence, daemon=True).start()

    def _watch_silence(self):
        while self.mode == "listening":
            time.sleep(0.08)
            if self.mic is None:
                return
            if self.mic.error:
                self._set_mode("error", "Microphone problem", self.mic.error)
                return
            now = time.time()
            if self.mic.level > 0.06:
                self._silence_since = None
            elif self._silence_since is None:
                self._silence_since = now
            elif now - self._silence_since > 1.2:
                self._finish_listening()
                return
            if now - self._listen_started > 12:
                self._finish_listening()
                return

    def _finish_listening(self):
        mic, self.mic = self.mic, None
        self._set_mode("thinking", "Thinking…", "")
        if mic is None:
            return
        wav = mic.stop()
        threading.Thread(target=self._transcribe_and_ask, args=(wav,), daemon=True).start()

    def _transcribe_and_ask(self, wav):
        text, err = voice.transcribe_wav(wav)
        if err:
            self._set_mode("error", "Couldn't read that audio", err)
            return
        if not text:
            self._set_mode("idle", "Tap to talk", "Didn't catch that — try again")
            return
        self._show(heard=f"You: {text}")
        self._add_history("You", text)
        self._run_turn(text)

    def _run_turn(self, text):
        self._spoken = []
        self._set_mode("thinking", "Thinking…", "")
        try:
            reply = self.assistant.ask(text)
        except Exception as e:
            self._set_mode("error", "Service error", str(e)[:180])
            return
        reply = (reply or "").strip()
        if not reply:
            self._set_mode("idle", "Tap to talk", "")
            return
        self._show(reply=reply)
        self._add_history("RA", reply)
        self._set_mode("speaking", "Speaking…", "")
        try:
            voice.speak(reply)
        except Exception:
            pass
        self._set_mode("idle", "Tap to talk", "Press the orb, speak, then stop — I'll answer out loud")

    # --------------------------------------------------------- assistant
    def _on_text(self, chunk):
        self._spoken.append(chunk)

    def _on_tool(self, name, args, result):
        self.hint.value = f"running {name}…"
        try:
            self.page.update()
        except Exception:
            pass

    def _on_learned(self, facts):
        pass

    # ------------------------------------------------------------- extras
    def _toggle_type(self):
        self.typed.visible = not self.typed.visible
        self.page.update()

    def _toggle_history(self):
        self.history_card.visible = not self.history_card.visible
        self.page.update()

    def _toggle_settings(self):
        self.settings.visible = not self.settings.visible
        self.page.update()

    def _submit_typed(self, e):
        text = (self.typed.value or "").strip()
        if not text:
            return
        self.typed.value = ""
        self._show(heard=f"You: {text}")
        self._add_history("You", text)
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()

    def _set_voice(self, e):
        from config import save_setting
        if save_setting("voice_name", self.voice_dd.value):
            self.settings_note.value = f"Voice set to {self.voice_dd.value} — restart to apply."
            self.page.update()

    def _check_service(self):
        import api_check
        self.settings_note.value = "checking…"
        self.page.update()
        threading.Thread(target=api_check.main, daemon=True).start()


def main(page: ft.Page):
    VoiceUI(page).start()


if __name__ == "__main__":
    ft.run(main)
