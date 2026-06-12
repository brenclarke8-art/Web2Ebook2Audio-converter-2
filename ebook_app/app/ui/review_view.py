# ebook_app/app/ui/review_view.py
"""
Review page — inspect per-chapter pipeline output and edit segment assignments.

Tabs:
  1. Scraped Text    — raw scraped content from chapters_raw.json
  2. Cleaned Text    — cleaned text from ch{N}_cleaned.txt
  3. Pass-1 Segments — deterministic extraction result (ch{N}_pass1.json)
  4. Pass-2 / Final  — LLM classification + editable speaker/type assignments
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ebook_app.app.ui.base_view import BasePage
from ebook_app.tts.voice_catalog import KOKORO_VOICE_LIST

_SEGMENT_TYPES = ["narration", "dialogue", "thought"]
_GENDERS = ["unknown", "male", "female"]


def _normalize_type(value: str) -> str:
    lowered = (value or "").strip().lower()
    return lowered if lowered in {"dialogue", "thought", "narration"} else "narration"


def _normalize_gender(value: str) -> str:
    lowered = (value or "").strip().lower()
    return lowered if lowered in {"male", "female"} else "unknown"


class ReviewPage(BasePage):
    """Chapter review page: inspect scraped/cleaned/segmented data and edit assignments."""

    def __init__(self, *, settings, log, project_manager=None, parent=None):
        self.current_chapter_id: str | None = None
        self.pass2_segments: list[dict] = []
        self.final_segments: list[dict] = []
        super().__init__(settings=settings, log=log, project_manager=project_manager, parent=parent)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        title = QLabel("Review & Dialogue Inspector")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        self._layout.addWidget(title)

        self._project_label = QLabel("No project loaded.")
        self._project_label.setStyleSheet("color: steelblue;")
        self._layout.addWidget(self._project_label)

        # ── Chapter selector row ────────────────────────────────────────
        chapter_row = QHBoxLayout()
        chapter_row.addWidget(QLabel("Chapter:"))
        self._chapter_combo = QComboBox()
        self._chapter_combo.setMinimumWidth(280)
        self._chapter_combo.currentIndexChanged.connect(self._on_chapter_combo_changed)
        chapter_row.addWidget(self._chapter_combo)
        self._reload_chapters_btn = QPushButton("↺ Reload Chapter List")
        self._reload_chapters_btn.clicked.connect(self._load_chapter_list)
        chapter_row.addWidget(self._reload_chapters_btn)
        chapter_row.addStretch()
        self._layout.addLayout(chapter_row)

        # ── Tab widget ─────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._layout.addWidget(self._tabs, stretch=1)

        # Tab 1: Scraped Text
        tab1 = QWidget()
        t1_vbox = QVBoxLayout(tab1)
        t1_vbox.addWidget(QLabel(
            "<i>Raw text recovered from the web scraper for this chapter.</i>"
        ))
        self._scraped_view = QPlainTextEdit()
        self._scraped_view.setReadOnly(True)
        self._scraped_view.setStyleSheet(
            "font-family: monospace; font-size: 12px;"
        )
        t1_vbox.addWidget(self._scraped_view)
        self._tabs.addTab(tab1, "Scraped Text")

        # Tab 2: Cleaned Text
        tab2 = QWidget()
        t2_vbox = QVBoxLayout(tab2)
        t2_vbox.addWidget(QLabel(
            "<i>Text after HTML cleaning and normalization.</i>"
        ))
        self._cleaned_view = QPlainTextEdit()
        self._cleaned_view.setReadOnly(True)
        self._cleaned_view.setStyleSheet(
            "font-family: monospace; font-size: 12px;"
        )
        t2_vbox.addWidget(self._cleaned_view)
        self._tabs.addTab(tab2, "Cleaned Text")

        # Tab 3: Pass-1 Segments
        tab3 = QWidget()
        t3_vbox = QVBoxLayout(tab3)
        t3_vbox.addWidget(QLabel(
            "<i>Deterministic Pass-1 extraction — identifies potential dialogue "
            "boundaries without LLM assistance.</i>"
        ))
        self._pass1_table = QTableWidget(0, 3)
        self._pass1_table.setHorizontalHeaderLabels(["Type", "Speaker (raw)", "Text"])
        self._pass1_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._pass1_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._pass1_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._pass1_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._pass1_table.setAlternatingRowColors(True)
        self._pass1_table.verticalHeader().setVisible(False)
        t3_vbox.addWidget(self._pass1_table)
        self._tabs.addTab(tab3, "Pass-1 Segments")

        # Tab 4: Pass-2 / Final Segments (editable)
        tab4 = QWidget()
        t4_vbox = QVBoxLayout(tab4)
        t4_vbox.addWidget(QLabel(
            "<i>LLM Pass-2 classification — edit speaker and segment type, then "
            "save.  These edits are used when running 'Continue Audio + Export'.</i>"
        ))
        self._pass2_table = QTableWidget(0, 3)
        self._pass2_table.setHorizontalHeaderLabels(["Text", "Speaker", "Type"])
        self._pass2_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._pass2_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._pass2_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._pass2_table.setAlternatingRowColors(True)
        self._pass2_table.verticalHeader().setVisible(False)
        t4_vbox.addWidget(self._pass2_table, stretch=1)

        p2_btn_row = QHBoxLayout()
        self._save_segments_btn = QPushButton("💾 Save Segment Edits")
        self._save_segments_btn.setStyleSheet("font-weight:bold; padding:6px 14px;")
        self._save_segments_btn.clicked.connect(self._on_save_segment_edits)
        p2_btn_row.addWidget(self._save_segments_btn)
        self._rerun_llm_btn = QPushButton("🔄 Re-run LLM Classification")
        self._rerun_llm_btn.setToolTip(
            "Re-run Pass-2 LLM classification for this chapter and reload the results."
        )
        self._rerun_llm_btn.clicked.connect(self._on_rerun_llm)
        p2_btn_row.addWidget(self._rerun_llm_btn)
        p2_btn_row.addStretch()
        t4_vbox.addLayout(p2_btn_row)

        self._tabs.addTab(tab4, "Pass-2 / Final Segments")

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
        for w in (
            self._chapter_combo, self._reload_chapters_btn,
            self._save_segments_btn, self._rerun_llm_btn,
        ):
            w.setEnabled(enabled)

    def _try_load_initial(self) -> None:
        if self.project_manager and self.project_manager.current_book_id:
            self._on_project_loaded(self.project_manager.current_book_id)

    def _on_project_loaded(self, book_id: str) -> None:
        info = (self.project_manager.get_project_info() or {}) if self.project_manager else {}
        title = info.get("title", book_id) or book_id
        self._project_label.setText(f"Project: <b>{title}</b>")
        self._set_controls_enabled(True)
        self._load_chapter_list()

    def _on_project_closed(self) -> None:
        self._project_label.setText("No project loaded.")
        self._set_controls_enabled(False)
        self._chapter_combo.clear()
        self._clear_all_views()

    def _clear_all_views(self) -> None:
        self._scraped_view.clear()
        self._cleaned_view.clear()
        self._pass1_table.setRowCount(0)
        self._pass2_table.setRowCount(0)
        self.current_chapter_id = None
        self.pass2_segments = []
        self.final_segments = []

    def _work_dir(self) -> Path | None:
        if not self.project_manager:
            return None
        return self.project_manager.get_work_dir()

    # ------------------------------------------------------------------
    # Chapter list loading
    # ------------------------------------------------------------------

    def _load_chapter_list(self) -> None:
        self._chapter_combo.blockSignals(True)
        self._chapter_combo.clear()

        work_dir = self._work_dir()
        if not work_dir:
            self._chapter_combo.blockSignals(False)
            return

        chapters_file = work_dir / "chapters_raw.json"
        if chapters_file.exists():
            try:
                chapters = json.loads(chapters_file.read_text(encoding="utf-8"))
                for idx, ch in enumerate(chapters):
                    chapter_id = f"ch{idx + 1:03d}"
                    label = ch.get("title") or chapter_id
                    self._chapter_combo.addItem(f"{chapter_id} — {label}", userData=chapter_id)
            except Exception as exc:
                self.log.log(f"Failed to load chapter list: {exc}", level="WARNING")
        else:
            # No scraped chapters yet — fall back to scanning for cleaned text files
            cleaned_files = sorted(work_dir.glob("ch*_cleaned.txt"))
            for p in cleaned_files:
                chapter_id = p.name.split("_cleaned")[0]
                self._chapter_combo.addItem(chapter_id, userData=chapter_id)

        self._chapter_combo.blockSignals(False)

        if self._chapter_combo.count() > 0:
            self._chapter_combo.setCurrentIndex(0)
            self._on_chapter_combo_changed(0)

    # ------------------------------------------------------------------
    # Chapter data loading
    # ------------------------------------------------------------------

    def _on_chapter_combo_changed(self, index: int) -> None:
        if index < 0:
            return
        chapter_id = self._chapter_combo.itemData(index)
        if not chapter_id:
            return
        self.current_chapter_id = chapter_id
        self._load_chapter_data(chapter_id)

    def _load_chapter_data(self, chapter_id: str) -> None:
        work_dir = self._work_dir()
        if not work_dir:
            return

        # Tab 1 — Scraped text from chapters_raw.json
        self._load_scraped_text(chapter_id, work_dir)
        # Tab 2 — Cleaned text
        self._load_cleaned_text(chapter_id, work_dir)
        # Tab 3 — Pass-1 segments
        self._load_pass1_segments(chapter_id, work_dir)
        # Tab 4 — Pass-2 / Final segments
        self._load_pass2_segments(chapter_id, work_dir)

    def _load_scraped_text(self, chapter_id: str, work_dir: Path) -> None:
        self._scraped_view.clear()
        # Extract from chapters_raw.json by matching chapter_id
        try:
            idx = int(chapter_id[2:]) - 1  # "ch001" → 0
        except (ValueError, IndexError):
            idx = -1

        raw_file = work_dir / "chapters_raw.json"
        if raw_file.exists() and idx >= 0:
            try:
                chapters = json.loads(raw_file.read_text(encoding="utf-8"))
                if idx < len(chapters):
                    ch = chapters[idx]
                    url = ch.get("source", "")
                    title = ch.get("title", "")
                    header = f"URL: {url}\nTitle: {title}\n\n"
                    content = ch.get("content", "") or ch.get("raw_text", "")
                    self._scraped_view.setPlainText(header + content)
                    return
            except Exception:
                pass

        # Fall back to a separate scraped file if it exists
        scraped_path = work_dir / f"{chapter_id}_scraped.txt"
        if scraped_path.exists():
            self._scraped_view.setPlainText(scraped_path.read_text(encoding="utf-8"))
        else:
            self._scraped_view.setPlainText("(Scraped text not available for this chapter)")

    def _load_cleaned_text(self, chapter_id: str, work_dir: Path) -> None:
        self._cleaned_view.clear()
        cleaned_path = work_dir / f"{chapter_id}_cleaned.txt"
        if cleaned_path.exists():
            self._cleaned_view.setPlainText(cleaned_path.read_text(encoding="utf-8"))
        else:
            self._cleaned_view.setPlainText("(Cleaned text not yet available — run pipeline phases 1–2 first)")

    def _load_pass1_segments(self, chapter_id: str, work_dir: Path) -> None:
        self._pass1_table.setRowCount(0)
        for candidate in (
            work_dir / f"{chapter_id}_pass1.json",
        ):
            if candidate.exists():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    segments = data if isinstance(data, list) else data.get("segments", [])
                    for seg in segments:
                        self._add_pass1_row(seg)
                    return
                except Exception as exc:
                    self.log.log(f"Failed to load pass-1 data: {exc}", level="WARNING")
                    return
        self._pass1_table.setRowCount(1)
        item = QTableWidgetItem("(Pass-1 data not yet available — run pipeline phase 3 first)")
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._pass1_table.setSpan(0, 0, 1, 3)
        self._pass1_table.setItem(0, 0, item)

    def _add_pass1_row(self, seg: dict) -> None:
        row = self._pass1_table.rowCount()
        self._pass1_table.insertRow(row)
        self._pass1_table.setItem(row, 0, QTableWidgetItem(seg.get("type", "")))
        self._pass1_table.setItem(row, 1, QTableWidgetItem(seg.get("speaker", "")))
        text_item = QTableWidgetItem(seg.get("text", ""))
        text_item.setToolTip(seg.get("text", ""))
        self._pass1_table.setItem(row, 2, text_item)
        self._pass1_table.resizeRowToContents(row)

    def _load_pass2_segments(self, chapter_id: str, work_dir: Path) -> None:
        self._pass2_table.setRowCount(0)
        self.pass2_segments = []
        self.final_segments = []

        # Try files in priority order
        for candidate in (
            work_dir / f"{chapter_id}_chapter_info_final.json",
            work_dir / f"{chapter_id}_final.json",
            work_dir / f"{chapter_id}_llm_normalized.json",
            work_dir / f"{chapter_id}_pass2.json",
            work_dir / f"{chapter_id}_llm_raw.json",
        ):
            if candidate.exists():
                try:
                    raw = json.loads(candidate.read_text(encoding="utf-8"))
                    segments = raw if isinstance(raw, list) else raw.get("segments", [])
                    self.pass2_segments = segments
                    self._populate_pass2_table(segments)
                    return
                except Exception as exc:
                    self.log.log(f"Failed to load segment data from {candidate.name}: {exc}", level="WARNING")
                    return

        # Nothing found
        self._pass2_table.setRowCount(1)
        item = QTableWidgetItem(
            "(Segment data not yet available — run pipeline phases 3–4 first)"
        )
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._pass2_table.setSpan(0, 0, 1, 3)
        self._pass2_table.setItem(0, 0, item)

    def _populate_pass2_table(self, segments: list[dict]) -> None:
        # Build speaker list from character DB + known speakers in segments
        all_speakers = self._get_known_speakers(segments)

        for seg in segments:
            row = self._pass2_table.rowCount()
            self._pass2_table.insertRow(row)

            text_item = QTableWidgetItem(seg.get("text", ""))
            text_item.setToolTip(seg.get("text", ""))
            self._pass2_table.setItem(row, 0, text_item)

            speaker_combo = QComboBox()
            speaker_combo.setEditable(True)
            speaker_combo.addItems(all_speakers)
            current_speaker = seg.get("speaker", "narrator") or "narrator"
            if current_speaker not in all_speakers:
                speaker_combo.insertItem(0, current_speaker)
            speaker_combo.setCurrentText(current_speaker)
            self._pass2_table.setCellWidget(row, 1, speaker_combo)

            type_combo = QComboBox()
            type_combo.addItems(_SEGMENT_TYPES)
            seg_type = _normalize_type(seg.get("type", "narration"))
            type_combo.setCurrentText(seg_type)
            self._pass2_table.setCellWidget(row, 2, type_combo)

            self._pass2_table.resizeRowToContents(row)

    def _get_known_speakers(self, segments: list[dict]) -> list[str]:
        speakers: list[str] = ["narrator"]
        # Add from character DB
        if self.project_manager:
            char_db = self.project_manager.load_character_db() or []
            for ch in char_db:
                name = (ch.get("name") or "").strip()
                if name and name not in speakers:
                    speakers.append(name)
        # Add from current segments
        for seg in segments:
            sp = (seg.get("speaker") or "").strip()
            if sp and sp not in speakers:
                speakers.append(sp)
        return speakers

    def _collect_pass2_table_data(self) -> list[dict]:
        result = []
        for row in range(self._pass2_table.rowCount()):
            text_item = self._pass2_table.item(row, 0)
            if text_item is None:
                continue
            speaker_widget = self._pass2_table.cellWidget(row, 1)
            type_widget = self._pass2_table.cellWidget(row, 2)
            base = dict(self.pass2_segments[row]) if row < len(self.pass2_segments) else {}
            base["text"] = text_item.text()
            base["speaker"] = speaker_widget.currentText() if speaker_widget else base.get("speaker", "narrator")
            base["type"] = _normalize_type(type_widget.currentText() if type_widget else base.get("type", "narration"))
            result.append(base)
        return result

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _on_chapter_changed(self, chapter_id: str) -> None:
        """Legacy helper used by external callers."""
        self.current_chapter_id = chapter_id

    def _on_save_segment_edits(self) -> None:
        if not self.current_chapter_id or not self.project_manager:
            QMessageBox.warning(self, "No Chapter", "No chapter is selected.")
            return

        work_dir = self._work_dir()
        if not work_dir:
            return

        updated = self._collect_pass2_table_data()
        chapter_id = self.current_chapter_id

        # Write to all output files that already exist for this chapter
        written = []
        for candidate in (
            work_dir / f"{chapter_id}_chapter_info_final.json",
            work_dir / f"{chapter_id}_final.json",
            work_dir / f"{chapter_id}_llm_normalized.json",
            work_dir / f"{chapter_id}_pass2.json",
        ):
            if candidate.exists():
                try:
                    raw = json.loads(candidate.read_text(encoding="utf-8"))
                    if isinstance(raw, list):
                        candidate.write_text(
                            json.dumps(updated, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    else:
                        raw["segments"] = updated
                        candidate.write_text(
                            json.dumps(raw, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    written.append(candidate.name)
                except Exception as exc:
                    self.log.log(f"Failed to write {candidate.name}: {exc}", level="ERROR")

        if not written:
            # Create the final file even if no prior files exist
            final_path = work_dir / f"{chapter_id}_chapter_info_final.json"
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.write_text(
                json.dumps({"segments": updated}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written.append(final_path.name)

        self.pass2_segments = updated
        self.final_segments = updated
        self.log.log(
            f"Saved {len(updated)} segments for {chapter_id} "
            f"→ {', '.join(written)}",
            level="SUCCESS",
        )

    def _save_final_chapter(self) -> None:
        """Legacy helper kept for external callers."""
        self._on_save_segment_edits()

    def _on_rerun_llm(self) -> None:
        if not self.project_manager or not self.current_chapter_id:
            QMessageBox.warning(self, "No Chapter", "No chapter is selected.")
            return

        reply = QMessageBox.question(
            self,
            "Re-run LLM",
            f"Re-run Pass-2 LLM classification for chapter {self.current_chapter_id}?\n"
            "This will overwrite existing segment assignments.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            ctrl = self.project_manager.create_pipeline_controller()
            if ctrl is None:
                self.log.log("No pipeline controller available.", level="ERROR")
                return
            self.log.log(
                f"Re-running Pass-2 classification for {self.current_chapter_id}…",
                level="INFO",
            )
            ctrl.pass2_classification()
            ctrl.smart_review_dialogue()
            self._load_pass2_segments(self.current_chapter_id, self._work_dir())
            self.log.log("LLM re-classification complete.", level="SUCCESS")
        except Exception as exc:
            self.log.log(f"LLM re-classification failed: {exc}", level="ERROR")
            QMessageBox.critical(self, "Error", f"Re-run failed:\n{exc}")
