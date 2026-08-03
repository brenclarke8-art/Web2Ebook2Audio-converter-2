# ebook_app/app/ui/review_view.py
"""Review page — inspect and edit classified segments before audio generation."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QWidget,
)

from ebook_app.app.ui.base_view import BasePage
from ebook_app.app.widgets.review_inspector_panel import ReviewInspectorPanel
from ebook_app.app.widgets.segment_table import SegmentTable

logger = logging.getLogger(__name__)


class ReviewPage(BasePage):
    """Page for reviewing LLM-classified dialogue segments before TTS generation."""

    def _build_ui(self) -> None:
        self._segments: list[dict] = []
        self._pass2_json: dict = {}
        self._final_json: dict = {}
        self._current_chapter_id: Optional[str] = None

        # ── toolbar ──────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("<b>Review Segments</b>"))

        toolbar.addWidget(QLabel("Chapter:"))
        self._chapter_combo = QComboBox()
        self._chapter_combo.setMinimumWidth(180)
        self._chapter_combo.currentIndexChanged.connect(self._on_chapter_changed)
        toolbar.addWidget(self._chapter_combo)

        load_btn = QPushButton("🔄 Load")
        load_btn.clicked.connect(self._reload_chapters)
        toolbar.addWidget(load_btn)

        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(save_btn)

        toolbar.addStretch()
        self._layout.addLayout(toolbar)

        # ── splitter: table | inspector ───────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._table = SegmentTable()
        self._table.table.currentCellChanged.connect(self._on_cell_changed)
        splitter.addWidget(self._table)

        self._inspector = ReviewInspectorPanel()
        self._inspector.speaker_changed.connect(self._on_speaker_changed)
        self._inspector.text_changed.connect(self._on_text_changed)
        splitter.addWidget(self._inspector)
        splitter.setSizes([560, 320])

        self._layout.addWidget(splitter, 1)

        # Refresh on project load
        if self.project_manager:
            self.project_manager.project_loaded.connect(self._reload_chapters)

        self._reload_chapters()

    # ------------------------------------------------------------------

    def _reload_chapters(self) -> None:
        self._chapter_combo.blockSignals(True)
        self._chapter_combo.clear()

        chapters: list[dict] = []
        if self.project_manager:
            chapters = self.project_manager.load_chapter_index()

        for i, ch in enumerate(chapters):
            label = ch.get("title") or ch.get("chapter_id") or f"Chapter {i + 1}"
            chapter_id = ch.get("chapter_id") or f"ch{i + 1:03d}"
            self._chapter_combo.addItem(label, userData=chapter_id)

        self._chapter_combo.blockSignals(False)

        if self._chapter_combo.count() > 0:
            self._on_chapter_changed(0)

    def _on_chapter_changed(self, idx: int) -> None:
        if idx < 0 or not self.project_manager:
            return
        chapter_id: str = self._chapter_combo.itemData(idx) or ""
        self._current_chapter_id = chapter_id

        self._pass2_json = {}
        self._final_json = {}

        raw_segs = self.project_manager.load_pass2_segments(chapter_id)
        self._final_json = self.project_manager.load_final_chapter(chapter_id)
        self._segments = self._final_json.get("segments", raw_segs)

        char_db = self.project_manager.load_character_db() if self.project_manager else []
        self._inspector.load_character_db(list(char_db))

        self._table.load_segments(self._segments)
        self._inspector.clear()

    def _on_cell_changed(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if 0 <= row < len(self._segments):
            self._inspector.load_segment(
                row,
                self._segments[row],
                self._pass2_json,
                self._final_json,
            )

    def _on_speaker_changed(self, name: str) -> None:
        row = self._table.table.currentRow()
        if 0 <= row < len(self._segments):
            self._segments[row]["speaker"] = name

    def _on_text_changed(self, text: str) -> None:
        row = self._table.table.currentRow()
        if 0 <= row < len(self._segments):
            self._segments[row]["text"] = text

    def _on_save(self) -> None:
        if not self._current_chapter_id or not self.project_manager:
            return
        # Flush any edits from the table back into _segments
        self._segments = self._table.extract_segments(self._segments)
        data = dict(self._final_json)
        data["segments"] = self._segments
        self.project_manager.save_final_chapter(self._current_chapter_id, data)
        if self.log:
            self.log.log(
                f"Saved {len(self._segments)} segments for "
                f"chapter '{self._current_chapter_id}'.",
                "SUCCESS",
            )
        logger.info("Saved segments for chapter %s.", self._current_chapter_id)
