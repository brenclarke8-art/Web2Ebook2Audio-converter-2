# src/ebook_app/ui/pages/chapter_preview_page.py
"""Chapter Preview page — browse scraped/translated chapters."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from ebook_app.ui.pages._base_page import BasePage


class ChapterPreviewPage(BasePage):
    """Page for previewing scraped and translated chapter content.

    Left panel: chapter list.
    Right panel: chapter text viewer.

    TODO: populate from the project's chapter store.
    """

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- Chapter list --
        list_container = QGroupBox("Chapters")
        list_vbox = QVBoxLayout(list_container)
        self._chapter_list = QListWidget()
        self._chapter_list.currentRowChanged.connect(self._on_chapter_selected)
        list_vbox.addWidget(self._chapter_list)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        list_vbox.addWidget(refresh_btn)

        splitter.addWidget(list_container)

        # -- Chapter viewer --
        viewer_container = QGroupBox("Content")
        viewer_vbox = QVBoxLayout(viewer_container)
        self._chapter_label = QLabel("Select a chapter to preview")
        viewer_vbox.addWidget(self._chapter_label)
        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        viewer_vbox.addWidget(self._text_view)
        splitter.addWidget(viewer_container)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self._layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_refresh(self) -> None:
        """Placeholder: reload chapter list from disk."""
        self._chapter_list.clear()
        self.log.log("Chapter list refreshed. (not yet implemented)", level="INFO")
        # TODO: load chapter titles from the project's chapter store

    def _on_chapter_selected(self, index: int) -> None:
        """Placeholder: display the selected chapter's text."""
        if index < 0:
            return
        item = self._chapter_list.item(index)
        if item is None:
            return
        title = item.text()
        self._chapter_label.setText(title)
        self._text_view.setPlainText(
            f"[Content for '{title}' will appear here once loading is implemented.]"
        )
        # TODO: load chapter content from the project's chapter store
