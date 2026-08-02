# ebook_app/gui/phase_panels/phase1_panel.py
"""Phase 1 panel — Project Setup."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase1Panel(BasePhasePanel):
    """Panel for Phase 1: enter project title, author, source, output dir."""

    PHASE_NAME = "Phase 1 — Project Setup"
    PHASE_DESCRIPTION = (
        "Enter the book title, author, and source (URL or local file/folder).\n"
        "This information is saved with the project for future sessions."
    )

    def _build_content(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setSpacing(10)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("e.g. The Name of the Wind")
        form.addRow("Book title *", self._title_edit)

        self._author_edit = QLineEdit()
        self._author_edit.setPlaceholderText("e.g. Patrick Rothfuss")
        form.addRow("Author", self._author_edit)

        # Source type selector
        self._source_type = QComboBox()
        self._source_type.addItems(["Web URL (index page)", "Local folder", "EPUB / PDF file"])
        form.addRow("Source type", self._source_type)

        # Source path / URL
        src_row = QWidget()
        src_layout = QHBoxLayout(src_row)
        src_layout.setContentsMargins(0, 0, 0, 0)
        self._source_edit = QLineEdit()
        self._source_edit.setPlaceholderText("URL or file path…")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.setFixedWidth(80)
        self._browse_btn.clicked.connect(self._browse_source)
        src_layout.addWidget(self._source_edit)
        src_layout.addWidget(self._browse_btn)
        form.addRow("Source *", src_row)

        # Output directory
        out_row = QWidget()
        out_layout = QHBoxLayout(out_row)
        out_layout.setContentsMargins(0, 0, 0, 0)
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("(default output directory)")
        self._output_browse_btn = QPushButton("Browse…")
        self._output_browse_btn.setFixedWidth(80)
        self._output_browse_btn.clicked.connect(self._browse_output)
        out_layout.addWidget(self._output_edit)
        out_layout.addWidget(self._output_browse_btn)
        form.addRow("Output directory", out_row)

        # Pre-fill from settings
        self._output_edit.setText(self.settings.get("output_dir", ""))

        return widget

    def _browse_source(self) -> None:
        idx = self._source_type.currentIndex()
        if idx == 0:
            return  # URL — user types it
        elif idx == 1:
            path = QFileDialog.getExistingDirectory(self, "Select folder")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select file", filter="Documents (*.epub *.pdf *.txt *.html)"
            )
        if path:
            self._source_edit.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select output directory")
        if path:
            self._output_edit.setText(path)

    def get_phase_kwargs(self) -> dict:
        """Return the kwargs that will be passed to Phase1Project.run()."""
        return {
            "title": self._title_edit.text().strip(),
            "author": self._author_edit.text().strip(),
            "source": self._source_edit.text().strip(),
            "output_dir": self._output_edit.text().strip(),
        }
