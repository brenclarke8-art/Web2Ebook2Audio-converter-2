# src/ebook_app/ui/widgets/segment_table.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QPushButton, QVBoxLayout
)
from PySide6.QtCore import Qt


class SegmentTable(QWidget):
    """
    Reusable table for displaying Pass‑2 or final chapter segments.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Paragraph ID", "Type", "Speaker", "Text", "Preview"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.table)

    # --------------------------------------------------------------
    # Populate table with segments
    # --------------------------------------------------------------
    def load_segments(self, segments: list[dict], preview_callback):
        self.table.setRowCount(len(segments))

        for row, seg in enumerate(segments):
            pid = str(seg.get("paragraph_id", ""))
            typ = seg.get("type", "")
            speaker = seg.get("speaker", "")
            text = seg.get("text", "")

            # Paragraph ID
            self.table.setItem(row, 0, QTableWidgetItem(pid))

            # Type
            self.table.setItem(row, 1, QTableWidgetItem(typ))

            # Speaker
            self.table.setItem(row, 2, QTableWidgetItem(speaker))

            # Text (editable)
            item_text = QTableWidgetItem(text)
            item_text.setFlags(item_text.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 3, item_text)

            # Preview button
            btn = QPushButton("▶")
            btn.clicked.connect(lambda _, r=row: preview_callback(r))
            self.table.setCellWidget(row, 4, btn)

        self.table.resizeColumnsToContents()

    # --------------------------------------------------------------
    # Extract edited segments
    # --------------------------------------------------------------
    def extract_segments(self, base_segments: list[dict]) -> list[dict]:
        """
        Returns a new list of segments with edited text/speaker/type.
        """
        out = []

        for row in range(self.table.rowCount()):
            seg = dict(base_segments[row])  # copy

            seg["paragraph_id"] = self.table.item(row, 0).text()
            seg["type"] = self.table.item(row, 1).text()
            seg["speaker"] = self.table.item(row, 2).text()
            seg["text"] = self.table.item(row, 3).text()

            out.append(seg)

        return out
