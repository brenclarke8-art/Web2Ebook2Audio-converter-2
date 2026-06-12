# ebook_app/app/ui/segmentation_preview.py
"""Segmentation Preview — table view of text segments after dialogue detection."""
from __future__ import annotations
from typing import Any, Dict, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel,
)
from PySide6.QtCore import Qt


class SegmentationPreviewWidget(QWidget):
    """Table view showing type/speaker/text for each segment."""

    COLUMNS = ["#", "Type", "Speaker", "Gender", "Text"]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Segmentation Preview</b>"))

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
            self.table.setItem(row, 3, QTableWidgetItem(seg.get("gender", "")))
            self.table.setItem(row, 4, QTableWidgetItem(seg.get("text", "")[:200]))

    def clear(self):
        self.table.setRowCount(0)
