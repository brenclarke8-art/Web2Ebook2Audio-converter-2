# ebook_app/app/ui/final_preview.py
"""Final Preview — shows the final fully-annotated segments ready for TTS."""
from __future__ import annotations
from typing import Any, Dict, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel,
)


class FinalPreviewWidget(QWidget):
    """Table showing all segment data (type, speaker, emotion, voice, text)."""

    COLUMNS = ["#", "Type", "Speaker", "Emotion", "Voice", "Speed", "Text"]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Final Segments (Ready for TTS)</b>"))

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def set_segments(self, segments: List[Dict[str, Any]]):
        self.table.setRowCount(0)
        for i, seg in enumerate(segments):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(seg.get("type", "")))
            self.table.setItem(row, 2, QTableWidgetItem(seg.get("speaker", "")))
            self.table.setItem(row, 3, QTableWidgetItem(seg.get("emotion", "neutral")))
            self.table.setItem(row, 4, QTableWidgetItem(seg.get("voice", "")))
            speed = seg.get("tts_speed", seg.get("speed", 1.0))
            self.table.setItem(row, 5, QTableWidgetItem(str(speed)))
            self.table.setItem(row, 6, QTableWidgetItem(seg.get("text", "")[:200]))

    def clear(self):
        self.table.setRowCount(0)
