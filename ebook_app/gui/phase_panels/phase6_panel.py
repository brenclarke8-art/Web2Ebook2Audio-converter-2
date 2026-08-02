# ebook_app/gui/phase_panels/phase6_panel.py
"""Phase 6 panel — Review and Audio Generation Prep."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase6Panel(BasePhasePanel):
    PHASE_NAME = "Phase 6 — Review & Audio Prep"
    PHASE_DESCRIPTION = (
        "Review speaker and voice assignments before audio generation.\n"
        "Segments flagged for review (low confidence) are highlighted.\n"
        "Confirm to proceed to audio generation."
    )

    def __init__(self, settings, parent=None):
        super().__init__(settings, parent)
        # Phase 6 always starts in confirm mode in manual/semi_auto
        self.set_confirm_mode(True)

    def _build_content(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Final segment review — voice assignments:"))

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["#", "Type", "Speaker", "Voice", "Review?"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)
        return widget

    def show_segments(self, segments: list) -> None:
        self._table.setRowCount(len(segments))
        for row, seg in enumerate(segments):
            self._table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self._table.setItem(row, 1, QTableWidgetItem(seg.get("type", "")))
            self._table.setItem(row, 2, QTableWidgetItem(seg.get("speaker", "")))
            self._table.setItem(row, 3, QTableWidgetItem(seg.get("voice", "")))
            flag = "⚠️" if seg.get("needs_review") else ""
            self._table.setItem(row, 4, QTableWidgetItem(flag))
            if seg.get("needs_review"):
                for col in range(5):
                    item = self._table.item(row, col)
                    if item:
                        item.setBackground(__import__("PySide6.QtGui", fromlist=["QColor"]).QColor("#4a2000"))
