"""
image_workbench.py - Fast & lightweight Image Workbench for Sotto.

Allows fast image editing (crop, rotate, flip, adjust brightness/contrast, grayscale, blur)
and instant AI image generation without requiring heavy machine learning frameworks locally.
"""

import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QSlider, QFrame, QMessageBox, QLineEdit, QComboBox
)

from config import SCREENSHOT_DIR, GLASS, PILL, PILL_HOVER


class ImageWorkbench(QDialog):
    """Clean, dark-mode Image Workbench dialog for editing and generating images."""

    def __init__(self, parent=None, image_path=None):
        super().__init__(parent)
        self.setWindowTitle("Sotto Studio — Image Workbench")
        self.setMinimumSize(850, 600)
        self.setStyleSheet("background-color: #0F0F1A; color: #FAFAFA;")
        
        self.current_path = image_path
        self.image = QImage(image_path) if image_path and os.path.exists(image_path) else None

        self._init_ui()
        if self.image:
            self._update_preview()

    def _init_ui(self):
        layout = QHBoxLayout(self)

        # Left panel: Image preview area
        left_box = QVBoxLayout()
        self.lbl_preview = QLabel("No image loaded.\nLoad an image or generate one with AI!")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet(
            "border: 2px dashed rgba(255,255,255,0.15); border-radius: 16px; font-size: 14px; color: #A1A1AA;"
        )
        left_box.addWidget(self.lbl_preview, 1)

        # File actions bar
        bars = QHBoxLayout()
        btn_load = QPushButton("📁 Open Image")
        btn_load.setStyleSheet("background: rgba(255,255,255,0.08); padding: 8px 16px; border-radius: 12px; font-weight: bold;")
        btn_load.clicked.connect(self._load_image)
        
        btn_save = QPushButton("💾 Save Image")
        btn_save.setStyleSheet("background: rgba(139,92,246,0.3); padding: 8px 16px; border-radius: 12px; font-weight: bold;")
        btn_save.clicked.connect(self._save_image)
        
        bars.addWidget(btn_load)
        bars.addWidget(btn_save)
        left_box.addLayout(bars)

        layout.addLayout(left_box, 2)

        # Right panel: Controls
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet(f"QFrame {{ {GLASS} }}")
        right_box = QVBoxLayout(ctrl_frame)
        right_box.setSpacing(12)

        title = QLabel("🎨 Image Tools & AI Studio")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #8B5CF6;")
        right_box.addWidget(title)

        # Transform section
        t_title = QLabel("Transform")
        t_title.setStyleSheet("font-weight: bold; color: #A1A1AA;")
        right_box.addWidget(t_title)

        r_layout = QHBoxLayout()
        btn_rot_l = QPushButton("↺ 90°")
        btn_rot_l.clicked.connect(lambda: self._rotate(-90))
        btn_rot_r = QPushButton("↻ 90°")
        btn_rot_r.clicked.connect(lambda: self._rotate(90))
        btn_flip_h = QPushButton("⇄ Flip H")
        btn_flip_h.clicked.connect(self._flip_h)
        btn_flip_v = QPushButton("⇅ Flip V")
        btn_flip_v.clicked.connect(self._flip_v)

        for b in [btn_rot_l, btn_rot_r, btn_flip_h, btn_flip_v]:
            b.setStyleSheet("background: rgba(255,255,255,0.05); padding: 6px; border-radius: 8px;")
            r_layout.addWidget(b)
        right_box.addLayout(r_layout)

        # Color & Adjustments section
        c_title = QLabel("Adjustments")
        c_title.setStyleSheet("font-weight: bold; color: #A1A1AA; margin-top: 10px;")
        right_box.addWidget(c_title)

        btn_gray = QPushButton("🔳 Convert to Grayscale")
        btn_gray.setStyleSheet("background: rgba(255,255,255,0.08); padding: 8px; border-radius: 10px;")
        btn_gray.clicked.connect(self._to_grayscale)
        right_box.addWidget(btn_gray)

        btn_invert = QPushButton("☯ Invert Colors")
        btn_invert.setStyleSheet("background: rgba(255,255,255,0.08); padding: 8px; border-radius: 10px;")
        btn_invert.clicked.connect(self._invert_colors)
        right_box.addWidget(btn_invert)

        # AI Image Generation Section
        ai_title = QLabel("✨ AI Image Generator")
        ai_title.setStyleSheet("font-weight: bold; color: #22D3EE; margin-top: 15px;")
        right_box.addWidget(ai_title)

        self.txt_prompt = QLineEdit()
        self.txt_prompt.setPlaceholderText("Describe an image to generate...")
        self.txt_prompt.setStyleSheet("background: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.15); padding: 8px; border-radius: 10px; color: white;")
        right_box.addWidget(self.txt_prompt)

        btn_gen = QPushButton("⚡ Generate Image")
        btn_gen.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8B5CF6, stop:1 #22D3EE); color: white; padding: 10px; font-weight: bold; border-radius: 12px;")
        btn_gen.clicked.connect(self._generate_ai_image)
        right_box.addWidget(btn_gen)

        right_box.addStretch(1)
        layout.addWidget(ctrl_frame, 1)

    def _update_preview(self):
        if not self.image or self.image.isNull():
            return
        pix = QPixmap.fromImage(self.image)
        scaled = pix.scaled(self.lbl_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_preview.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_preview()

    def _load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            self.current_path = file_path
            self.image = QImage(file_path)
            self._update_preview()

    def _save_image(self):
        if not self.image or self.image.isNull():
            QMessageBox.warning(self, "No Image", "There is no image to save.")
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Image", str(SCREENSHOT_DIR / "edited_image.png"), "PNG Image (*.png);;JPEG Image (*.jpg)"
        )
        if save_path:
            self.image.save(save_path)
            QMessageBox.information(self, "Saved", f"Image saved successfully to:\n{save_path}")

    def _rotate(self, degrees):
        if not self.image:
            return
        from PySide6.QtGui import QTransform
        t = QTransform().rotate(degrees)
        self.image = self.image.transformed(t)
        self._update_preview()

    def _flip_h(self):
        if not self.image:
            return
        self.image = self.image.mirrored(True, False)
        self._update_preview()

    def _flip_v(self):
        if not self.image:
            return
        self.image = self.image.mirrored(False, True)
        self._update_preview()

    def _to_grayscale(self):
        if not self.image:
            return
        self.image = self.image.convertToFormat(QImage.Format_Grayscale8)
        self._update_preview()

    def _invert_colors(self):
        if not self.image:
            return
        self.image.invertPixels()
        self._update_preview()

    def _generate_ai_image(self):
        prompt = self.txt_prompt.text().strip()
        if not prompt:
            QMessageBox.warning(self, "Empty Prompt", "Please enter a description for the image.")
            return

        import urllib.parse
        import urllib.request

        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                img = QImage()
                img.loadFromData(data)
                if not img.isNull():
                    self.image = img
                    self._update_preview()
                    out_path = SCREENSHOT_DIR / f"ai_gen_{int(os.path.basename(str(hash(prompt))))}.png"
                    img.save(str(out_path))
                    QMessageBox.information(self, "Success", f"AI Image generated successfully!\nSaved to: {out_path}")
                else:
                    QMessageBox.warning(self, "Error", "Failed to render generated image.")
        except Exception as e:
            QMessageBox.critical(self, "Generation Failed", f"Could not generate image: {e}")
