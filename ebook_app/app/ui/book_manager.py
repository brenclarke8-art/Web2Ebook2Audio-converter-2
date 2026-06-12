# ebook_app/app/ui/book_manager.py
"""Book Manager UI — list, create, open, and delete book projects."""
from __future__ import annotations
import logging
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox, QInputDialog,
)

from ebook_app.app.state.book_state import ProjectManager

logger = logging.getLogger(__name__)


class BookManagerWidget(QWidget):
    """Displays the book library and lets users create/open/delete projects."""

    book_opened = Signal(str)   # emits book_id

    def __init__(self, project_manager: ProjectManager, parent=None):
        super().__init__(parent)
        self.pm = project_manager
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Book Library</b>"))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_open)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("New Project")
        self.btn_open = QPushButton("Open")
        self.btn_delete = QPushButton("Delete")
        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_open)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_delete)
        layout.addLayout(btn_row)

    def refresh(self):
        """Reload the book list from the library."""
        self.list_widget.clear()
        for book in self.pm.library.list_books():
            item = QListWidgetItem(f"{book.get('title', '?')} — {book.get('author', '?')}")
            item.setData(0x100, book.get("book_id"))
            self.list_widget.addItem(item)

    def _current_id(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        return item.data(0x100) if item else None

    def _on_new(self):
        title, ok = QInputDialog.getText(self, "New Project", "Book title:")
        if not ok or not title.strip():
            return
        author, ok2 = QInputDialog.getText(self, "New Project", "Author:")
        if not ok2:
            return
        url, ok3 = QInputDialog.getText(self, "New Project", "Index URL (optional):")
        if not ok3:
            url = ""
        book_id = self.pm.create_project(title.strip(), author.strip(), url.strip())
        self.refresh()
        self.book_opened.emit(book_id)

    def _on_open(self):
        bid = self._current_id()
        if bid:
            self.pm.load_project(bid)
            self.book_opened.emit(bid)

    def _on_delete(self):
        bid = self._current_id()
        if not bid:
            return
        reply = QMessageBox.question(
            self, "Delete Project",
            "Are you sure you want to delete this project? This cannot be undone.",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.pm.library.remove_book(bid)
            self.refresh()
