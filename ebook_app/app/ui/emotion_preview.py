# ebook_app/app/ui/emotion_preview.py
"""Emotion Preview — shows emotion tags applied to each segment."""
from __future__ import annotations
from typing import Any, Dict, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel,
)


EMOTION_COLORS = {
    "happy":      "#d4edda",
    "sad":        "#cce5ff",
    "angry":      "#f8d7da",
    "fearful":    "#fff3cd",
    "surprised":  "#e2d9f3",
    "disgusted":  "#d1ecf1",
    "whispering": "#e9ecef",
    "neutral":    "#ffffff",
}


class EmotionPreviewWidget(QWidget):
    """Table view showing emotion label per segment with color coding."""

    COLUMNS = ["#", "Emotion", "Type", "Speaker", "Text Preview"]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Emotion Tags</b>"))

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def set_segments(self, segments: List[Dict[str, Any]]):
        from PySide6.QtGui import QColor
        self.table.setRowCount(0)
        for i, seg in enumerate(segments):
            row = self.table.rowCount()
            self.table.insertRow(row)
            emotion = seg.get("emotion", "neutral")
            color = QColor(EMOTION_COLORS.get(emotion, "#ffffff"))
            items = [
                QTableWidgetItem(str(i + 1)),
                QTableWidgetItem(emotion),
                QTableWidgetItem(seg.get("type", "")),
                QTableWidgetItem(seg.get("speaker", "")),
                QTableWidgetItem(seg.get("text", "")[:150]),
            ]
            for col, item in enumerate(items):
                item.setBackground(color)
                self.table.setItem(row, col, item)

    def clear(self):
        self.table.setRowCount(0)
