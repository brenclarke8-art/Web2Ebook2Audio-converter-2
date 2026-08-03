# ebook_app/gui/phase_panels/phase1_panel.py
"""Phase 1 panel — Project Setup."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase1Panel(BasePhasePanel):
    """Panel for Phase 1: enter project title and author only.

    Source method selection (URL vs local folder) is handled by the
    SourceMethodPanel that follows immediately after this phase.
    """

    PHASE_NAME = "Phase 1 — Project Setup"
    PHASE_DESCRIPTION = (
        "Enter the book title and author.\n"
        "You will choose the source method (web URL or local folder) on the next screen."
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

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select output directory")
        if path:
            self._output_edit.setText(path)

    def get_phase_kwargs(self) -> dict:
        """Return the kwargs that will be passed to Phase1Project.run()."""
        return {
            "title": self._title_edit.text().strip(),
            "author": self._author_edit.text().strip(),
            "output_dir": self._output_edit.text().strip(),
        }
