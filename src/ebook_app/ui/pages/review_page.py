# src/ebook_app/ui/pages/review_page.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt, Slot


class ReviewPage(QWidget):
    """
    Review & Dialogue Inspector Page.
    Allows the user to:
        - Select a chapter
        - View Pass‑2 segments
        - View final rebuilt segments
        - Edit speaker/type/text
        - Preview TTS for any segment
        - Save updated final chapter JSON
    """

    def __init__(self, settings, log, project_manager):
        super().__init__()

        self.settings = settings
        self.log_console = log
        self.project_manager = project_manager

        # Currently loaded chapter data
        self.current_chapter_id: str | None = None
        self.pass2_segments: list[dict] = []
        self.final_segments: list[dict] = []

        # --------------------------------------------------------------
        # Layout
        # --------------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Review & Dialogue Inspector")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # --------------------------------------------------------------
        # Chapter selector row
        # --------------------------------------------------------------
        row = QHBoxLayout()
        layout.addLayout(row)

        row.addWidget(QLabel("Chapter:"))

        self.chapter_combo = QComboBox()
        self.chapter_combo.currentIndexChanged.connect(self._on_chapter_changed)
        row.addWidget(self.chapter_combo, 1)

        self.btn_reload = QPushButton("Reload")
        self.btn_reload.clicked.connect(self._reload_current)
        row.addWidget(self.btn_reload)

        # --------------------------------------------------------------
        # Segment table
        # --------------------------------------------------------------
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Paragraph ID", "Type", "Speaker", "Text", "Preview"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        # --------------------------------------------------------------
        # Save button
        # --------------------------------------------------------------
        self.btn_save = QPushButton("Save Final Chapter")
        self.btn_save.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_save.clicked.connect(self._save_final_chapter)
        layout.addWidget(self.btn_save)

        # Load chapter list
        self._load_chapter_list()

    # ------------------------------------------------------------------
    # Load chapter list
    # ------------------------------------------------------------------

    def _load_chapter_list(self):
        chapters = self.project_manager.load_chapter_index()
        self.chapter_combo.clear()

        if not chapters:
            self.chapter_combo.addItem("No chapters found")
            return

        for idx, ch in enumerate(chapters):
            title = ch.get("title", f"Chapter {idx+1}")
            chapter_id = f"ch{idx+1:03d}"
            self.chapter_combo.addItem(f"{idx+1:03d} — {title}", chapter_id)

    # ------------------------------------------------------------------
    # Chapter changed
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_chapter_changed(self, index: int):
        if index < 0:
            return

        chapter_id = self.chapter_combo.currentData()
        if not chapter_id:
            return

        self.current_chapter_id = chapter_id
        self._load_chapter_data()

    # ------------------------------------------------------------------
    # Load Pass‑2 + Final segments
    # ------------------------------------------------------------------

    def _load_chapter_data(self):
        if not self.current_chapter_id:
            return

        # Load Pass‑2
        self.pass2_segments = self.project_manager.load_pass2_segments(
            self.current_chapter_id
        )

        # Load Final
        final = self.project_manager.load_final_chapter(self.current_chapter_id)
        self.final_segments = final.get("segments", []) if final else []

        self._populate_table()

        self.log_console.log(f"Loaded chapter {self.current_chapter_id}")

    # ------------------------------------------------------------------
    # Populate table
    # ------------------------------------------------------------------

    def _populate_table(self):
        segs = self.final_segments or self.pass2_segments

        self.table.setRowCount(len(segs))

        for row, seg in enumerate(segs):
            pid = str(seg.get("paragraph_id", ""))
            typ = seg.get("type", "")
            speaker = seg.get("speaker", "")
            text = seg.get("text", "")

            # Paragraph ID
            self.table.setItem(row, 0, QTableWidgetItem(pid))

            # Type
            self.table.setItem(row, 1, QTableWidgetItem(typ))

            # Speaker
            self.table.setItem(row, 2, QTableWidgetItem(speaker))

            # Text
            item_text = QTableWidgetItem(text)
            item_text.setFlags(item_text.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 3, item_text)

            # Preview button
            btn = QPushButton("▶")
            btn.clicked.connect(lambda _, r=row: self._preview_segment(r))
            self.table.setCellWidget(row, 4, btn)

        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Reload current chapter
    # ------------------------------------------------------------------

    def _reload_current(self):
        if self.current_chapter_id:
            self._load_chapter_data()

    # ------------------------------------------------------------------
    # Preview TTS
    # ------------------------------------------------------------------

    def _preview_segment(self, row: int):
        if not self.current_chapter_id:
            return

        try:
            path = self.project_manager.pipeline_controller.tts_generate_segment(
                chapter_index=int(self.current_chapter_id[2:]) - 1,
                segment_index=row,
            )
            self.log_console.log(f"Preview generated: {path}")
        except Exception as e:
            QMessageBox.critical(self, "TTS Error", str(e))

    # ------------------------------------------------------------------
    # Save final chapter
    # ------------------------------------------------------------------

    def _save_final_chapter(self):
        if not self.current_chapter_id:
            return

        # Update final_segments from table
        for row in range(self.table.rowCount()):
            seg = self.final_segments[row] if row < len(self.final_segments) else {}

            seg["paragraph_id"] = self.table.item(row, 0).text()
            seg["type"] = self.table.item(row, 1).text()
            seg["speaker"] = self.table.item(row, 2).text()
            seg["text"] = self.table.item(row, 3).text()

        # Save via ProjectManager
        self.project_manager.save_final_chapter(
            self.current_chapter_id,
            {"chapter_id": self.current_chapter_id, "segments": self.final_segments},
        )

        self.log_console.log(f"Saved final chapter {self.current_chapter_id}")
        QMessageBox.information(self, "Saved", "Final chapter saved.")
