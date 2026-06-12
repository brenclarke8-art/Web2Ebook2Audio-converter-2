# ebook_app/app/ui/browser_view.py
"""Browser View — embedded web browser for manual navigation during scraping."""
from __future__ import annotations
import logging
from typing import Optional

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel

logger = logging.getLogger(__name__)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _WEB_ENGINE_AVAILABLE = True
except ImportError:
    _WEB_ENGINE_AVAILABLE = False


class BrowserView(QWidget):
    """Embedded browser widget for JS-heavy sites that require manual login/navigation."""

    url_captured = Signal(str)  # emitted when user clicks "Use this URL"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Address bar
        addr_row = QHBoxLayout()
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL...")
        self.url_bar.returnPressed.connect(self._navigate)
        btn_go = QPushButton("Go")
        btn_go.clicked.connect(self._navigate)
        btn_capture = QPushButton("Use This URL")
        btn_capture.clicked.connect(self._capture_url)
        addr_row.addWidget(self.url_bar)
        addr_row.addWidget(btn_go)
        addr_row.addWidget(btn_capture)
        layout.addLayout(addr_row)

        if _WEB_ENGINE_AVAILABLE:
            self.web_view = QWebEngineView()
            layout.addWidget(self.web_view)
        else:
            self.web_view = None
            layout.addWidget(QLabel(
                "PySide6-WebEngine is not installed.\n"
                "Install it to enable the embedded browser:\n"
                "  pip install PySide6-WebEngine"
            ))

    def navigate(self, url: str):
        self.url_bar.setText(url)
        if self.web_view:
            self.web_view.load(QUrl(url))

    def _navigate(self):
        url = self.url_bar.text().strip()
        if url:
            self.navigate(url)

    def _capture_url(self):
        url = self.url_bar.text().strip()
        if url:
            self.url_captured.emit(url)
