# ebook_app/app/ui/pipeline_view.py
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QSplitter,
    QVBoxLayout, QWidget,
)

from ebook_app.app.ui.base_view import BasePage
from ebook_app.app.ui.book_manager import BookManagerWidget


class _PipelineWorker(QThread):
    RUN_TO_REVIEW = 'run_to_review'
    CONTINUE_AUDIO = 'continue_audio'
    CHECK_INDEX = 'check_index'

    log_message = Signal(str, str)
    inventory_ready = Signal(dict)
    finished_ok = Signal(str, str)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(self, *, project_manager, settings, mode, start_ch=1, end_ch=0):
        super().__init__()
        self.project_manager = project_manager
        self.settings = settings
        self.mode = mode
        self._start = start_ch
        self._end = end_ch
        self._cancel_requested = False

    def request_stop(self):
        self._cancel_requested = True

    def _abort_if_cancelled(self) -> bool:
        if self._cancel_requested:
            self.cancelled.emit('Pipeline cancelled by user.')
            return True
        return False

    def _run_to_review(self, ctrl):
        import json as _json

        cached_urls = list(getattr(self.project_manager, 'get_chapter_urls', lambda: [])() or [])
        cached_inventory = getattr(self.project_manager, 'get_inventory', lambda: {})() or {}
        if cached_urls:
            raw_count = int(cached_inventory.get('raw_chapter_count') or len(cached_urls))
            valid_count = int(cached_inventory.get('valid_chapter_count') or 0)
            if valid_count <= 0 or valid_count > len(cached_urls):
                valid_count = len(cached_urls)
            self.inventory_ready.emit({'raw_count': raw_count, 'valid_count': valid_count, 'chapter_urls': cached_urls})
        else:
            # Phase 1 — scrape index, build chapters_raw.json
            ctrl.scrape_index()
            # Read inventory from chapters_raw.json written by scrape_index
            work_dir = getattr(self.project_manager, 'get_work_dir', lambda: None)()
            chapter_urls: list[str] = []
            if work_dir is not None:
                chapters_raw_path = work_dir / 'chapters_raw.json'
                if chapters_raw_path.exists():
                    try:
                        chapters_data = _json.loads(chapters_raw_path.read_text(encoding='utf-8'))
                        chapter_urls = [c.get('source', '') for c in chapters_data if c.get('source')]
                    except Exception:
                        pass
            count = len(chapter_urls)
            self.inventory_ready.emit({'raw_count': count, 'valid_count': count, 'chapter_urls': chapter_urls})

        if self._abort_if_cancelled():
            return

        # Phase 2 — scrape chapter text
        ctrl.scrape_chapters()
        if self._abort_if_cancelled():
            return

        # Phase 3 — deterministic Pass-1 extraction
        ctrl.pass1_extraction()
        if self._abort_if_cancelled():
            return

        # Phase 4 — LLM-based Pass-2 classification
        ctrl.pass2_classification()
        self.finished_ok.emit(self.RUN_TO_REVIEW, 'Processing complete. Review detected characters in the Review tab before audio.')

    def _run_continue_audio(self, ctrl):
        # Phase 5 — rebuild final chapters from reviewed characters
        ctrl.smart_review_dialogue()
        # Phase 6 — TTS audio generation
        ctrl.tts_generate()
        # Phase 7 — EPUB build
        ctrl.epub_build()

    def _run_check_index(self, ctrl):
        ctrl.scrape_index()
        work_dir = self.project_manager.get_work_dir() if self.project_manager else None
        chapter_urls: list[str] = []
        if work_dir is not None:
            chapters_raw_path = work_dir / 'chapters_raw.json'
            if chapters_raw_path.exists():
                try:
                    chapters_data = json.loads(chapters_raw_path.read_text(encoding='utf-8'))
                    chapter_urls = [c.get('source', '') for c in chapters_data if c.get('source')]
                except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
                    self.log_message.emit(
                        f"Failed to load indexed chapters from {chapters_raw_path}: {exc}",
                        "WARNING",
                    )
        count = len(chapter_urls)
        self.inventory_ready.emit({'raw_count': count, 'valid_count': count, 'chapter_urls': chapter_urls})
        self.finished_ok.emit(self.CHECK_INDEX, f'Indexing complete. Found {count} chapters.')

    def run(self):
        try:
            ctrl = self.project_manager.create_pipeline_controller()
            if self.mode == self.RUN_TO_REVIEW:
                self._run_to_review(ctrl)
            elif self.mode == self.CONTINUE_AUDIO:
                self._run_continue_audio(ctrl)
                self.finished_ok.emit(self.CONTINUE_AUDIO, 'Audio generation complete.')
            elif self.mode == self.CHECK_INDEX:
                self._run_check_index(ctrl)
        except Exception as exc:
            self.failed.emit(str(exc))


