# ebook_app/app/ui/character_view.py
"""Character database page."""

from __future__ import annotations

import json
import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ebook_app.app.ui.base_view import BasePage
from ebook_app.app.widgets.character_editor import CharacterEditor

logger = logging.getLogger(__name__)


class CharacterDBPage(BasePage):
    """Page for browsing and editing the per-project character database."""

    def _build_ui(self) -> None:
        self._characters: list[dict] = []
        self._current_index: Optional[int] = None

        # ── toolbar ──────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        title = QLabel("<b>Character Database</b>")
        add_btn = QPushButton("➕ Add")
        del_btn = QPushButton("🗑 Delete")
        save_btn = QPushButton("💾 Save")
        add_btn.clicked.connect(self._on_add)
        del_btn.clicked.connect(self._on_delete)
        save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(title)
        toolbar.addStretch()
        toolbar.addWidget(add_btn)
        toolbar.addWidget(del_btn)
        toolbar.addWidget(save_btn)
        self._layout.addLayout(toolbar)

        # ── splitter: list | editor ───────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        splitter.addWidget(self._list)

        self._editor = CharacterEditor()
        splitter.addWidget(self._editor)
        splitter.setSizes([280, 520])

        self._layout.addWidget(splitter, 1)

        # Load initial data if a project is open
        self._reload()

        # Refresh when a new project is loaded
        if self.project_manager:
            self.project_manager.project_loaded.connect(self._reload)

    # ------------------------------------------------------------------

    def _reload(self) -> None:
        """Load character data from the active project."""
        if self.project_manager:
            self._characters = list(self.project_manager.load_character_db())
        else:
            self._characters = []
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        for char in self._characters:
            name = char.get("name", "?")
            gender = char.get("gender", "unknown")
            item = QListWidgetItem(f"{name}  ({gender})")
            self._list.addItem(item)
        self._current_index = None

    # ------------------------------------------------------------------

    def _on_row_changed(self, row: int) -> None:
        # Flush any pending edits for the previously selected character first,
        # and update the list item text so the name/gender stays current.
        if self._current_index is not None and 0 <= self._current_index < len(self._characters):
            updated = self._editor.extract()
            self._characters[self._current_index] = updated
            prev_item = self._list.item(self._current_index)
            if prev_item is not None:
                prev_item.setText(
                    f"{updated.get('name', '?')}  ({updated.get('gender', 'unknown')})"
                )

        if 0 <= row < len(self._characters):
            self._current_index = row
            self._editor.load_character(self._characters[row])

    def _on_add(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Character", "Name:")
        if not ok or not name.strip():
            return
        self._characters.append({"name": name.strip(), "gender": "unknown",
                                   "voice": "", "aliases": [], "description": ""})
        self._refresh_list()
        self._list.setCurrentRow(len(self._characters) - 1)

    def _on_delete(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        reply = QMessageBox.question(
            self, "Delete Character",
            f"Delete '{self._characters[row].get('name', '?')}'?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self._characters[row]
            self._refresh_list()

    def _on_save(self) -> None:
        # Flush editor content for the currently selected character
        if self._current_index is not None and 0 <= self._current_index < len(self._characters):
            self._characters[self._current_index] = self._editor.extract()

        if self.project_manager:
            self.project_manager.save_character_db(self._characters)

        if self.log:
            self.log.log(f"Character database saved ({len(self._characters)} entries).", "SUCCESS")
        logger.info("Character database saved (%d entries).", len(self._characters))
