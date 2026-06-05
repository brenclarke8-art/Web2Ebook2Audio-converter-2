# src/ebook_app/ui/pages/character_db_page.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, Slot


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

        # ---------------- Left: Character list ------------------------
        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(240)
        self.list_widget.currentRowChanged.connect(self._on_select_character)
        split.addWidget(self.list_widget, 1)

        # ---------------- Right: Editor panel -------------------------
        editor = QVBoxLayout()
        editor.setSpacing(6)
        split.addLayout(editor, 2)

        # Name
        editor.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        editor.addWidget(self.name_edit)

        # Gender
        editor.addWidget(QLabel("Gender:"))
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["unknown", "male", "female"])
        editor.addWidget(self.gender_combo)

        # Voice
        editor.addWidget(QLabel("Voice:"))
        self.voice_edit = QLineEdit()
        editor.addWidget(self.voice_edit)

        # Aliases
        editor.addWidget(QLabel("Aliases (comma-separated):"))
        self.aliases_edit = QLineEdit()
        editor.addWidget(self.aliases_edit)

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
        self.btn_merge.clicked.connect(self._merge_characters_stub)

        # Load DB on startup
        self.load_character_db()

    # ------------------------------------------------------------------
    # Load + display character DB
    # ------------------------------------------------------------------

    def load_character_db(self):
        """
        Load character_db.json via ProjectManager.
        """
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
        self.voice_edit.setText(char.get("voice", ""))

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
        char["voice"] = self.voice_edit.text().strip()

        aliases_raw = self.aliases_edit.text().strip()
        char["aliases"] = [a.strip() for a in aliases_raw.split(",") if a.strip()]

        char["description"] = self.desc_edit.toPlainText().strip()

        # Save to disk
        self.project_manager.save_character_db(self.character_db)
        self.log_console.log("Character DB saved.")

        # Refresh list names
        self.load_character_db()

    # ------------------------------------------------------------------
    # Merge characters (stub)
    # ------------------------------------------------------------------

    def _merge_characters_stub(self):
        QMessageBox.information(
            self,
            "Merge Characters",
            "Merge dialog not implemented yet.\n"
            "We will add this after widgets/dialogs are generated."
        )
