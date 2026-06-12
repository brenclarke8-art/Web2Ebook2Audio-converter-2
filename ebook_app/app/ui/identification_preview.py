# ebook_app/app/ui/identification_preview.py
"""Identification Preview — shows speaker identification and character assignment."""
from __future__ import annotations
from typing import Any, Dict, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel,
)


class IdentificationPreviewWidget(QWidget):
    """Table view showing speaker assignments and confidence scores."""

    COLUMNS = ["#", "Speaker", "Type", "Gender", "Confidence", "Voice", "Text Preview"]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Speaker Identification</b>"))

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
            conf = seg.get("speaker_confidence", seg.get("character_confidence", 0.0))
            self.table.setItem(row, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(seg.get("speaker", "")))
            self.table.setItem(row, 2, QTableWidgetItem(seg.get("type", "")))
            self.table.setItem(row, 3, QTableWidgetItem(seg.get("gender", "")))
            self.table.setItem(row, 4, QTableWidgetItem(f"{conf:.0%}"))
            self.table.setItem(row, 5, QTableWidgetItem(seg.get("voice", "")))
            self.table.setItem(row, 6, QTableWidgetItem(seg.get("text", "")[:150]))

    def clear(self):
        self.table.setRowCount(0)
