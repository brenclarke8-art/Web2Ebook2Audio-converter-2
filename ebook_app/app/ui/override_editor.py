# ebook_app/app/ui/override_editor.py
"""Override Editor — UI for managing text override rules and glossary."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QFileDialog, QMessageBox, QCheckBox,
)

logger = logging.getLogger(__name__)


class OverrideEditorWidget(QWidget):
    """Table-based editor for override rules (pattern → replacement)."""

    COLUMNS = ["Pattern", "Replacement", "Regex", "Enabled", "Comment"]

    def __init__(self, config_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Override Rules</b>"))

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add Rule")
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_load = QPushButton("Load JSON…")
        self.btn_save = QPushButton("Save JSON…")
        self.btn_add.clicked.connect(self._add_row)
        self.btn_remove.clicked.connect(self._remove_row)
        self.btn_load.clicked.connect(self._load)
        self.btn_save.clicked.connect(self._save)
        for btn in (self.btn_add, self.btn_remove, self.btn_load, self.btn_save):
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col in range(len(self.COLUMNS)):
            self.table.setItem(row, col, QTableWidgetItem(""))

    def _remove_row(self):
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self.table.removeRow(row)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Override Rules", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.table.setRowCount(0)
            for rule in data:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(rule.get("pattern", "")))
                self.table.setItem(row, 1, QTableWidgetItem(rule.get("replacement", "")))
                self.table.setItem(row, 2, QTableWidgetItem(str(rule.get("is_regex", False))))
                self.table.setItem(row, 3, QTableWidgetItem(str(rule.get("enabled", True))))
                self.table.setItem(row, 4, QTableWidgetItem(rule.get("comment", "")))
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Override Rules", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = []
            for row in range(self.table.rowCount()):
                data.append({
                    "pattern":     (self.table.item(row, 0) or QTableWidgetItem("")).text(),
                    "replacement": (self.table.item(row, 1) or QTableWidgetItem("")).text(),
                    "is_regex":    (self.table.item(row, 2) or QTableWidgetItem("False")).text().lower() == "true",
                    "enabled":     (self.table.item(row, 3) or QTableWidgetItem("True")).text().lower() == "true",
                    "comment":     (self.table.item(row, 4) or QTableWidgetItem("")).text(),
                })
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
