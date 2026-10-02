# ebook_app/app/top_navbar.py
"""Top navigation bar for Ebook Audio Studio."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

_NAV_ITEMS = [
    (0, "🔄 Pipeline"),
    (1, "👤 Characters"),
    (2, "⚙ Settings"),
]


class TopNavBar(QWidget):
    """Horizontal navigation bar that emits ``navigate(int)`` on tab click.

    The integer payload matches the stacked-widget page index used by
    :class:`ebook_app.app.main_window.MainWindow`.
    """

    navigate = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[QPushButton] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        for idx, label in _NAV_ITEMS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(110)
            btn.clicked.connect(lambda checked=False, i=idx: self._on_clicked(i))
            self._buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Activate the first tab by default
        self._set_active(0)

    # ------------------------------------------------------------------

    def _on_clicked(self, idx: int) -> None:
        self._set_active(idx)
        self.navigate.emit(idx)

    def _set_active(self, idx: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == idx)
