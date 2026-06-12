# ebook_app/app/ui/translation_preview.py
"""Translation Preview — side-by-side original and translated text."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QSplitter
)
from PySide6.QtCore import Qt


class TranslationPreviewWidget(QWidget):
    """Side-by-side view of original and translated chapter text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Translation Preview</b>"))

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Original"))
        self.original_view = QTextEdit()
        self.original_view.setReadOnly(True)
        ll.addWidget(self.original_view)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Translated"))
        self.translated_view = QTextEdit()
        self.translated_view.setReadOnly(True)
        rl.addWidget(self.translated_view)

        splitter.addWidget(left)
        splitter.addWidget(right)
        layout.addWidget(splitter)

    def set_content(self, original: str, translated: str):
        self.original_view.setPlainText(original)
        self.translated_view.setPlainText(translated)

    def clear(self):
        self.original_view.clear()
        self.translated_view.clear()
