# ebook_app/app/widgets/character_editor.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox
)

from ebook_app.tts.voice_catalog import KOKORO_VOICE_LIST

# "(none)" sentinel lets users explicitly clear the voice assignment
_VOICE_OPTIONS = ["(none)"] + KOKORO_VOICE_LIST


class CharacterEditor(QWidget):
    """
    Reusable editor panel for a single character.
    Lets users set the name, gender, TTS voice, aliases, and description.
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

        # Voice — dropdown populated from KOKORO_VOICE_LIST
        layout.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)   # allow manual override for custom voices
        self.voice_combo.addItems(_VOICE_OPTIONS)
        self.voice_combo.setToolTip(
            "Select a Kokoro voice or type a custom voice name.\n"
            "Leave as '(none)' to use the per-gender default."
        )
        layout.addWidget(self.voice_combo)

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

        voice = char.get("voice", "") or ""
        if voice and voice not in _VOICE_OPTIONS:
            # Custom voice not in the catalog — add it so it can be displayed
            self.voice_combo.addItem(voice)
        self.voice_combo.setCurrentText(voice if voice else "(none)")

        aliases = ", ".join(char.get("aliases", []))
        self.aliases_edit.setText(aliases)

        self.desc_edit.setPlainText(char.get("description", ""))

    # --------------------------------------------------------------
    # Extract edited character
    # --------------------------------------------------------------
    def extract(self) -> dict:
        aliases_raw = self.aliases_edit.text().strip()
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]

        voice = self.voice_combo.currentText().strip()
        if voice == "(none)":
            voice = ""

        return {
            "name": self.name_edit.text().strip(),
            "gender": self.gender_combo.currentText(),
            "voice": voice,
            "aliases": aliases,
            "description": self.desc_edit.toPlainText().strip(),
        }
