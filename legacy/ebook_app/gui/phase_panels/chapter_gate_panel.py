# ebook_app/gui/phase_panels/chapter_gate_panel.py
"""Chapter gate screen — shown between chapters in manual / semi_auto mode."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt


class ChapterGatePanel(QWidget):
    """Screen shown after one chapter completes asking to start the next.

    Signals
    -------
    next_requested
        User clicked "Start Next Chapter".
    cancel_requested
        User clicked "Cancel".
    """

    next_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        layout.addStretch()

        self._msg_label = QLabel("")
        self._msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg_label.setStyleSheet("font-size: 18px;")
        self._msg_label.setWordWrap(True)
        layout.addWidget(self._msg_label)

        self._detail_label = QLabel("")
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_label.setStyleSheet("color: #888;")
        layout.addWidget(self._detail_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        self._cancel_btn = QPushButton("✖ Cancel All")
        self._cancel_btn.setStyleSheet(
            "background-color: #c0392b; color: white; font-weight: bold; padding: 8px 20px;"
        )
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)

        self._next_btn = QPushButton("▶ Start Next Chapter")
        self._next_btn.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; padding: 8px 20px;"
        )
        self._next_btn.clicked.connect(self.next_requested.emit)

        btn_row.addStretch()
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._next_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()

    def update_info(
        self,
        completed_num: int,
        next_num: int,
        total: int,
    ) -> None:
        self._msg_label.setText(
            f"✅ Chapter {completed_num} complete.\n"
            f"Ready to start Chapter {next_num} of {total}?"
        )
        self._detail_label.setText(
            f"Progress: {completed_num}/{total} chapters processed."
        )
