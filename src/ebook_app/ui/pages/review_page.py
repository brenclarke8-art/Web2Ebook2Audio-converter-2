# src/ebook_app/ui/pages/review_page.py

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QMessageBox
)
from PySide6.QtCore import Qt, Slot

from ebook_app.ui.widgets.segment_table import SegmentTable
from ebook_app.ui.widgets.chapter_selector import ChapterSelector
from ebook_app.ui.widgets.review_inspector_panel import ReviewInspectorPanel


class ReviewPage(QWidget):
    """
    Review & Dialogue Inspector Page.
    Now includes:
        - Left pane: chapter selector, mode toggle, segment table, save button
        - Right pane: ReviewInspectorPanel (metadata, waveform, diff, etc.)
    """

    def __init__(self, settings, log, project_manager):
        super().__init__()

        self.settings = settings
        self.log_console = log
        self.project_manager = project_manager

        # Data
        self.current_chapter_id: str | None = None
        self.pass2_segments: list[dict] = []
        self.final_segments: list[dict] = []

        # --------------------------------------------------------------
        # Main layout: horizontal split
        # --------------------------------------------------------------
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Left side
        left_layout = QVBoxLayout()
        left_layout.setSpacing(10)
        main_layout.addLayout(left_layout, 3)

        # Right side: Inspector Panel
        self.inspector = ReviewInspectorPanel()
        main_layout.addWidget(self.inspector, 2)

        # --------------------------------------------------------------
        # Title
        # --------------------------------------------------------------
        title = QLabel("Review & Dialogue Inspector")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        left_layout.addWidget(title)

        # --------------------------------------------------------------
        # Chapter selector
        # --------------------------------------------------------------
        self.chapter_selector = ChapterSelector(self.project_manager)
        self.chapter_selector.chapter_changed.connect(self._on_chapter_changed)
        left_layout.addWidget(self.chapter_selector)

        # --------------------------------------------------------------
        # Mode toggle (Final / Pass‑2)
        # --------------------------------------------------------------
        mode_row = QHBoxLayout()
        left_layout.addLayout(mode_row)

        mode_row.addWidget(QLabel("View:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Final", "Pass‑2"])
        self.mode_combo.currentIndexChanged.connect(self._refresh_table)
        mode_row.addWidget(self.mode_combo)

        mode_row.addStretch()

        # --------------------------------------------------------------
        # Segment table
        # --------------------------------------------------------------
        self.segment_table = SegmentTable()
        left_layout.addWidget(self.segment_table, 1)

        # Connect selection → inspector
        self.segment_table.table.itemSelectionChanged.connect(self._on_segment_selected)

        # --------------------------------------------------------------
        # Save button
        # --------------------------------------------------------------
        self.btn_save = QPushButton("Save Final Chapter")
        self.btn_save.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_save.clicked.connect(self._save_final_chapter)
        left_layout.addWidget(self.btn_save)

        # --------------------------------------------------------------
        # Inspector signals → ReviewPage
        # --------------------------------------------------------------
        self.inspector.speaker_changed.connect(self._on_speaker_changed)
        self.inspector.text_changed.connect(self._on_text_changed)
        self.inspector.request_preview_tts.connect(self._on_preview_tts)
        self.inspector.request_rerun_llm.connect(self._on_rerun_llm)
        self.inspector.request_open_character.connect(self._on_open_character)

    # ==================================================================
    # Chapter loading
    # ==================================================================
    @Slot(str)
    def _on_chapter_changed(self, chapter_id: str):
        self.current_chapter_id = chapter_id
        self._load_chapter_data()

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

        # Load Character DB into inspector
        if hasattr(self.project_manager, "load_character_db"):
            char_db = self.project_manager.load_character_db()
            self.inspector.load_character_db(char_db)

        self._refresh_table()
        self.log_console.log(f"Loaded chapter {self.current_chapter_id}")

    # ==================================================================
    # Table refresh
    # ==================================================================
    def _refresh_table(self):
        if not self.current_chapter_id:
            return

        mode = self.mode_combo.currentText()

        if mode == "Final" and self.final_segments:
            segments = self.final_segments
        elif mode == "Final" and not self.final_segments:
            segments = self.pass2_segments
        else:
            segments = self.pass2_segments

        self.segment_table.load_segments(segments)

    # ==================================================================
    # Segment selection → Inspector
    # ==================================================================
    def _on_segment_selected(self):
        if not self.current_chapter_id:
            return

        selected = self.segment_table.table.selectedIndexes()
        if not selected:
            return

        row = selected[0].row()

        # Determine mode
        mode = self.mode_combo.currentText()
        if mode == "Final" and self.final_segments:
            segment = self.final_segments[row]
        else:
            segment = self.pass2_segments[row]

        # JSON for diff viewer
        pass2_json = {"segments": self.pass2_segments}
        final_json = {"segments": self.final_segments}

        # Load into inspector
        self.inspector.load_segment(row, segment, pass2_json, final_json)

        # Load waveform
        self._load_waveform_for_segment(row)

    def _load_waveform_for_segment(self, row: int):
        try:
            wav_path = self.project_manager.pipeline_controller.preview_segment(
                self.current_chapter_id,
                row
            )
            self.inspector.load_waveform(wav_path)
        except Exception as e:
            self.log_console.log(f"Waveform load error: {e}")

    # ==================================================================
    # Inspector → ReviewPage updates
    # ==================================================================
    def _on_speaker_changed(self, name: str):
        selected = self.segment_table.table.selectedIndexes()
        if not selected:
            return
        row = selected[0].row()

        mode = self.mode_combo.currentText()
        target = self.final_segments if (mode == "Final" and self.final_segments) else self.pass2_segments
        target[row]["speaker"] = name

        self._refresh_table()

    def _on_text_changed(self, new_text: str):
        selected = self.segment_table.table.selectedIndexes()
        if not selected:
            return
        row = selected[0].row()

        mode = self.mode_combo.currentText()
        target = self.final_segments if (mode == "Final" and self.final_segments) else self.pass2_segments
        target[row]["text"] = new_text

    def _on_preview_tts(self, row: int):
        self._preview_segment(row)

    def _on_rerun_llm(self, row: int):
        self.log_console.log(f"Re-running LLM classification for segment {row}…")
        # TODO: integrate your LLM reclassification pipeline

    def _on_open_character(self, name: str):
        self.log_console.log(f"Open Character DB for: {name}")
        # TODO: switch to CharacterDBPage and select character

    # ==================================================================
    # TTS preview
    # ==================================================================
    def _preview_segment(self, row: int):
        if not self.current_chapter_id:
            return

        try:
            path = self.project_manager.pipeline_controller.preview_segment(
                self.current_chapter_id,
                row
            )
            self.log_console.log(f"Preview generated: {path}")
        except Exception as e:
            QMessageBox.critical(self, "TTS Error", str(e))

    # ==================================================================
    # Save final chapter
    # ==================================================================
    def _save_final_chapter(self):
        if not self.current_chapter_id:
            return

        # Extract edited segments from table
        edited = self.segment_table.extract_segments(
            self.final_segments if self.final_segments else self.pass2_segments
        )

        # Save via ProjectManager
        self.project_manager.save_final_chapter(
            self.current_chapter_id,
            {"chapter_id": self.current_chapter_id, "segments": edited},
        )

        self.final_segments = edited

        self.log_console.log(f"Saved final chapter {self.current_chapter_id}")
        QMessageBox.information(self, "Saved", "Final chapter saved.")
