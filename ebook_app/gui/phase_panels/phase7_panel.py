# ebook_app/gui/phase_panels/phase7_panel.py
"""Phase 7 panel — Audio Generation."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase7Panel(BasePhasePanel):
    PHASE_NAME = "Phase 7 — Audio Generation"
    PHASE_DESCRIPTION = (
        "Generate audio for each segment using the TTS service.\n"
        "Segments are processed in order and concatenated into a chapter audio file."
    )

    def _build_content(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        self._status_label = QLabel("Ready to generate audio.")
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        layout.addWidget(self._progress)

        layout.addStretch()
        return widget

    def set_progress(self, pct: int) -> None:
        self._progress.setValue(pct)
        self._status_label.setText(f"Generating… {pct}%")

    def set_complete(self, audio_path: str) -> None:
        self._progress.setValue(100)
        self._status_label.setText(f"✅ Audio saved: {audio_path}")
