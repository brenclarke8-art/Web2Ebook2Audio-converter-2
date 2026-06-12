# ebook_app/app/ui/scrape_preview.py
"""Scrape Preview — shows raw scraped text for a selected chapter."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel, QSplitter
from PySide6.QtCore import Qt


class ScrapePreviewWidget(QWidget):
    """Read-only preview of scraped chapter content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Scraped Content</b>"))
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText("Scraped text will appear here after scraping.")
        layout.addWidget(self.text_view)

    def set_content(self, text: str):
        self.text_view.setPlainText(text)

    def clear(self):
        self.text_view.clear()
