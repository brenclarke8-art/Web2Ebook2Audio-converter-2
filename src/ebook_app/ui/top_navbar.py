# src/ebook_app/ui/top_navbar.py
"""Dark-mode top navigation bar widget."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget


_PAGES = [
    ("Scraper", "scraper"),
    ("Translator", "translator"),
    ("TTS", "tts"),
    ("EPUB Export", "epub_export"),
    ("Pipeline", "pipeline"),
    ("Preview", "chapter_preview"),
    ("Settings", "settings"),
]

_NAVBAR_STYLE = """
QWidget#TopNavBar {
    background-color: #1e1e2e;
}
QPushButton {
    color: #cdd6f4;
    background: transparent;
    border: none;
    padding: 8px 16px;
    font-size: 14px;
}
QPushButton:hover {
    background-color: #313244;
}
QPushButton:checked {
    background-color: #45475a;
    border-bottom: 2px solid #89b4fa;
}
"""


class TopNavBar(QWidget):
    """Horizontal navigation bar that emits :attr:`page_requested` when a tab is clicked.

    Signals:
        page_requested (str): The page key corresponding to the clicked button.
    """

    page_requested: Signal = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopNavBar")
        self.setStyleSheet(_NAVBAR_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(48)

        self._buttons: dict[str, QPushButton] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(0)

        for label, key in _PAGES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key: self._on_button_clicked(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # Activate the first page by default.
        first_key = _PAGES[0][1]
        self._buttons[first_key].setChecked(True)

    def set_active_page(self, key: str) -> None:
        """Programmatically highlight the button for *key*."""
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)

    def _on_button_clicked(self, key: str) -> None:
        self.set_active_page(key)
        self.page_requested.emit(key)
