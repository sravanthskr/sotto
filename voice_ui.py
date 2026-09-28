"""
voice_ui.py - the voice-first desktop app (Flet, pure Python).

Tap the orb, speak, and it answers out loud. The orb is a live audio visualiser: it
breathes when idle, reacts to your voice while listening, orbits while thinking, and
pulses while speaking.

    .\\run.bat ui        (or: python voice_ui.py)
"""

import math
import threading
import time

import flet as ft

import tools
import voice
from audio import MicStream
from config import MODEL_NAME
from core import Assistant

# Apple design-system tokens (dark chapter: absolute black + single blue accent)
BG = "#000000"
SURFACE = "#111113"
TEXT = "#f5f5f7"
MUTED = "#8e8e93"
ACCENT = "#0071e3"
ACCENT_SOFT = "#2997ff"


def _op(color, alpha):
    try:
        return ft.Colors.with_opacity(alpha, color)
    except Exception:
        return color


RING_IDLE = _op(ft.Colors.WHITE, 0.10)
RING_LIVE = _op(ft.Colors.WHITE, 0.30)


class VoiceUI:
    def __init__(self, page: ft.Page):
        self.page = page
        self.assistant = Assistant(on_text=self._on_text, on_tool=self._on_tool,
                                    on_learned=self._on_learned)
        self.mic = None
        self.mode = "idle"            # idle | listening | thinking | speaking | error
        self.level = 0.0              # smoothed
        self._spoken = []
        self._stop_anim = threading.Event()
        self._silence_since = None
        self._listen_started = 0.0
        self._phase = 0.0
        self.settings_note = ft.Text("", size=12, color=MUTED)
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self):
        p = self.page
        p.title = "RealAssistant"
        p.bgcolor = BG
        p.padding = 0
        try:
            p.window.width = 480
            p.window.height = 780
            p.window.min_width = 420
            p.window.min_height = 680
        except Exception:
            pass

        self.rings = []
        for size in (260, 210, 160, 116):
            ring = ft.Container(
                width=size, height=size, border_radius=size,
                border=ft.Border.all(1.5, RING_IDLE),
                alignment=ft.Alignment.CENTER,
                scale=1.0, opacity=0.9,
            )
            self.rings.append(ring)

        self.core = ft.Container(
            width=76, height=76, border_radius=38, bgcolor=ACCENT,
            shadow=ft.BoxShadow(blur_radius=36, color=_op(ACCENT, 0.55)),
            scale=1.0,
        )

        self.orb = ft.GestureDetector(
            content=ft.Stack(controls=self.rings + [self.core],
                             width=280, height=280, alignment=ft.Alignment.CENTER),
            on_tap=lambda e: self.toggle_talk(),
        )

        self.status = ft.Text("Tap to talk", size=17, color=MUTED,
                              weight=ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER)
        self.heard = ft.Text("", size=13, color=MUTED, text_align=ft.TextAlign.CENTER,
                             animate_opacity=300, opacity=0)
        self.reply = ft.Text("", size=15, color=TEXT, text_align=ft.TextAlign.CENTER,
                             animate_opacity=300, opacity=0)

        self.primary = ft.Container(
            content=ft.Text("Tap to talk", size=15, weight=ft.FontWeight.W_600, color="#ffffff"),
            bgcolor=ACCENT, border_radius=980, padding=ft.Padding.symmetric(vertical=16, horizontal=30),
            on_click=lambda e: self.toggle_talk(), ink=True,
        )

        self.footer = ft.Row(
            controls=[
                ft.TextButton("Type instead", on_click=lambda e: self._toggle_type()),
                ft.TextButton("Settings", on_click=lambda e: self._toggle_settings()),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )

        self.typed = ft.TextField(
            hint_text="Type a request and press Enter", autofocus=False,
            on_submit=self._submit_typed, visible=False,
            border=ft.OutlineInputBorder(side=ft.BorderSide(width=1, color=_op(ft.Colors.WHITE, 0.16))),
            color=TEXT, hint_style=ft.TextStyle(color=MUTED), text_size=15, width=360,
        )

        self.settings = ft.Column(visible=False, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                  controls=[
                                      ft.Text("Spoken voice", size=13, color=MUTED),
                                      self._voice_dropdown(),
                                      ft.TextButton("Check the service", on_click=lambda e: self._check_service()),
                                      self.settings_note,
                                  ])

        header = ft.Row(
            controls=[
                ft.Text("RealAssistant", size=15, weight=ft.FontWeight.W_600, color=TEXT),
                ft.Text(f"{MODEL_NAME.split('/')[-1]} · {len(tools.APP_INDEX)} apps",
                        size=11, color=MUTED),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        p.add(ft.Container(
            expand=True, bgcolor=BG, padding=ft.Padding.symmetric(vertical=24, horizontal=28),
            content=ft.Column(
                controls=[
                    header,
                    ft.Container(height=8),
                    ft.Container(content=self.orb, alignment=ft.Alignment.CENTER, expand=True),
                    ft.Container(height=6),
                    self.status,
                    ft.Container(height=10),
                    self.heard,
                    self.reply,
                    ft.Container(height=14),
                    ft.Row([self.primary], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Container(height=6),
                    self.typed,
                    self.settings,
                    ft.Container(height=4),
                    self.footer,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4, expand=True,
            ),
        ))

    def _voice_dropdown(self):
        voices = voice.list_voices() or ["(none found)"]
        self.voice_dd = ft.Dropdown(
            value=voice.default_voice() or voices[0], width=280, options=[
                ft.dropdown.Option(v) for v in voices],
            on_select=self._set_voice,
            border=ft.OutlineInputBorder(side=ft.BorderSide(width=1, color=_op(ft.Colors.WHITE, 0.16))),
            color=TEXT, text_size=14,
        )
        return self.voice_dd

    # --------------------------------------------------------- lifecycle
    def start(self):
        self.assistant.start()
        self.assistant.start_watcher()
        self._anim_thread = threading.Thread(target=self._animate, daemon=True)
        self._anim_thread.start()

    def _anim(self):
        """kept for readability - the animation runs in _animate/_frame."""

    def _animate(self):
        while not self._stop_anim.is_set():
            try:
                self._frame()
            except Exception:
                pass
            time.sleep(1 / 25)

    def _frame(self):
        self._phase += 0.12
        target = self.mic.level if (self.mic and self.mode == "listening") else 0.0
        self.level += (target - self.level) * 0.35

        for idx, ring in enumerate(self.rings):
            depth = (idx + 1) / len(self.rings)
            if self.mode == "listening":
                scale = 1.0 + self.level * (0.28 * depth)
                opacity = 0.35 + self.level * (0.6 * depth)
                color = RING_LIVE if self.level > 0.08 else RING_IDLE
            elif self.mode == "thinking":
                scale = 1.0 + 0.03 * math.sin(self._phase * 0.5 - idx * 0.7)
                opacity = 0.45 + 0.25 * math.sin(self._phase * 0.5 - idx * 0.7)
                color = _op(ACCENT_SOFT, 0.45)
            elif self.mode == "speaking":
                wave = (math.sin(self._phase * 0.9 - idx * 1.1) + 1) / 2
                scale = 1.0 + 0.14 * wave * depth
                opacity = 0.4 + 0.5 * wave
                color = _op(ACCENT, 0.5)
            else:
                breathe = math.sin(self._phase * 0.18) * 0.5 + 0.5
                scale = 1.0 + 0.02 * breathe
                opacity = 0.5 + 0.3 * breathe
                color = RING_IDLE
            ring.scale = scale
            ring.opacity = opacity
            ring.border = ft.Border.all(1.5, color)

        core_target = 1.0
        if self.mode == "listening":
            core_target = 1.0 + self.level * 0.55
        elif self.mode == "speaking":
            core_target = 1.0 + 0.18 * (math.sin(self._phase * 0.9) + 1) / 2
        self.core.scale = core_target
        self.core.shadow = ft.BoxShadow(
            blur_radius=30 + 40 * (self.level if self.mode == "listening" else 0.3),
            color=_op(ACCENT, 0.5))
        self.page.update()

    # ------------------------------------------------------------- state
    def _set_mode(self, mode, status):
        self.mode = mode
        self.status.value = status
        self.status.color = ACCENT_SOFT if mode in ("listening", "speaking") else MUTED
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
        self._set_mode("listening", "Listening…")
        threading.Thread(target=self._watch_silence, daemon=True).start()

    def _watch_silence(self):
        """Auto-stop after ~1.2 s of silence (or 12 s max)."""
        while self.mode == "listening":
            time.sleep(0.1)
            if self.mic is None or self.mic.error:
                self._set_mode("error", "Microphone problem")
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
        mic = self.mic
        self.mic = None
        self._set_mode("thinking", "Thinking…")
        if mic is None:
            return
        wav = mic.stop()
        threading.Thread(target=self._transcribe_and_ask, args=(wav,), daemon=True).start()

    def _transcribe_and_ask(self, wav):
        text, err = voice.transcribe_wav(wav)
        if err:
            self._set_mode("error", f"Couldn't understand audio ({err})")
            return
        if not text:
            self._set_mode("idle", "Tap to talk")
            self._show(heard="Didn't catch that — try again.")
            return
        self._show(heard=f"You: {text}")
        self._run_turn(text)

    def _run_turn(self, text):
        self._spoken = []
        self._set_mode("thinking", "Thinking…")
        try:
            reply = self.assistant.ask(text)
        except Exception as e:
            self._set_mode("error", str(e))
            return
        reply = (reply or "").strip()
        if not reply:
            self._set_mode("idle", "Tap to talk")
            return
        self._show(reply=reply)
        self._set_mode("speaking", "Speaking…")
        try:
            voice.speak(reply)
        except Exception:
            pass
        self._set_mode("idle", "Tap to talk")

    # --------------------------------------------------------- assistant
    def _on_text(self, chunk):
        self._spoken.append(chunk)

    def _on_tool(self, name, args, result):
        self.status.value = f"{name}…"
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

    def _submit_typed(self, e):
        text = (self.typed.value or "").strip()
        if not text:
            return
        self.typed.value = ""
        self._show(heard=f"You: {text}")
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()

    def _toggle_settings(self):
        self.settings.visible = not self.settings.visible
        self.page.update()

    def _set_voice(self, e):
        from config import save_setting
        if save_setting("voice_name", self.voice_dd.value):
            self.settings_note.value = f"Voice set to {self.voice_dd.value} (restart to apply)."
            self.page.update()

    def _check_service(self):
        import api_check
        threading.Thread(target=api_check.main, daemon=True).start()


def main(page: ft.Page):
    ui = VoiceUI(page)
    ui.start()


if __name__ == "__main__":
    ft.run(main)
