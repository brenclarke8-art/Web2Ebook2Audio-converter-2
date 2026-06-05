# src/ebook_app/ui/pages/character_db_page.py

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, Slot

from ebook_app.ui.dialogs import MergeCharactersDialog, EditAliasesDialog


class CharacterDBPage(QWidget):
    """
    UI for viewing and editing the canonical character database.
    """

    def __init__(self, settings, log, project_manager):
        super().__init__()

        self.settings = settings
        self.log_console = log
        self.project_manager = project_manager

        # Loaded character DB
        self.character_db: list[dict] = []

        # Currently selected character index
        self.current_index: int | None = None

        # --------------------------------------------------------------
        # Layout
        # --------------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Character Database")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # --------------------------------------------------------------
        # Main split: list on left, editor on right
        # --------------------------------------------------------------
        split = QHBoxLayout()
        layout.addLayout(split)

        # ---------------- Left Panel: Search + List + Buttons ----------
        left_panel = QVBoxLayout()
        split.addLayout(left_panel, 1)

        # Search bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search characters…")
        self.search_edit.textChanged.connect(self._filter_list)
        left_panel.addWidget(self.search_edit)

        # Character list
        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(240)
        self.list_widget.currentRowChanged.connect(self._on_select_character)
        left_panel.addWidget(self.list_widget, 1)

        # New / Delete buttons
        btn_list_row = QHBoxLayout()
        left_panel.addLayout(btn_list_row)

        self.btn_new = QPushButton("New")
        self.btn_delete = QPushButton("Delete")

        btn_list_row.addWidget(self.btn_new)
        btn_list_row.addWidget(self.btn_delete)

        self.btn_new.clicked.connect(self._new_character)
        self.btn_delete.clicked.connect(self._delete_character)

        # ---------------- Right: Editor panel -------------------------
        editor = QVBoxLayout()
        editor.setSpacing(6)
        split.addLayout(editor, 2)

        # Name
        editor.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        editor.addWidget(self.name_edit)

        # Gender dropdown
        editor.addWidget(QLabel("Gender:"))
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["unknown", "male", "female"])
        editor.addWidget(self.gender_combo)

        # Voice dropdown
        editor.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
        voices = self.settings.get("voice_catalog", [])
        self.voice_combo.addItems([""] + voices)
        editor.addWidget(self.voice_combo)

        # Aliases
        editor.addWidget(QLabel("Aliases (comma-separated):"))
        self.aliases_edit = QLineEdit()
        editor.addWidget(self.aliases_edit)

        self.btn_edit_aliases = QPushButton("Edit Aliases…")
        self.btn_edit_aliases.clicked.connect(self._open_alias_editor)
        editor.addWidget(self.btn_edit_aliases)

        # Description
        editor.addWidget(QLabel("Description:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setMinimumHeight(80)
        editor.addWidget(self.desc_edit)

        # Buttons row
        btn_row = QHBoxLayout()
        editor.addLayout(btn_row)

        self.btn_save = QPushButton("Save Changes")
        self.btn_reload = QPushButton("Reload")
        self.btn_merge = QPushButton("Merge Characters…")

        btn_row.addWidget(self.btn_save)
        btn_row.addWidget(self.btn_reload)
        btn_row.addWidget(self.btn_merge)

        # Connect buttons
        self.btn_save.clicked.connect(self._save_changes)
        self.btn_reload.clicked.connect(self.load_character_db)
        self.btn_merge.clicked.connect(self._merge_characters)

        # Load DB on startup
        self.load_character_db()

    # ------------------------------------------------------------------
    # Search filter
    # ------------------------------------------------------------------
    def _filter_list(self, text: str):
        text = text.lower().strip()
        self.list_widget.clear()

        for char in self.character_db:
            name = char.get("name", "")
            aliases = ", ".join(char.get("aliases", []))

            if text in name.lower() or text in aliases.lower():
                self.list_widget.addItem(name)

    # ------------------------------------------------------------------
    # New character
    # ------------------------------------------------------------------
    def _new_character(self):
        new_char = {
            "name": "New Character",
            "gender": "unknown",
            "voice": "",
            "aliases": [],
            "description": "",
        }

        self.character_db.append(new_char)
        self.project_manager.save_character_db(self.character_db)

        self.load_character_db()
        self.list_widget.setCurrentRow(len(self.character_db) - 1)

        self.log_console.log("New character added.")

    # ------------------------------------------------------------------
    # Delete character
    # ------------------------------------------------------------------
    def _delete_character(self):
        if self.current_index is None:
            QMessageBox.warning(self, "No Selection", "Select a character to delete.")
            return

        name = self.character_db[self.current_index].get("name", "Unnamed")

        confirm = QMessageBox.question(
            self,
            "Delete Character",
            f"Are you sure you want to delete '{name}'?"
        )

        if confirm != QMessageBox.Yes:
            return

        del self.character_db[self.current_index]
        self.project_manager.save_character_db(self.character_db)

        self.load_character_db()
        self.current_index = None

        self.log_console.log(f"Deleted character: {name}")

    # ------------------------------------------------------------------
    # Alias editor dialog
    # ------------------------------------------------------------------
    def _open_alias_editor(self):
        if self.current_index is None:
            QMessageBox.warning(self, "No Selection", "Select a character first.")
            return

        char = self.character_db[self.current_index]
        dlg = EditAliasesDialog(char.get("aliases", []), self)

        def apply_aliases(new_aliases):
            char["aliases"] = new_aliases
            self.aliases_edit.setText(", ".join(new_aliases))
            self.project_manager.save_character_db(self.character_db)
            self.log_console.log("Aliases updated.")

        dlg.aliases_updated.connect(apply_aliases)
        dlg.exec()

    # ------------------------------------------------------------------
    # Load + display character DB
    # ------------------------------------------------------------------
    def load_character_db(self):
        self.character_db = self.project_manager.load_character_db()
        self.list_widget.clear()

        if not self.character_db:
            self.list_widget.addItem("No characters found.")
            return

        for char in self.character_db:
            item = QListWidgetItem(char.get("name", "Unnamed"))
            self.list_widget.addItem(item)

        self.log_console.log("Character DB loaded.")

    # ------------------------------------------------------------------
    # Selection handler
    # ------------------------------------------------------------------
    @Slot(int)
    def _on_select_character(self, index: int):
        if index < 0 or index >= len(self.character_db):
            self.current_index = None
            return

        self.current_index = index
        char = self.character_db[index]

        self.name_edit.setText(char.get("name", ""))
        self.gender_combo.setCurrentText(char.get("gender", "unknown"))
        self.voice_combo.setCurrentText(char.get("voice", ""))

        aliases = ", ".join(char.get("aliases", []))
        self.aliases_edit.setText(aliases)

        self.desc_edit.setPlainText(char.get("description", ""))

    # ------------------------------------------------------------------
    # Save changes
    # ------------------------------------------------------------------
    def _save_changes(self):
        if self.current_index is None:
            QMessageBox.warning(self, "No Selection", "Select a character first.")
            return

        char = self.character_db[self.current_index]

        char["name"] = self.name_edit.text().strip()
        char["gender"] = self.gender_combo.currentText()
        char["voice"] = self.voice_combo.currentText().strip()

        aliases_raw = self.aliases_edit.text().strip()
        char["aliases"] = [a.strip() for a in aliases_raw.split(",") if a.strip()]

        char["description"] = self.desc_edit.toPlainText().strip()

        self.project_manager.save_character_db(self.character_db)
        self.log_console.log("Character DB saved.")

        # Refresh list names
        self.load_character_db()
        self.list_widget.setCurrentRow(self.current_index)

    # ------------------------------------------------------------------
    # Merge characters
    # ------------------------------------------------------------------
    def _merge_characters(self):
        if len(self.character_db) < 2:
            QMessageBox.warning(self, "Not Enough Characters",
                                "You need at least two characters to merge.")
            return

        dlg = MergeCharactersDialog(self.character_db, self)

        def apply_merge(merged_char):
            idx_a = dlg.combo_a.currentIndex()
            idx_b = dlg.combo_b.currentIndex()

            # Remove originals
            for idx in sorted([idx_a, idx_b], reverse=True):
                del self.character_db[idx]

            # Insert merged
            self.character_db.append(merged_char)

            # Save DB
            self.project_manager.save_character_db(self.character_db)
            self.log_console.log("Characters merged and saved.")

            # Reload UI
            self.load_character_db()

            # Select merged entry
            self.list_widget.setCurrentRow(len(self.character_db) - 1)

        dlg.merged.connect(apply_merge)
        dlg.exec()
