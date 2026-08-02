# ebook_app/app/widgets/character_editor.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox
)


class CharacterEditor(QWidget):
    """
    Reusable editor panel for a single character.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Name
        layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        layout.addWidget(self.name_edit)

        # Gender
        layout.addWidget(QLabel("Gender:"))
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["unknown", "male", "female"])
        layout.addWidget(self.gender_combo)

        # Voice
        layout.addWidget(QLabel("Voice:"))
        self.voice_edit = QLineEdit()
        layout.addWidget(self.voice_edit)

        # Aliases
        layout.addWidget(QLabel("Aliases (comma-separated):"))
        self.aliases_edit = QLineEdit()
        layout.addWidget(self.aliases_edit)

        # Description
        layout.addWidget(QLabel("Description:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setMinimumHeight(80)
        layout.addWidget(self.desc_edit)

    # --------------------------------------------------------------
    # Load character into editor
    # --------------------------------------------------------------
    def load_character(self, char: dict):
        self.name_edit.setText(char.get("name", ""))
        self.gender_combo.setCurrentText(char.get("gender", "unknown"))
        self.voice_edit.setText(char.get("voice", ""))

        aliases = ", ".join(char.get("aliases", []))
        self.aliases_edit.setText(aliases)

        self.desc_edit.setPlainText(char.get("description", ""))

    # --------------------------------------------------------------
    # Extract edited character
    # --------------------------------------------------------------
    def extract(self) -> dict:
        aliases_raw = self.aliases_edit.text().strip()
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]

        return {
            "name": self.name_edit.text().strip(),
            "gender": self.gender_combo.currentText(),
            "voice": self.voice_edit.text().strip(),
            "aliases": aliases,
            "description": self.desc_edit.toPlainText().strip(),
        }