class PipelinePage(BasePage):
    def __init__(self, *, settings, log, project_manager=None, parent=None):
        self._worker = None
        super().__init__(settings=settings, log=log, project_manager=project_manager, parent=parent)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Title
        title = QLabel("Pipeline")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        self._layout.addWidget(title)

        # Main splitter: left = book library, right = project + pipeline controls
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._layout.addWidget(splitter, stretch=1)

        # ── LEFT: Book Library ─────────────────────────────────────────
        left_panel = QWidget()
        left_vbox = QVBoxLayout(left_panel)
        left_vbox.setContentsMargins(0, 0, 8, 0)
        left_vbox.setSpacing(8)

        self._book_manager = BookManagerWidget(self.project_manager)
        self._book_manager.book_opened.connect(self._on_project_opened)
        left_vbox.addWidget(self._book_manager)
        splitter.addWidget(left_panel)

        # ── RIGHT: Project Details + Pipeline Controls ─────────────────
        right_panel = QWidget()
        right_vbox = QVBoxLayout(right_panel)
        right_vbox.setContentsMargins(8, 0, 0, 0)
        right_vbox.setSpacing(12)
        splitter.addWidget(right_panel)

        # Active project group
        proj_group = QGroupBox("Active Project")
        proj_form = QFormLayout(proj_group)

        self._proj_title_label = QLabel("—")
        proj_form.addRow("Title:", self._proj_title_label)

        self._proj_author_label = QLabel("—")
        proj_form.addRow("Author:", self._proj_author_label)

        index_row = QHBoxLayout()
        self._index_url_edit = QLineEdit()
        self._index_url_edit.setPlaceholderText("https://example.com/novel/")
        index_row.addWidget(self._index_url_edit)
        self._save_url_btn = QPushButton("Save URL")
        self._save_url_btn.clicked.connect(self._on_save_index_url)
        index_row.addWidget(self._save_url_btn)
        proj_form.addRow("Index URL:", index_row)

        actions_row = QHBoxLayout()
        self._index_chapters_btn = QPushButton("Index Chapters")
        self._index_chapters_btn.clicked.connect(self._on_index_chapters)
        actions_row.addWidget(self._index_chapters_btn)
        actions_row.addStretch()
        proj_form.addRow("Actions:", actions_row)

        right_vbox.addWidget(proj_group)

        # Chapter range group
        range_group = QGroupBox("Chapter Range")
        range_form = QFormLayout(range_group)

        self._ch_count_label = QLabel("Not scraped yet")
        range_form.addRow("Available chapters:", self._ch_count_label)

        start_row = QHBoxLayout()
        self._start_ch_spin = QSpinBox()
        self._start_ch_spin.setRange(1, 9999)
        self._start_ch_spin.setValue(1)
        self._start_ch_spin.setToolTip("First chapter to process (1 = start from beginning)")
        start_row.addWidget(self._start_ch_spin)
        start_row.addStretch()
        range_form.addRow("Start chapter:", start_row)

        end_row = QHBoxLayout()
        self._end_ch_spin = QSpinBox()
        self._end_ch_spin.setRange(0, 9999)
        self._end_ch_spin.setValue(0)
        self._end_ch_spin.setToolTip("Last chapter to process (0 = process all chapters)")
        end_row.addWidget(self._end_ch_spin)
        end_row.addStretch()
        range_form.addRow("End chapter (0=all):", end_row)

        right_vbox.addWidget(range_group)

        # Pipeline controls group
        pipe_group = QGroupBox("Pipeline Controls")
        pipe_vbox = QVBoxLayout(pipe_group)

        phase1_note = QLabel(
            "<b>Phase 1–4:</b> Scrape chapters, run Pass-1 extraction, and "
            "classify dialogue with the LLM.  When complete, review characters "
            "in the <i>Characters</i> tab and segments in the <i>Review</i> tab."
        )
        phase1_note.setWordWrap(True)
        pipe_vbox.addWidget(phase1_note)

        run_row = QHBoxLayout()
        self._run_btn = QPushButton("▶  Run to Character Review  (Phases 1–4)")
        self._run_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._run_btn.clicked.connect(self._on_run_to_review)
        run_row.addWidget(self._run_btn)
        pipe_vbox.addLayout(run_row)

        phase5_note = QLabel(
            "<b>Phase 5–7:</b> Rebuild chapters using reviewed characters, "
            "generate TTS audio, and package the EPUB.  Run after approving "
            "character assignments in the Review tab."
        )
        phase5_note.setWordWrap(True)
        pipe_vbox.addWidget(phase5_note)

        cont_row = QHBoxLayout()
        self._continue_btn = QPushButton("▶  Continue: Audio + Export  (Phases 5–7)")
        self._continue_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._continue_btn.clicked.connect(self._on_continue_audio)
        cont_row.addWidget(self._continue_btn)
        pipe_vbox.addLayout(cont_row)

        stop_row = QHBoxLayout()
        self._stop_btn = QPushButton("⛔  Stop Pipeline")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("padding:6px 14px; color:#f38ba8;")
        self._stop_btn.clicked.connect(self._on_stop_pipeline)
        stop_row.addWidget(self._stop_btn)
        stop_row.addStretch()
        pipe_vbox.addLayout(stop_row)

        right_vbox.addWidget(pipe_group)

        # Status / progress label
        self._status_label = QLabel("No project loaded.")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: steelblue;")
        right_vbox.addWidget(self._status_label)

        right_vbox.addStretch()

        splitter.setSizes([260, 700])

        # Wire project-manager signals
        if self.project_manager:
            self.project_manager.project_loaded.connect(self._on_project_loaded)
            self.project_manager.chapters_updated.connect(self._refresh_chapter_counts)

        # Disable controls until a project is loaded
        self._set_project_controls_enabled(False)

    # ------------------------------------------------------------------
    # Project management helpers
    # ------------------------------------------------------------------

    def _set_project_controls_enabled(self, enabled: bool) -> None:
        for w in (
            self._index_url_edit, self._save_url_btn, self._index_chapters_btn,
            self._start_ch_spin, self._end_ch_spin,
            self._run_btn, self._continue_btn,
        ):
            w.setEnabled(enabled)

    def _on_project_opened(self, book_id: str) -> None:
        """Called when BookManagerWidget opens a project."""
        self._load_active_project_state()

    def _on_project_loaded(self, book_id: str) -> None:
        """Called when project_manager emits project_loaded."""
        self._load_active_project_state()

    def _load_active_project_state(self) -> None:
        """Populate all form fields from the currently active project."""
        if not self.project_manager or not self.project_manager.current_book_id:
            self._set_project_controls_enabled(False)
            self._status_label.setText("No project loaded.")
            self._proj_title_label.setText("—")
            self._proj_author_label.setText("—")
            self._index_url_edit.clear()
            return

        info = self.project_manager.get_project_info() or {}
        self._proj_title_label.setText(info.get("title", "—") or "—")
        self._proj_author_label.setText(info.get("author", "—") or "—")
        self._index_url_edit.setText(info.get("index_url", "") or "")

        sel = self.project_manager.get_selected_range()
        self._start_ch_spin.setValue(max(1, int(sel.get("start", 1))))
        self._end_ch_spin.setValue(max(0, int(sel.get("end", 0))))

        self._set_project_controls_enabled(True)
        self._refresh_chapter_counts()

    def _refresh_chapter_counts(self) -> None:
        if not self.project_manager or not self.project_manager.current_book_id:
            return
        inv = self.project_manager.get_inventory()
        raw = inv.get("raw_chapter_count", 0)
        valid = inv.get("valid_chapter_count", 0)
        last = inv.get("last_processed_chapter", 0)
        if raw > 0:
            self._ch_count_label.setText(
                f"{valid} valid (of {raw} found); last processed: {last}"
            )
        else:
            self._ch_count_label.setText("Not scraped yet")
        title = self._proj_title_label.text()
        self._status_label.setText(
            f"Project: <b>{title}</b> — {valid} chapters available"
        )

    def _on_save_index_url(self) -> None:
        if not self.project_manager or not self.project_manager.current_book_id:
            return
        url = self._index_url_edit.text().strip()
        self.project_manager.set_index_url(url)
        self.settings.set("index_url", url)
        self.log.log(f"Index URL saved: {url}", level="SUCCESS")

    # ------------------------------------------------------------------
    # Pipeline run helpers
    # ------------------------------------------------------------------

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._index_chapters_btn.setEnabled(enabled)
        self._run_btn.setEnabled(enabled)
        self._continue_btn.setEnabled(enabled)
        self._stop_btn.setEnabled(not enabled)

    def _is_busy(self) -> bool:
        if self._worker is None:
            return False
        try:
            return bool(self._worker.isRunning())
        except RuntimeError:
            self._worker = None
            return False

    def _on_run_to_review(self) -> None:
        if self._is_busy():
            QMessageBox.warning(self, "Busy", "A pipeline task is already running.")
            return
        if not self.project_manager or not self.project_manager.current_book_id:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return
        # Auto-save current URL + range before starting
        self._on_save_index_url()
        start_ch = self._start_ch_spin.value()
        end_ch = self._end_ch_spin.value()
        self.project_manager.set_selected_range(start_ch, end_ch)

        self._set_buttons_enabled(False)
        self._status_label.setText("⏳ Running phases 1–4 (scrape + LLM classification)…")
        self._worker = _PipelineWorker(
            project_manager=self.project_manager,
            settings=self.settings,
            mode=_PipelineWorker.RUN_TO_REVIEW,
            start_ch=start_ch,
            end_ch=end_ch,
        )
        self._worker.inventory_ready.connect(self._on_inventory_ready)
        self._worker.finished_ok.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.cancelled.connect(self._on_worker_cancelled)
        self._worker.log_message.connect(lambda msg, lvl: self.log.log(msg, level=lvl))
        self._worker.start()
        self.log.log("Pipeline started: Run to Character Review.", level="INFO")

    def _on_continue_audio(self) -> None:
        if self._is_busy():
            QMessageBox.warning(self, "Busy", "A pipeline task is already running.")
            return
        if not self.project_manager or not self.project_manager.current_book_id:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return
        start_ch = self._start_ch_spin.value()
        end_ch = self._end_ch_spin.value()
        self.project_manager.set_selected_range(start_ch, end_ch)

        self._set_buttons_enabled(False)
        self._status_label.setText("⏳ Running phases 5–7 (audio generation + EPUB export)…")
        self._worker = _PipelineWorker(
            project_manager=self.project_manager,
            settings=self.settings,
            mode=_PipelineWorker.CONTINUE_AUDIO,
            start_ch=start_ch,
            end_ch=end_ch,
        )
        self._worker.finished_ok.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.cancelled.connect(self._on_worker_cancelled)
        self._worker.log_message.connect(lambda msg, lvl: self.log.log(msg, level=lvl))
        self._worker.start()
        self.log.log("Pipeline started: Continue Audio + Export.", level="INFO")

    def _on_index_chapters(self) -> None:
        if self._is_busy():
            QMessageBox.warning(self, "Busy", "A pipeline task is already running.")
            return
        if not self.project_manager or not self.project_manager.current_book_id:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return

        self._on_save_index_url()
        self._set_buttons_enabled(False)
        self._status_label.setText("⏳ Scraping chapter index…")
        self._worker = _PipelineWorker(
            project_manager=self.project_manager,
            settings=self.settings,
            mode=_PipelineWorker.CHECK_INDEX,
        )
        self._worker.inventory_ready.connect(self._on_inventory_ready)
        self._worker.finished_ok.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.cancelled.connect(self._on_worker_cancelled)
        self._worker.log_message.connect(lambda msg, lvl: self.log.log(msg, level=lvl))
        self._worker.start()
        self.log.log("Pipeline started: Index Chapters.", level="INFO")

    def _on_stop_pipeline(self) -> None:
        if not self._is_busy():
            return
        self._worker.request_stop()
        self._stop_btn.setEnabled(False)
        self.log.log("Stop requested. Current phase will halt shortly.", level="WARNING")

    def _on_inventory_ready(self, data: dict) -> None:
        raw = data.get("raw_count", 0)
        valid = data.get("valid_count", 0)
        self._ch_count_label.setText(f"{valid} valid (of {raw} found)")
        self.project_manager.set_inventory(
            raw_chapter_count=raw,
            valid_chapter_count=valid,
            chapter_urls=data.get("chapter_urls"),
        )
        self._status_label.setText(
            f"⏳ Index scraped — {valid} chapters found. Processing…"
        )

    def _on_worker_finished(self, mode: str, message: str) -> None:
        worker = self._worker
        self._worker = None
        # Index-only runs do not process chapter content, so they should not
        # overwrite last_processed_chapter progress.
        if self.project_manager and worker is not None and mode != _PipelineWorker.CHECK_INDEX:
            self.project_manager.set_last_processed_chapter(getattr(worker, '_end', 0))
        self._set_buttons_enabled(True)
        self._load_active_project_state()
        self.log.log(message, level="SUCCESS")
        status_label = getattr(self, '_status_label', None)
        if status_label is not None:
            status_label.setStyleSheet("color: #a6e3a1;")
            status_label.setText(f"✅ {message}")
        if mode == _PipelineWorker.RUN_TO_REVIEW:
            QMessageBox.information(
                self,
                "Character Review Required",
                "Chapter parsing is complete. Review scraped text and detected "
                "characters in the Review tab, then click 'Continue Audio + Export'.",
            )

    def _on_worker_failed(self, error: str) -> None:
        self._worker = None
        self._set_buttons_enabled(True)
        status_label = getattr(self, '_status_label', None)
        if status_label is not None:
            status_label.setStyleSheet("color: #f38ba8;")
            status_label.setText(f"❌ Pipeline error: {error}")
        self.log.log(f"Pipeline failed: {error}", level="ERROR")
        QMessageBox.critical(self, "Pipeline Error", f"Pipeline failed:\n\n{error}")

    def _on_worker_cancelled(self, message: str) -> None:
        self._worker = None
        self._set_buttons_enabled(True)
        status_label = getattr(self, '_status_label', None)
        if status_label is not None:
            status_label.setStyleSheet("color: #f9e2af;")
            status_label.setText(f"⚠ {message}")
        self.log.log(message, level="WARNING")

    # ------------------------------------------------------------------
    # Review page helpers (segment editing + character DB)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_segment_type(seg_type: str) -> str:
        return seg_type if seg_type in {"dialogue", "narration", "thought"} else "narration"

    @staticmethod
    def _normalize_gender(gender: str) -> str:
        return gender if gender in {"male", "female", "unknown"} else "unknown"

    def _collect_review_segments_from_table(self) -> list:
        """Build an updated segment list from the current review table widget."""
        segments = list(self._current_review_segments)
        for row in range(self._segment_table.rowCount()):
            if row >= len(self._current_review_row_segment_indexes):
                continue
            seg_idx = self._current_review_row_segment_indexes[row]
            if seg_idx >= len(segments):
                continue
            speaker_widget = self._segment_table.cellWidget(row, 1)
            type_widget = self._segment_table.cellWidget(row, 2)
            speaker = speaker_widget.currentText() if speaker_widget else segments[seg_idx].get("speaker", "")
            seg_type = type_widget.currentText() if type_widget else segments[seg_idx].get("type", "narration")
            segments[seg_idx] = dict(segments[seg_idx])
            segments[seg_idx]["speaker"] = speaker
            segments[seg_idx]["type"] = self._normalize_segment_type(seg_type)
        return segments

    def _refresh_final_review_view(self, chapter_id: str) -> None:
        """Refresh the final review view panel for the given chapter.

        This is a no-op in the base implementation; the full pipeline UI
        overrides this to repopulate the review tab after segment edits.
        """
        views = getattr(self, '_review_stage_views', {})
        view = views.get(chapter_id)
        if view is not None and hasattr(self, '_segments_to_html'):
            pass  # actual refresh delegated to full UI subclass

    def _character_db_path(self) -> Path:
        return Path(self.project_manager.get_work_dir()) / "character_database.json"

    def _load_character_database_entries(self) -> list:
        path = self._character_db_path()
        if path.exists():
            try:
                import json as _json
                return _json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _on_save_segment_speakers(self) -> None:
        """Persist review table edits back to all chapter LLM/final JSON files."""
        import json as _json
        chapter_id = self._current_review_chapter_id
        work_dir = Path(self.project_manager.get_work_dir())

        updated_segments = self._collect_review_segments_from_table()

        for filename in (
            f"{chapter_id}_llm_raw.json",
            f"{chapter_id}_llm_normalized.json",
            f"{chapter_id}_chapter_info_final.json",
        ):
            path = work_dir / filename
            if path.exists():
                try:
                    data = _json.loads(path.read_text(encoding="utf-8"))
                    data["segments"] = updated_segments
                    path.write_text(
                        _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                except Exception:
                    pass

        self._refresh_final_review_view(chapter_id)
        self.log.log("Saved segment review edits for chapter review.", level="SUCCESS")

    def _on_save_detected_characters(self) -> None:
        """Persist the character table back to the character database JSON and settings."""
        import json as _json
        table = self._detected_char_table
        rows = table.rowCount()
        existing = {e["name"]: e for e in self._load_character_database_entries()}
        clamped_count = 0
        updated = []
        for row in range(rows):
            name_item = table.item(row, 0)
            name = name_item.text() if name_item else ""
            if not name:
                continue
            gender_widget = table.cellWidget(row, 1)
            voice_widget = table.cellWidget(row, 2)
            conf_item = table.item(row, 3)
            gender = self._normalize_gender(gender_widget.currentText() if gender_widget else "")
            voice = voice_widget.currentText() if voice_widget else ""
            try:
                conf = float(conf_item.text()) if conf_item else 0.0
            except (ValueError, AttributeError):
                conf = 0.0
            if conf < 0.0 or conf > 1.0:
                conf = max(0.0, min(1.0, conf))
                clamped_count += 1
            if name in existing:
                entry = dict(existing[name])
                entry["gender"] = gender
                entry["voice"] = voice or entry.get("voice", "")
            else:
                entry = {
                    "name": name,
                    "gender": gender,
                    "voice": voice or self._default_voice_for_gender(gender),
                    "description": "",
                }
            updated.append(entry)

        db_path = self._character_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_text(_json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        self.settings.set("character_db", updated)
        self.settings.set("pending_character_additions", [])
        self.settings.save()
        self._refresh_segment_speaker_options()
        if clamped_count > 0:
            self.log.log(
                f"Saved character edits ({clamped_count} confidence values clamped to 0..1).",
                level="WARNING",
            )
        else:
            self.log.log("Saved character edits.", level="SUCCESS")

    def _on_recheck_dialogue(self) -> None:
        """Re-run Pass-2 classification and smart review for the active chapter."""
        if not self._require_project():
            return
        self.log.log("Rechecking dialogue classification…", level="INFO")
        ctrl = self.project_manager.create_pipeline_controller()
        ctrl.pass2_classification()
        ctrl.smart_review_dialogue()
        self.log.log("Dialogue recheck complete.", level="SUCCESS")

    def _refresh_segment_speaker_options(self) -> None:
        """Refresh speaker combo-box options in the segment review table.

        This is a no-op placeholder; the full pipeline UI overrides this to
        repopulate combo boxes when the character database changes.
        """
