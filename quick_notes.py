"""
quick_notes.py - Floating Quick Note & AI Scratchpad for Sotto.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox
)
import core


class QuickNotesWidget(QDialog):
    """Floating lightweight note widget with built-in fast AI actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sotto Quick Note & AI Scratchpad")
        self.setMinimumSize(500, 400)
        self.setStyleSheet("""
            QDialog { background-color: #0F0F1A; color: #FAFAFA; }
            QTextEdit { background-color: rgba(20, 20, 28, 0.8); border: 1px solid rgba(255,255,255,0.12); border-radius: 12px; padding: 10px; color: #FAFAFA; font-size: 14px; }
            QPushButton { background-color: rgba(139, 92, 246, 0.2); border: 1px solid rgba(139, 92, 246, 0.4); border-radius: 8px; padding: 6px 12px; color: #FAFAFA; font-weight: bold; }
            QPushButton:hover { background-color: rgba(139, 92, 246, 0.4); }
        """)

        layout = QVBoxLayout(self)

        title = QLabel("📝 Quick Note & AI Scratchpad")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #8B5CF6;")
        layout.addWidget(title)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Type your notes here or paste text to summarize/clean up...")
        layout.addWidget(self.editor, 1)

        # AI Toolbar
        ai_bar = QHBoxLayout()
        btn_sum = QPushButton("⚡ Summarize")
        btn_sum.clicked.connect(self._ai_summarize)
        
        btn_bullet = QPushButton("• Bullet Points")
        btn_bullet.clicked.connect(self._ai_bullets)

        btn_fix = QPushButton("✨ Fix Grammar")
        btn_fix.clicked.connect(self._ai_fix_grammar)

        ai_bar.addWidget(btn_sum)
        ai_bar.addWidget(btn_bullet)
        ai_bar.addWidget(btn_fix)
        layout.addLayout(ai_bar)

        # Bottom Bar
        bot_bar = QHBoxLayout()
        btn_copy = QPushButton("📋 Copy All")
        btn_copy.clicked.connect(self._copy)

        btn_clear = QPushButton("🗑 Clear")
        btn_clear.clicked.connect(self.editor.clear)

        bot_bar.addWidget(btn_copy)
        bot_bar.addWidget(btn_clear)
        layout.addLayout(bot_bar)

    def _copy(self):
        text = self.editor.toPlainText()
        if text:
            import PySide6.QtWidgets
            PySide6.QtWidgets.QApplication.clipboard().setText(text)
            QMessageBox.information(self, "Copied", "Copied text to clipboard!")

    def _ai_action(self, prompt_prefix):
        text = self.editor.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty Text", "Please enter some text first.")
            return

        try:
            bot = core.Assistant()
            response = bot.chat(f"{prompt_prefix}:\n\n{text}")
            self.editor.setText(response)
        except Exception as e:
            QMessageBox.critical(self, "AI Action Failed", f"Failed: {e}")

    def _ai_summarize(self):
        self._ai_action("Please summarize the following text concisely")

    def _ai_bullets(self):
        self._ai_action("Convert the following content into clear bullet points")

    def _ai_fix_grammar(self):
        self._ai_action("Fix any grammar, spelling, or phrasing issues in the following text while preserving its meaning")
