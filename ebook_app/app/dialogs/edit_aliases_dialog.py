# ebook_app/app/dialogs/edit_aliases_dialog.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QLineEdit, QMessageBox
)
from PySide6.QtCore import Qt, Signal


class EditAliasesDialog(QDialog):
    """
    Dialog for editing a character's alias list.
    Emits:
        aliases_updated(list[str])
    """

    aliases_updated = Signal(list)

    def __init__(self, aliases: list[str], parent=None):
        super().__init__(parent)

        self.setWindowTitle("Edit Aliases")
        self.setMinimumWidth(360)

        # Make a working copy
        self.aliases = list(aliases)

        # --------------------------------------------------------------
        # Layout
        # --------------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Aliases:"))

        # --------------------------------------------------------------
        # Alias list
        # --------------------------------------------------------------
        self.list_widget = QListWidget()
        for a in self.aliases:
            self.list_widget.addItem(a)
        layout.addWidget(self.list_widget)

        # --------------------------------------------------------------
        # Add alias row
        # --------------------------------------------------------------
        add_row = QHBoxLayout()
        layout.addLayout(add_row)

        self.add_edit = QLineEdit()
        self.add_edit.setPlaceholderText("New alias…")
        add_row.addWidget(self.add_edit)

        self.btn_add = QPushButton("Add")
        self.btn_add.clicked.connect(self._add_alias)
        add_row.addWidget(self.btn_add)

        # --------------------------------------------------------------
        # Remove button
        # --------------------------------------------------------------
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self._remove_selected)
        layout.addWidget(self.btn_remove)

        # --------------------------------------------------------------
        # OK / Cancel buttons
        # --------------------------------------------------------------
        btn_row = QHBoxLayout()
        layout.addLayout(btn_row)

        self.btn_ok = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")

        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(self.btn_cancel)

        self.btn_ok.clicked.connect(self._save)
        self.btn_cancel.clicked.connect(self.reject)

    # ------------------------------------------------------------------
    # Add alias
    # ------------------------------------------------------------------

    def _add_alias(self):
        alias = self.add_edit.text().strip()
        if not alias:
            return

        if alias in self.aliases:
            QMessageBox.warning(self, "Duplicate", "Alias already exists.")
            return

        self.aliases.append(alias)
        self.list_widget.addItem(alias)
        self.add_edit.clear()

    # ------------------------------------------------------------------
    # Remove selected alias
    # ------------------------------------------------------------------

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return

        alias = self.aliases[row]
        self.aliases.remove(alias)
        self.list_widget.takeItem(row)

    # ------------------------------------------------------------------
    # Save + emit
    # ------------------------------------------------------------------

    def _save(self):
        # Clean + sort
        cleaned = sorted(a.strip() for a in self.aliases if a.strip())

        self.aliases_updated.emit(cleaned)
        self.accept()
