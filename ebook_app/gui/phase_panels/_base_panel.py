# ebook_app/gui/phase_panels/_base_panel.py
"""Abstract base widget shared by all phase panels.

Every panel has:
  - A title + description header
  - A central content area (implemented by subclass)
  - A diff/output viewer that shows the phase result text
  - A button row: [Cancel] [Back] [Run / Confirm & Continue]
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt


class BasePhasePanel(QWidget):
    """Base widget for a single pipeline phase panel.

    Signals
    -------
    run_requested
        Emitted when the user clicks "Run Phase" or "Confirm & Continue".
    cancel_requested
        Emitted when the user clicks the Cancel button (after confirmation).
    back_requested
        Emitted when the user clicks Back.
    """

    run_requested = Signal()
    cancel_requested = Signal()
    back_requested = Signal()

    PHASE_NAME: str = "Phase"
    PHASE_DESCRIPTION: str = ""

    def __init__(self, settings: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._result_text: str = ""
        self._build_layout()

    # ─────────────────────────────────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 12)
        outer.setSpacing(10)

        # Header
        title_lbl = QLabel(f"<h2>{self.PHASE_NAME}</h2>")
        title_lbl.setWordWrap(True)
        outer.addWidget(title_lbl)

        if self.PHASE_DESCRIPTION:
            desc_lbl = QLabel(self.PHASE_DESCRIPTION)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #888;")
            outer.addWidget(desc_lbl)

        # Content + output splitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Top: subclass content
        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_widget = self._build_content()
        content_scroll.setWidget(content_widget)
        splitter.addWidget(content_scroll)

        # Bottom: output viewer
        output_frame = QWidget()
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(4)
        output_layout.addWidget(QLabel("<b>Phase output:</b>"))
        self._output_view = QPlainTextEdit()
        self._output_view.setReadOnly(True)
        self._output_view.setPlaceholderText("Run the phase to see output here…")
        self._output_view.setMaximumHeight(200)
        output_layout.addWidget(self._output_view)
        splitter.addWidget(output_frame)

        splitter.setSizes([400, 200])
        outer.addWidget(splitter, 1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)

        self._cancel_btn = QPushButton("✖ Cancel")
        self._cancel_btn.setStyleSheet(
            "background-color: #c0392b; color: white; font-weight: bold; padding: 6px 14px;"
        )
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._cancel_btn.setVisible(False)  # shown only while phase is running

        self._back_btn = QPushButton("← Back")
        self._back_btn.clicked.connect(self.back_requested.emit)

        self._run_btn = QPushButton("▶ Run Phase")
        self._run_btn.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; padding: 6px 14px;"
        )
        self._run_btn.clicked.connect(self.run_requested.emit)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._back_btn)
        btn_row.addWidget(self._run_btn)

        outer.addLayout(btn_row)

    # ─────────────────────────────────────────────────────────────────────
    # Subclass interface
    # ─────────────────────────────────────────────────────────────────────

    def _build_content(self) -> QWidget:
        """Return the main content widget for this phase. Override in subclass."""
        return QWidget()

    def get_phase_kwargs(self) -> dict:
        """Return kwargs passed to the phase controller's run() method."""
        return {}

    # ─────────────────────────────────────────────────────────────────────
    # Public API called by PipelineWizard
    # ─────────────────────────────────────────────────────────────────────

    def set_running(self, running: bool) -> None:
        """Switch the panel into/out of 'running' state."""
        self._cancel_btn.setVisible(running)
        self._run_btn.setEnabled(not running)
        self._back_btn.setEnabled(not running)

    def set_confirm_mode(self, enabled: bool) -> None:
        """Switch the run button label to 'Confirm & Continue'."""
        self._run_btn.setText("✔ Confirm & Continue" if enabled else "▶ Run Phase")

    def show_output(self, text: str) -> None:
        """Display phase output text in the output viewer."""
        self._result_text = text
        self._output_view.setPlainText(text)

    def clear_output(self) -> None:
        self._output_view.clear()
        self._result_text = ""

    # ─────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────

    def _on_cancel_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Cancel Pipeline",
            "Cancel processing and reset the pipeline?\n\nThis will stop all processing.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cancel_requested.emit()
