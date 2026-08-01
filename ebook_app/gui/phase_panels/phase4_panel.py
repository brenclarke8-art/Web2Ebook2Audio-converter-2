# ebook_app/gui/phase_panels/phase4_panel.py
"""Phase 4 panel — Text Segmentation."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase4Panel(BasePhasePanel):
    PHASE_NAME = "Phase 4 — Text Segmentation"
    PHASE_DESCRIPTION = (
        "Split the chapter text into dialogue, thought, and narration segments.\n"
        "This step uses deterministic rules — no LLM."
    )

    def _build_content(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["#", "Type", "Text preview"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)
        return widget

    def show_segments(self, segments: list) -> None:
        self._table.setRowCount(len(segments))
        for row, seg in enumerate(segments):
            self._table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            is_dial = "dialogue" if seg.get("is_dialogue_candidate") else "narration"
            self._table.setItem(row, 1, QTableWidgetItem(is_dial))
            text = (seg.get("text") or "")[:80]
            self._table.setItem(row, 2, QTableWidgetItem(text))
