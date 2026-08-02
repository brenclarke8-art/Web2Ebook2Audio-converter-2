# ebook_app/gui/phase_panels/phase2_panel.py
"""Phase 2 panel — Text Retrieval and Cleaning."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel, QProgressBar, QTextEdit, QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase2Panel(BasePhasePanel):
    PHASE_NAME = "Phase 2 — Text Retrieval & Cleaning"
    PHASE_DESCRIPTION = (
        "Retrieve and clean the chapter text from the configured source.\n"
        "Web sources are scraped and HTML noise is removed."
    )

    def _build_content(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Cleaned text preview will appear in the output panel below after running."))
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)
        layout.addStretch()
        return widget

    def set_progress(self, pct: int) -> None:
        self._progress_bar.setVisible(pct < 100)
        self._progress_bar.setValue(pct)
