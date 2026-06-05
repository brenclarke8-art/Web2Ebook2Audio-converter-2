# src/ebook_app/ui/widgets/speaker_dropdown.py

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel
)


class SpeakerDropdown(QWidget):
    """
    A searchable dropdown for selecting speakers from the Character DB.

    Features:
        - Fuzzy search
        - Shows character names + aliases
        - Emits speaker_selected(name)
        - Emits add_new_character_requested()
        - Can be embedded in forms or sidebars

    Public API:
        load_characters(character_db)
        set_current_speaker(name)
    """

    speaker_selected = Signal(str)
    add_new_character_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Speaker")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # Search bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search speaker…")
        self.search_edit.textChanged.connect(self._filter_list)
        layout.addWidget(self.search_edit)

        # List of speakers
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget, 1)

        # Internal data
        self.character_db = []
        self.current_speaker = ""

    # ------------------------------------------------------------------
    # Load characters from Character DB
    # ------------------------------------------------------------------
    def load_characters(self, character_db: list[dict]):
        self.character_db = character_db
        self._refresh_list()

    # ------------------------------------------------------------------
    def _refresh_list(self):
        self.list_widget.clear()

        # Add "Add new character…" option
        item_new = QListWidgetItem("➕ Add new character…")
        item_new.setData(Qt.UserRole, "__add_new__")
        self.list_widget.addItem(item_new)

        # Add characters
        for char in self.character_db:
            name = char.get("name", "")
            aliases = ", ".join(char.get("aliases", []))

            label = name
            if aliases:
                label += f"  ({aliases})"

            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, name)
            self.list_widget.addItem(item)

    # ------------------------------------------------------------------
    def _filter_list(self, text: str):
        text = text.lower().strip()

        self.list_widget.clear()

        # Always keep "Add new character"
        item_new = QListWidgetItem("➕ Add new character…")
        item_new.setData(Qt.UserRole, "__add_new__")
        self.list_widget.addItem(item_new)

        for char in self.character_db:
            name = char.get("name", "")
            aliases = ", ".join(char.get("aliases", []))

            haystack = f"{name} {aliases}".lower()

            if text in haystack:
                label = name
                if aliases:
                    label += f"  ({aliases})"

                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, name)
                self.list_widget.addItem(item)

    # ------------------------------------------------------------------
    def _on_item_clicked(self, item: QListWidgetItem):
        value = item.data(Qt.UserRole)

        if value == "__add_new__":
            self.add_new_character_requested.emit()
            return

        self.current_speaker = value
        self.speaker_selected.emit(value)

    # ------------------------------------------------------------------
    def set_current_speaker(self, name: str):
        """Highlight the current speaker in the list."""
        self.current_speaker = name

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == name:
                self.list_widget.setCurrentItem(item)
                break
