# src/ebook_app/ui/widgets/confidence_bar.py

from __future__ import annotations
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor
from PySide6.QtCore import Qt


class ConfidenceBar(QWidget):
    """
    A simple horizontal confidence bar (0.0 to 1.0).
    """

    def __init__(self, value: float = 0.0, parent=None):
        super().__init__(parent)
        self.value = max(0.0, min(1.0, value))
        self.setMinimumHeight(12)

    def set_value(self, v: float):
        self.value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, QColor("#333"))

        # Foreground bar
        bar_w = int(w * self.value)
        painter.fillRect(0, 0, bar_w, h, QColor("#4caf50"))
