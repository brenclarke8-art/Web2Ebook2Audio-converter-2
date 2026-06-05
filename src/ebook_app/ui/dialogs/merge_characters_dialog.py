# src/ebook_app/ui/dialogs/merge_characters_dialog.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt, Signal


class MergeCharactersDialog(QDialog):
    """
    Dialog for merging two characters into one.
    Emits:
        merged(character_dict)
    """

    merged = Signal(dict)

    def __init__(self, characters: list[dict], parent=None):
        super().__init__(parent)

        self.characters = characters

        self.setWindowTitle("Merge Characters")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --------------------------------------------------------------
        # Character selectors
        # --------------------------------------------------------------
        row = QHBoxLayout()
        layout.addLayout(row)

        row.addWidget(QLabel("Character A:"))
        self.combo_a = QComboBox()
        row.addWidget(self.combo_a, 1)

        row.addWidget(QLabel("Character B:"))
        self.combo_b = QComboBox()
        row.addWidget(self.combo_b, 1)

        for c in characters:
            name = c.get("name", "Unnamed")
            self.combo_a.addItem(name)
            self.combo_b.addItem(name)

        # --------------------------------------------------------------
        # Preview area
        # --------------------------------------------------------------
        layout.addWidget(QLabel("Merged Result Preview:"))

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(120)
        layout.addWidget(self.preview)

        # Update preview when selection changes
        self.combo_a.currentIndexChanged.connect(self._update_preview)
        self.combo_b.currentIndexChanged.connect(self._update_preview)

        # --------------------------------------------------------------
        # Buttons
        # --------------------------------------------------------------
        btn_row = QHBoxLayout()
        layout.addLayout(btn_row)

        self.btn_ok = QPushButton("Merge")
        self.btn_cancel = QPushButton("Cancel")

        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(self.btn_cancel)

        self.btn_ok.clicked.connect(self._do_merge)
        self.btn_cancel.clicked.connect(self.reject)

        # Initial preview
        self._update_preview()

    # ------------------------------------------------------------------
    # Preview logic
    # ------------------------------------------------------------------

    def _update_preview(self):
        a = self.characters[self.combo_a.currentIndex()]
        b = self.characters[self.combo_b.currentIndex()]

        merged = self._merge_preview(a, b)

        text = (
            f"Name: {merged['name']}\n"
            f"Gender: {merged['gender']}\n"
            f"Voice: {merged['voice']}\n"
            f"Aliases: {', '.join(merged['aliases'])}\n"
            f"Description:\n{merged['description']}"
        )

        self.preview.setPlainText(text)

    def _merge_preview(self, a: dict, b: dict) -> dict:
        """
        Non-destructive preview of merged character.
        """
        name = a.get("name") or b.get("name") or "Unnamed"
        gender = a.get("gender") if a.get("gender") != "unknown" else b.get("gender")
        voice = a.get("voice") or b.get("voice") or ""

        aliases = set(a.get("aliases", [])) | set(b.get("aliases", []))
        aliases |= {a.get("name", ""), b.get("name", "")}

        desc = a.get("description", "").strip()
        if not desc:
            desc = b.get("description", "").strip()

        return {
            "name": name,
            "gender": gender or "unknown",
            "voice": voice,
            "aliases": sorted(a for a in aliases if a),
            "description": desc,
        }

    # ------------------------------------------------------------------
    # Merge action
    # ------------------------------------------------------------------

    def _do_merge(self):
        idx_a = self.combo_a.currentIndex()
        idx_b = self.combo_b.currentIndex()

        if idx_a == idx_b:
            QMessageBox.warning(self, "Invalid Selection", "Select two different characters.")
            return

        a = self.characters[idx_a]
        b = self.characters[idx_b]

        merged = self._merge_preview(a, b)

        # Emit merged result
        self.merged.emit(merged)
        self.accept()
