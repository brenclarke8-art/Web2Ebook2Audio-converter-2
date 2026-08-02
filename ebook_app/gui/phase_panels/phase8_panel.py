# ebook_app/gui/phase_panels/phase8_panel.py
"""Phase 8 panel — Output."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase8Panel(BasePhasePanel):
    PHASE_NAME = "Phase 8 — Output"
    PHASE_DESCRIPTION = (
        "Assemble the EPUB and export audio files to the output directory.\n"
        "All processing is complete — your audiobook is ready."
    )

    def __init__(self, settings, parent=None):
        super().__init__(settings, parent)
        self._run_btn.setText("▶ Build Output")

    def _build_content(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Output files:"))
        self._file_list = QListWidget()
        layout.addWidget(self._file_list)

        open_row = QHBoxLayout()
        self._open_btn = QPushButton("📂 Open Output Folder")
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_output)
        open_row.addStretch()
        open_row.addWidget(self._open_btn)
        layout.addLayout(open_row)

        self._output_dir: str = ""
        return widget

    def show_output_files(self, epub_path: str, audio_files: list, output_dir: str) -> None:
        self._file_list.clear()
        self._output_dir = output_dir
        if epub_path:
            self._file_list.addItem(f"📚 EPUB: {epub_path}")
        for af in audio_files:
            self._file_list.addItem(f"🔊 {af}")
        self._open_btn.setEnabled(bool(output_dir))

    def _open_output(self) -> None:
        if self._output_dir and os.path.isdir(self._output_dir):
            import subprocess, sys
            if sys.platform == "win32":
                os.startfile(self._output_dir)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self._output_dir])
            else:
                subprocess.Popen(["xdg-open", self._output_dir])
