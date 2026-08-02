# ebook_app/gui/phase_panels/phase5b_panel.py
"""Phase 5b panel — LLM Classification."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHeaderView, QLabel, QProgressBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase5bPanel(BasePhasePanel):
    PHASE_NAME = "Phase 5b — LLM Classification"
    PHASE_DESCRIPTION = (
        "Use the LLM to classify each segment: type, speaker, gender, and confidence scores.\n"
        "This step may take a few minutes depending on chapter length."
    )

    def _build_content(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["#", "Type", "Speaker", "Gender", "Conf"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)
        return widget

    def set_progress(self, pct: int) -> None:
        self._progress.setVisible(0 < pct < 100)
        self._progress.setValue(pct)

    def show_segments(self, segments: list) -> None:
        self._table.setRowCount(len(segments))
        for row, seg in enumerate(segments):
            self._table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self._table.setItem(row, 1, QTableWidgetItem(seg.get("type", "")))
            self._table.setItem(row, 2, QTableWidgetItem(seg.get("speaker", "")))
            self._table.setItem(row, 3, QTableWidgetItem(seg.get("gender", "")))
            conf = seg.get("speaker_confidence", 0)
            self._table.setItem(row, 4, QTableWidgetItem(f"{float(conf):.0%}"))
