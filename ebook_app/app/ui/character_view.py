# ebook_app/app/ui/character_view.py
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from ebook_app.app.ui.base_view import BasePage
from ebook_app.tts.voice_catalog import KOKORO_VOICE_LIST

_GENDERS = ["unknown", "male", "female"]


def _normalize_gender(value: str) -> str:
    lowered = (value or "").strip().lower()
    return lowered if lowered in {"male", "female"} else "unknown"


class CharacterDBPage(BasePage):
    """Character database editor: view, add, edit, and delete characters."""

    def __init__(self, *, settings, log, project_manager=None, parent=None):
        self.character_db: list[dict] = []
        super().__init__(settings=settings, log=log, project_manager=project_manager, parent=parent)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        title = QLabel("Character Database")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        self._layout.addWidget(title)

        self._project_label = QLabel("No project loaded.")
        self._project_label.setStyleSheet("color: steelblue;")
        self._layout.addWidget(self._project_label)

        # ── Main splitter: table (left) | detail editor (right) ───────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._layout.addWidget(splitter, stretch=1)

        # ── LEFT: character table ──────────────────────────────────────
        left = QWidget()
        left_vbox = QVBoxLayout(left)
        left_vbox.setContentsMargins(0, 0, 8, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self._add_btn = QPushButton("+ Add Character")
        self._add_btn.clicked.connect(self._on_add_character)
        self._remove_btn = QPushButton("- Remove Selected")
        self._remove_btn.clicked.connect(self._on_remove_character)
        self._reload_btn = QPushButton("↺ Reload from File")
        self._reload_btn.clicked.connect(self._on_reload)
        toolbar.addWidget(self._add_btn)
        toolbar.addWidget(self._remove_btn)
        toolbar.addWidget(self._reload_btn)
        toolbar.addStretch()
        self._save_btn = QPushButton("💾 Save Characters")
        self._save_btn.setStyleSheet("font-weight:bold; padding:6px 14px;")
        self._save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(self._save_btn)
        left_vbox.addLayout(toolbar)

        # Table: Name | Gender | Voice | Description
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Name", "Gender", "Voice", "Description"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.currentCellChanged.connect(self._on_selection_changed)
        left_vbox.addWidget(self._table)

        splitter.addWidget(left)

        # ── RIGHT: detail / quick-edit panel ──────────────────────────
        right_group = QGroupBox("Character Details")
        right_vbox = QVBoxLayout(right_group)

        self._det_name = QLineEdit()
        self._det_name.setPlaceholderText("Character name")
        right_vbox.addWidget(QLabel("Name:"))
        right_vbox.addWidget(self._det_name)

        self._det_gender = QComboBox()
        self._det_gender.addItems(_GENDERS)
        self._det_gender.currentTextChanged.connect(self._on_gender_changed)
        right_vbox.addWidget(QLabel("Gender:"))
        right_vbox.addWidget(self._det_gender)

        self._det_voice = QComboBox()
        self._det_voice.addItems(KOKORO_VOICE_LIST)
        right_vbox.addWidget(QLabel("Voice:"))
        right_vbox.addWidget(self._det_voice)

        right_vbox.addWidget(QLabel("Description / Notes:"))
        self._det_desc = QTextEdit()
        self._det_desc.setPlaceholderText("Optional notes about this character…")
        self._det_desc.setMaximumHeight(120)
        right_vbox.addWidget(self._det_desc)

        apply_btn = QPushButton("Apply Changes")
        apply_btn.clicked.connect(self._on_apply_detail_edit)
        right_vbox.addWidget(apply_btn)

        right_vbox.addStretch()

        splitter.addWidget(right_group)
        splitter.setSizes([600, 300])

        # Wire project signals
        if self.project_manager:
            self.project_manager.project_loaded.connect(self._on_project_loaded)
            self.project_manager.project_closed.connect(self._on_project_closed)

        self._set_controls_enabled(False)
        self._try_load_initial()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_controls_enabled(self, enabled: bool) -> None:
        for w in (self._add_btn, self._remove_btn, self._save_btn,
                  self._reload_btn, self._table):
            w.setEnabled(enabled)

    def _try_load_initial(self) -> None:
        if self.project_manager and self.project_manager.current_book_id:
            self._on_project_loaded(self.project_manager.current_book_id)

    def _on_project_loaded(self, book_id: str) -> None:
        info = (self.project_manager.get_project_info() or {}) if self.project_manager else {}
        title = info.get("title", book_id) or book_id
        self._project_label.setText(f"Project: <b>{title}</b>")
        self._set_controls_enabled(True)
        self.load_character_db()

    def _on_project_closed(self) -> None:
        self._project_label.setText("No project loaded.")
        self._set_controls_enabled(False)
        self._table.setRowCount(0)

    def load_character_db(self) -> None:
        if self.project_manager and hasattr(self.project_manager, "load_character_db"):
            self.character_db = self.project_manager.load_character_db() or []
        else:
            self.character_db = list(self.settings.get("character_db", []) or [])
        self._populate_table()

    def _populate_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for entry in self.character_db:
            self._append_table_row(entry)
        self._table.blockSignals(False)

    def _append_table_row(self, entry: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        name_item = QTableWidgetItem(entry.get("name", ""))
        self._table.setItem(row, 0, name_item)

        gender_combo = QComboBox()
        gender_combo.addItems(_GENDERS)
        gender = _normalize_gender(entry.get("gender", "unknown"))
        gender_combo.setCurrentText(gender)
        self._table.setCellWidget(row, 1, gender_combo)

        voice_combo = QComboBox()
        voice_combo.addItems(KOKORO_VOICE_LIST)
        voice = entry.get("voice", "") or ""
        if voice in KOKORO_VOICE_LIST:
            voice_combo.setCurrentText(voice)
        self._table.setCellWidget(row, 2, voice_combo)

        desc_item = QTableWidgetItem(entry.get("description", ""))
        self._table.setItem(row, 3, desc_item)

    def _collect_table_data(self) -> list[dict]:
        result = []
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            desc_item = self._table.item(row, 3)
            gender_widget = self._table.cellWidget(row, 1)
            voice_widget = self._table.cellWidget(row, 2)
            name = (name_item.text().strip() if name_item else "").strip()
            if not name:
                continue
            result.append({
                "name": name,
                "gender": _normalize_gender(gender_widget.currentText() if gender_widget else "unknown"),
                "voice": (voice_widget.currentText() if voice_widget else "") or "",
                "description": (desc_item.text() if desc_item else "").strip(),
            })
        return result

    def _default_voice_for_gender(self, gender: str) -> str:
        if _normalize_gender(gender) == "male":
            return self.settings.get("default_male_voice", "am_adam")
        if _normalize_gender(gender) == "female":
            return self.settings.get("default_female_voice", "af_bella")
        return self.settings.get("narrator_voice", "af_heart")

    # ------------------------------------------------------------------
    # Detail panel
    # ------------------------------------------------------------------

    def _on_selection_changed(self, current_row: int, *_) -> None:
        if current_row < 0:
            return
        name_item = self._table.item(current_row, 0)
        desc_item = self._table.item(current_row, 3)
        gender_widget = self._table.cellWidget(current_row, 1)
        voice_widget = self._table.cellWidget(current_row, 2)

        self._det_name.setText(name_item.text() if name_item else "")
        self._det_desc.setPlainText(desc_item.text() if desc_item else "")
        if gender_widget:
            self._det_gender.blockSignals(True)
            self._det_gender.setCurrentText(gender_widget.currentText())
            self._det_gender.blockSignals(False)
        if voice_widget:
            self._det_voice.setCurrentText(voice_widget.currentText())

    def _on_gender_changed(self, gender: str) -> None:
        """Auto-suggest a voice when gender changes in the detail panel."""
        suggested = self._default_voice_for_gender(gender)
        if suggested in KOKORO_VOICE_LIST:
            self._det_voice.setCurrentText(suggested)

    def _on_apply_detail_edit(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.blockSignals(True)
        name_item = self._table.item(row, 0)
        if name_item is None:
            name_item = QTableWidgetItem()
            self._table.setItem(row, 0, name_item)
        name_item.setText(self._det_name.text().strip())

        gender_widget = self._table.cellWidget(row, 1)
        if gender_widget:
            gender_widget.setCurrentText(self._det_gender.currentText())

        voice_widget = self._table.cellWidget(row, 2)
        if voice_widget:
            voice_widget.setCurrentText(self._det_voice.currentText())

        desc_item = self._table.item(row, 3)
        if desc_item is None:
            desc_item = QTableWidgetItem()
            self._table.setItem(row, 3, desc_item)
        desc_item.setText(self._det_desc.toPlainText().strip())

        self._table.blockSignals(False)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _on_add_character(self) -> None:
        gender = "unknown"
        entry = {
            "name": "New Character",
            "gender": gender,
            "voice": self._default_voice_for_gender(gender),
            "description": "",
        }
        self._append_table_row(entry)
        new_row = self._table.rowCount() - 1
        self._table.selectRow(new_row)
        self._table.editItem(self._table.item(new_row, 0))

    def _on_remove_character(self) -> None:
        selected_rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        if not selected_rows:
            return
        reply = QMessageBox.question(
            self,
            "Remove Characters",
            f"Remove {len(selected_rows)} selected character(s)?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            for row in selected_rows:
                self._table.removeRow(row)

    def _on_reload(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reload Characters",
            "Reload character database from file? Unsaved changes will be lost.",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.load_character_db()

    def _on_save(self) -> None:
        data = self._collect_table_data()
        if self.project_manager and hasattr(self.project_manager, "save_character_db"):
            self.project_manager.save_character_db(data)
        self.settings.set("character_db", data)
        if hasattr(self.settings, "save"):
            self.settings.save()
        self.character_db = data
        self.log.log(f"Saved {len(data)} character(s) to character database.", level="SUCCESS")
