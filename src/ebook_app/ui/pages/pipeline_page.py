# src/ebook_app/ui/pages/pipeline_page.py
"""Pipeline page — run project-aware chapter processing and audio generation."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ebook_app.ui.pages._base_page import BasePage


_STEPS = [
    ("scrape_index", "1. Scrape index"),
    ("scrape_chapters", "2. Scrape chapters"),
    ("translate_chapters", "3. Translate"),
    ("parse_dialogue", "4. Parse dialogue"),
    ("multispeaker_tts", "5. Multi-speaker TTS"),
    ("batch_tts", "6. Batch TTS"),
    ("forced_alignment", "7. Forced alignment"),
    ("smil_generation", "8. Build SMIL"),
    ("epub_export", "9. Export EPUB3"),
]


class _PipelineWorker(QThread):
    """Background worker that runs heavy pipeline steps off the main GUI thread.

    Emitting signals is thread-safe in Qt; the connected slots execute on the
    main thread so UI updates and project-manager writes happen there.
    """

    step_progress = Signal(str, int)   # step_key, 0-100
    log_message = Signal(str, str)     # message, level
    inventory_ready = Signal(dict)     # {raw_count, valid_count, chapter_urls}
    finished_ok = Signal(str, str)     # mode, human-readable result message
    failed = Signal(str)               # error message

    # Modes
    CHECK_INDEX = "check_index"
    RUN_TO_REVIEW = "run_to_review"
    CONTINUE_AUDIO = "continue_audio"

    def __init__(self, project_manager, settings, mode: str,
                 start_ch: int = 1, end_ch: int = 1) -> None:
        super().__init__()
        self._pm = project_manager
        self._settings = settings
        self._mode = mode
        self._start = start_ch
        self._end = end_ch

    def run(self) -> None:
        try:
            ctrl = self._pm.create_pipeline_controller(
                on_progress=lambda k, v: self.step_progress.emit(k, v)
            )
            if ctrl is None:
                self.failed.emit("No project loaded.")
                return

            if self._mode == self.CHECK_INDEX:
                self._run_check_index(ctrl)
            elif self._mode == self.RUN_TO_REVIEW:
                self._run_to_review(ctrl)
            elif self._mode == self.CONTINUE_AUDIO:
                self._run_continue_audio(ctrl)
            else:
                self.failed.emit(f"Unknown pipeline mode: {self._mode!r}")
        except Exception as exc:
            self.failed.emit(str(exc))

    # ------------------------------------------------------------------
    # Mode implementations
    # ------------------------------------------------------------------

    def _run_check_index(self, ctrl) -> None:
        self.log_message.emit("Checking index…", "INFO")
        ctrl.scrape_index()
        inventory = ctrl.get_chapter_inventory()
        self.inventory_ready.emit({
            "raw_count": inventory["raw_count"],
            "valid_count": inventory["valid_count"],
            "chapter_urls": ctrl.chapter_urls,
        })
        self.finished_ok.emit(
            self.CHECK_INDEX,
            f"Index: raw={inventory['raw_count']}, valid={inventory['valid_count']}.",
        )

    def _run_to_review(self, ctrl) -> None:
        ctrl.set_chapter_range(self._start, self._end)

        self.log_message.emit("Scraping index…", "INFO")
        ctrl.scrape_index()
        inventory = ctrl.get_chapter_inventory()
        self.inventory_ready.emit({
            "raw_count": inventory["raw_count"],
            "valid_count": inventory["valid_count"],
            "chapter_urls": ctrl.chapter_urls,
        })

        if self._end > inventory["valid_count"]:
            self.failed.emit(
                "Requested end chapter exceeds currently available valid chapters."
            )
            return

        self.log_message.emit("Scraping chapters…", "INFO")
        ctrl.scrape_chapters()
        self.log_message.emit("Translating chapters…", "INFO")
        ctrl.translate_chapters()
        self.log_message.emit("Parsing dialogue…", "INFO")
        ctrl.parse_dialogue()

        self.finished_ok.emit(
            self.RUN_TO_REVIEW,
            "Chapter processing completed. Review character suggestions in Settings before audio.",
        )

    def _run_continue_audio(self, ctrl) -> None:
        ctrl.set_chapter_range(self._start, self._end)
        multispeaker = bool(self._settings.get("multispeaker_enabled", False))

        if multispeaker:
            self.log_message.emit("Running multi-speaker TTS…", "INFO")
            ctrl.multispeaker_tts()
        else:
            self.log_message.emit("Running batch TTS…", "INFO")
            ctrl.batch_tts()

        self.log_message.emit("Running forced alignment…", "INFO")
        ctrl.forced_alignment()
        self.log_message.emit("Building SMIL…", "INFO")
        ctrl.smil_generation()
        self.log_message.emit("Exporting EPUB3…", "INFO")
        ctrl.epub_export()

        self.finished_ok.emit(
            self.CONTINUE_AUDIO,
            "Audio generation and export complete.",
        )


class PipelinePage(BasePage):
    """Page for running the end-to-end processing pipeline by project."""

    def __init__(self, **kwargs) -> None:
        self._projects: list[dict[str, Any]] = []
        self._current_book_id: str | None = None
        self._worker: _PipelineWorker | None = None
        self._review_chapters: list[dict[str, Any]] = []
        super().__init__(**kwargs)
        self._reload_projects()

    def _build_ui(self) -> None:
        self._tabs = QTabWidget()
        self._layout.addWidget(self._tabs)
        pipeline_tab = QWidget()
        pipeline_layout = QVBoxLayout(pipeline_tab)

        project_group = QGroupBox("Book Library")
        project_layout = QVBoxLayout(project_group)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Active book:"))
        self._project_combo = QComboBox()
        select_row.addWidget(self._project_combo)
        self._load_project_btn = QPushButton("Load")
        self._load_project_btn.clicked.connect(self._on_load_project)
        select_row.addWidget(self._load_project_btn)
        self._refresh_projects_btn = QPushButton("Refresh")
        self._refresh_projects_btn.clicked.connect(self._reload_projects)
        select_row.addWidget(self._refresh_projects_btn)
        project_layout.addLayout(select_row)

        create_form = QFormLayout()
        self._new_title_input = QLineEdit()
        self._new_author_input = QLineEdit()
        self._index_url_input = QLineEdit()
        self._create_project_btn = QPushButton("Create Book Project")
        self._create_project_btn.clicked.connect(self._on_create_project)
        create_form.addRow("Title:", self._new_title_input)
        create_form.addRow("Author:", self._new_author_input)
        create_form.addRow("Index URL:", self._index_url_input)
        create_form.addRow("", self._create_project_btn)
        project_layout.addLayout(create_form)
        pipeline_layout.addWidget(project_group)

        inventory_group = QGroupBox("Index Inventory & Range")
        inventory_layout = QFormLayout(inventory_group)
        self._raw_count_label = QLabel("0")
        self._valid_count_label = QLabel("0")
        self._last_processed_label = QLabel("0")
        self._last_checked_label = QLabel("-")
        inventory_layout.addRow("Raw chapter URLs:", self._raw_count_label)
        inventory_layout.addRow("Valid chapters:", self._valid_count_label)
        inventory_layout.addRow("Last processed chapter:", self._last_processed_label)
        inventory_layout.addRow("Last checked:", self._last_checked_label)

        self._start_spin = QSpinBox()
        self._start_spin.setRange(1, 100000)
        self._start_spin.setValue(1)
        self._end_spin = QSpinBox()
        self._end_spin.setRange(1, 100000)
        self._end_spin.setValue(1)
        inventory_layout.addRow("Start chapter:", self._start_spin)
        inventory_layout.addRow("End chapter:", self._end_spin)

        self._browser_gui_check = QCheckBox("Use visible browser (non-headless)")
        self._browser_gui_check.setChecked(bool(self.settings.get("scraper_use_browser_gui", False)))
        inventory_layout.addRow("Browser mode:", self._browser_gui_check)

        self._scraper_method_combo = QComboBox()
        self._scraper_method_combo.addItem("Browser (JS/login pages)", "browser")
        self._scraper_method_combo.addItem("HTTP (fast, no JS)", "http")
        scraper_method = str(self.settings.get("scraper_method", "browser")).strip().lower()
        method_index = self._scraper_method_combo.findData(scraper_method)
        self._scraper_method_combo.setCurrentIndex(method_index if method_index >= 0 else 0)
        self._scraper_method_combo.currentIndexChanged.connect(self._on_scraper_method_changed)
        inventory_layout.addRow("Scraper method:", self._scraper_method_combo)

        self._manual_nav_check = QCheckBox("Allow manual navigation for protection/popups")
        self._manual_nav_check.setChecked(bool(self.settings.get("scraper_manual_navigation", False)))
        inventory_layout.addRow("Manual navigation:", self._manual_nav_check)

        self._max_index_pages_spin = QSpinBox()
        self._max_index_pages_spin.setRange(1, 1000)
        self._max_index_pages_spin.setValue(int(self.settings.get("scraper_max_index_pages", 50)))
        inventory_layout.addRow("Max index pages:", self._max_index_pages_spin)

        self._audio_mode_combo = QComboBox()
        self._audio_mode_combo.addItems(["per_chapter", "single_file"])
        current_mode = self.settings.get("audio_output_mode", "per_chapter")
        self._audio_mode_combo.setCurrentText(
            current_mode if current_mode in {"per_chapter", "single_file"} else "per_chapter"
        )
        inventory_layout.addRow("Audio output mode:", self._audio_mode_combo)

        action_row = QHBoxLayout()
        self._check_index_btn = QPushButton("Check Index")
        self._check_index_btn.clicked.connect(self._on_check_index)
        self._run_selected_btn = QPushButton("Run to Character Review")
        self._run_selected_btn.clicked.connect(self._on_run_to_review)
        self._continue_audio_btn = QPushButton("Continue Audio + Export")
        self._continue_audio_btn.clicked.connect(self._on_continue_audio)
        action_row.addWidget(self._check_index_btn)
        action_row.addWidget(self._run_selected_btn)
        action_row.addWidget(self._continue_audio_btn)
        inventory_layout.addRow("", action_row)
        pipeline_layout.addWidget(inventory_group)

        steps_group = QGroupBox("Pipeline Steps")
        steps_layout = QVBoxLayout(steps_group)
        self._step_bars: dict[str, QProgressBar] = {}
        for key, label in _STEPS:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            self._step_bars[key] = bar
            row.addWidget(bar)
            steps_layout.addLayout(row)
        pipeline_layout.addWidget(steps_group)
        pipeline_layout.addStretch()
        self._on_scraper_method_changed()

        review_tab = QWidget()
        self._build_review_tab(review_tab)

        self._tabs.addTab(pipeline_tab, "Pipeline")
        self._tabs.addTab(review_tab, "Review")

    def _build_review_tab(self, tab: QWidget) -> None:
        outer = QVBoxLayout(tab)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Chapter:"))
        self._review_chapter_combo = QComboBox()
        self._review_chapter_combo.currentIndexChanged.connect(self._on_review_chapter_changed)
        controls.addWidget(self._review_chapter_combo, 1)
        self._review_refresh_btn = QPushButton("Refresh")
        self._review_refresh_btn.clicked.connect(self._refresh_review_data)
        controls.addWidget(self._review_refresh_btn)
        outer.addLayout(controls)

        splitter = QSplitter()

        chapter_group = QGroupBox("Scraped Chapter Content")
        chapter_layout = QVBoxLayout(chapter_group)
        self._review_text_view = QTextEdit()
        self._review_text_view.setReadOnly(True)
        chapter_layout.addWidget(self._review_text_view)
        splitter.addWidget(chapter_group)

        detected_group = QGroupBox("Detected Characters")
        detected_layout = QVBoxLayout(detected_group)
        self._detected_char_table = QTableWidget(0, 4)
        self._detected_char_table.setHorizontalHeaderLabels(
            ["Name", "Gender", "Confidence", "Source Chapter(s)"]
        )
        self._detected_char_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._detected_char_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._detected_char_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._detected_char_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        detected_layout.addWidget(self._detected_char_table)

        detected_btns = QHBoxLayout()
        self._detected_add_btn = QPushButton("Add Character")
        self._detected_add_btn.clicked.connect(self._on_add_detected_character)
        self._detected_remove_btn = QPushButton("Remove Selected")
        self._detected_remove_btn.clicked.connect(self._on_remove_detected_character)
        self._detected_save_btn = QPushButton("Save Character Edits")
        self._detected_save_btn.clicked.connect(self._on_save_detected_characters)
        detected_btns.addWidget(self._detected_add_btn)
        detected_btns.addWidget(self._detected_remove_btn)
        detected_btns.addWidget(self._detected_save_btn)
        detected_btns.addStretch()
        detected_layout.addLayout(detected_btns)
        splitter.addWidget(detected_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter)

        self._review_text_view.setPlainText("Run 'Run to Character Review' to load scraped chapter content.")

    def _require_project(self) -> bool:
        if not self.project_manager:
            self.log.log("Project manager is not available.", level="ERROR")
            return False
        if not self.project_manager.current_book_id:
            self.log.log("Load or create a book project first.", level="WARNING")
            return False
        return True

    def _reload_projects(self) -> None:
        if not self.project_manager:
            return
        self._projects = self.project_manager.list_all_projects()
        self._project_combo.clear()
        for entry in self._projects:
            label = f"{entry.get('title', '')} ({entry.get('book_id', '')})"
            self._project_combo.addItem(label, entry.get("book_id"))
        if self.project_manager.current_book_id:
            idx = self._project_combo.findData(self.project_manager.current_book_id)
            if idx >= 0:
                self._project_combo.setCurrentIndex(idx)
            self._load_active_project_state()

    def _load_active_project_state(self) -> None:
        if not self.project_manager or not self.project_manager.current_book_id:
            return
        info = self.project_manager.get_project_info() or {}
        inventory = self.project_manager.get_inventory()
        selected_range = self.project_manager.get_selected_range()
        book = self.project_manager.library.get_book(self.project_manager.current_book_id) or {}

        self._current_book_id = self.project_manager.current_book_id
        self._index_url_input.setText(info.get("index_url", ""))
        self._raw_count_label.setText(str(inventory.get("raw_chapter_count", 0)))
        self._valid_count_label.setText(str(inventory.get("valid_chapter_count", 0)))
        self._last_processed_label.setText(str(inventory.get("last_processed_chapter", 0)))
        self._last_checked_label.setText(str(book.get("last_checked") or "-"))
        scraper_method = str(self.settings.get("scraper_method", "browser")).strip().lower()
        method_idx = self._scraper_method_combo.findData(scraper_method)
        self._scraper_method_combo.setCurrentIndex(method_idx if method_idx >= 0 else 0)
        self._on_scraper_method_changed()

        valid_count = max(1, int(inventory.get("valid_chapter_count", 1)))
        self._start_spin.setRange(1, valid_count)
        self._end_spin.setRange(1, valid_count)
        start = max(1, int(selected_range.get("start", 1)))
        end = int(selected_range.get("end", 0)) or valid_count
        start = min(start, valid_count)
        end = min(max(start, end), valid_count)
        self._start_spin.setValue(start)
        self._end_spin.setValue(end)
        self._refresh_review_data()

    def _on_create_project(self) -> None:
        if not self.project_manager:
            return
        title = self._new_title_input.text().strip()
        author = self._new_author_input.text().strip() or "Unknown"
        index_url = self._index_url_input.text().strip()
        if not title or not index_url:
            self.log.log("Title and Index URL are required.", level="WARNING")
            return
        book_id = self.project_manager.create_project(title, author, index_url)
        self.settings.set("index_url", index_url)
        self.log.log(f"Created project '{book_id}'.", level="SUCCESS")
        self._reload_projects()

    def _on_load_project(self) -> None:
        if not self.project_manager:
            return
        book_id = self._project_combo.currentData()
        if not book_id:
            return
        if self.project_manager.load_project(book_id):
            self.log.log(f"Loaded project '{book_id}'.", level="SUCCESS")
            self._load_active_project_state()
        else:
            self.log.log(f"Failed to load project '{book_id}'.", level="ERROR")

    # ------------------------------------------------------------------
    # Worker helpers
    # ------------------------------------------------------------------

    def _is_busy(self) -> bool:
        worker = self._worker
        if worker is None:
            return False
        try:
            return worker.isRunning()
        except RuntimeError:
            self._worker = None
            return False

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._check_index_btn.setEnabled(enabled)
        self._run_selected_btn.setEnabled(enabled)
        self._continue_audio_btn.setEnabled(enabled)

    def _start_worker(self, worker: _PipelineWorker) -> None:
        if self._is_busy():
            self.log.log("A pipeline operation is already running.", level="WARNING")
            return
        self._worker = worker
        worker.step_progress.connect(self._update_step)
        worker.log_message.connect(lambda msg, lvl: self.log.log(msg, level=lvl))
        worker.inventory_ready.connect(self._on_inventory_ready)
        worker.finished_ok.connect(self._on_worker_finished)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(worker.deleteLater)
        self._set_buttons_enabled(False)
        worker.start()

    def _persist_scraper_options(self) -> None:
        method = self._scraper_method_combo.currentData() or "browser"
        self.settings.set("scraper_method", method)
        self.settings.set("scraper_use_browser_gui", self._browser_gui_check.isChecked())
        self.settings.set("scraper_manual_navigation", self._manual_nav_check.isChecked())
        self.settings.set("scraper_max_index_pages", int(self._max_index_pages_spin.value()))

    def _on_scraper_method_changed(self) -> None:
        use_browser = self._scraper_method_combo.currentData() == "browser"
        self._browser_gui_check.setEnabled(use_browser)
        self._manual_nav_check.setEnabled(use_browser)

    def _on_inventory_ready(self, data: dict) -> None:
        if not self.project_manager:
            return
        self.project_manager.set_inventory(
            raw_chapter_count=data["raw_count"],
            valid_chapter_count=data["valid_count"],
            chapter_urls=data.get("chapter_urls"),
        )
        self._load_active_project_state()

    def _on_worker_finished(self, mode: str, message: str) -> None:
        worker = self._worker
        self._worker = None
        self._set_buttons_enabled(True)
        if mode == _PipelineWorker.RUN_TO_REVIEW and self.project_manager:
            end_chapter = worker._end if worker is not None else 0
            self.project_manager.set_last_processed_chapter(end_chapter)
        self._load_active_project_state()
        self.log.log(message, level="SUCCESS")
        if mode == _PipelineWorker.RUN_TO_REVIEW:
            self._refresh_review_data()
            self._tabs.setCurrentIndex(1)
            QMessageBox.information(
                self,
                "Character Review Required",
                "Chapter parsing is complete. Review scraped text and detected "
                "characters in the Review tab, then click 'Continue Audio + Export'.",
            )

    def _on_worker_failed(self, message: str) -> None:
        self._worker = None
        self._set_buttons_enabled(True)
        self._load_active_project_state()
        self.log.log(f"Pipeline failed: {message}", level="ERROR")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_check_index(self) -> None:
        if not self._require_project():
            return
        index_url = self._index_url_input.text().strip()
        if not index_url:
            self.log.log("Index URL is required.", level="WARNING")
            return
        self.settings.set("index_url", index_url)
        self._persist_scraper_options()
        self.project_manager.set_index_url(index_url)
        self.log.log("Checking index in background…", level="INFO")
        self._start_worker(
            _PipelineWorker(
                self.project_manager,
                self.settings,
                _PipelineWorker.CHECK_INDEX,
            )
        )

    def _validate_range(self) -> tuple[int, int] | None:
        valid_count = int(self._valid_count_label.text() or "0")
        if valid_count <= 0:
            self.log.log("Run 'Check Index' first to discover valid chapters.", level="WARNING")
            return None
        start = self._start_spin.value()
        end = self._end_spin.value()
        if start > end:
            self.log.log("Start chapter cannot be greater than end chapter.", level="WARNING")
            return None
        if end > valid_count:
            self.log.log("End chapter exceeds valid chapter count.", level="WARNING")
            return None
        return start, end

    def _on_run_to_review(self) -> None:
        if not self._require_project():
            return
        result = self._validate_range()
        if result is None:
            return
        start, end = result
        self.settings.set("audio_output_mode", self._audio_mode_combo.currentText())
        self.settings.set("character_review_approved", False)
        self._persist_scraper_options()
        self.project_manager.set_selected_range(start, end)
        self.log.log("Starting pipeline (scrape → translate → parse)…", level="INFO")
        self._start_worker(
            _PipelineWorker(
                self.project_manager,
                self.settings,
                _PipelineWorker.RUN_TO_REVIEW,
                start_ch=start,
                end_ch=end,
            )
        )

    def _on_continue_audio(self) -> None:
        if not self._require_project():
            return
        selected = self.project_manager.get_selected_range()
        start = max(1, int(selected.get("start", 1)))
        end = max(start, int(selected.get("end", 0)) or start)
        self.settings.set("audio_output_mode", self._audio_mode_combo.currentText())
        self.settings.set("character_review_approved", True)
        self.log.log("Starting audio generation and export in background…", level="INFO")
        self._start_worker(
            _PipelineWorker(
                self.project_manager,
                self.settings,
                _PipelineWorker.CONTINUE_AUDIO,
                start_ch=start,
                end_ch=end,
            )
        )

    def _update_step(self, key: str, value: int) -> None:
        if key in self._step_bars:
            self._step_bars[key].setValue(value)

    def _refresh_review_data(self) -> None:
        if not self.project_manager or not self.project_manager.current_book_id:
            self._review_chapter_combo.clear()
            self._review_chapters = []
            self._review_text_view.setPlainText("Load or create a book project to review chapter content.")
            self._detected_char_table.setRowCount(0)
            return

        selected_idx = self._review_chapter_combo.currentData()
        chapters = self.project_manager.get_chapters() or []
        self._review_chapters = chapters

        self._review_chapter_combo.blockSignals(True)
        self._review_chapter_combo.clear()
        for i, chapter in enumerate(chapters):
            title = str(chapter.get("title", "")).strip() or f"Chapter {i + 1}"
            self._review_chapter_combo.addItem(f"{i + 1}. {title}", i)
        self._review_chapter_combo.blockSignals(False)

        if self._review_chapter_combo.count() == 0:
            self._review_text_view.setPlainText("No scraped chapters found yet.")
        else:
            index_to_use = 0
            if isinstance(selected_idx, int):
                found_index = self._review_chapter_combo.findData(selected_idx)
                if found_index >= 0:
                    index_to_use = found_index
            self._review_chapter_combo.setCurrentIndex(index_to_use)
            self._on_review_chapter_changed(index_to_use)

        self._load_detected_characters()

    def _on_review_chapter_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._review_chapters):
            self._review_text_view.setPlainText("")
            return
        chapter = self._review_chapters[index] or {}
        content = str(chapter.get("content", "")).strip()
        self._review_text_view.setPlainText(content or "[No content available for this chapter.]")

    def _load_detected_characters(self) -> None:
        aggregated: dict[str, dict[str, Any]] = {}
        if self.project_manager:
            work_dir = self.project_manager.get_work_dir()
            if work_dir:
                chapter_info_file = work_dir / "chapter_info.json"
                if chapter_info_file.exists():
                    try:
                        with open(chapter_info_file, encoding="utf-8") as f:
                            chapter_info = json.load(f)
                        if isinstance(chapter_info, dict):
                            for chapter_data in chapter_info.values():
                                if not isinstance(chapter_data, dict):
                                    continue
                                source = str(
                                    chapter_data.get("title")
                                    or chapter_data.get("chapter_id")
                                    or ""
                                ).strip()
                                for char in chapter_data.get("detected_characters", []) or []:
                                    if not isinstance(char, dict):
                                        continue
                                    name = str(char.get("name", "")).strip()
                                    if not name:
                                        continue
                                    key = name.lower()
                                    confidence = float(char.get("confidence", 0.0))
                                    existing = aggregated.get(key)
                                    if existing is None:
                                        aggregated[key] = {
                                            "name": name,
                                            "gender": str(char.get("gender", "unknown")).strip() or "unknown",
                                            "confidence": confidence,
                                            "sources": {source} if source else set(),
                                        }
                                    else:
                                        if confidence > existing["confidence"]:
                                            existing["confidence"] = confidence
                                            existing["gender"] = (
                                                str(char.get("gender", "unknown")).strip() or "unknown"
                                            )
                                        if source:
                                            existing["sources"].add(source)
                    except Exception as exc:
                        self.log.log(f"Failed loading detected characters: {exc}", level="WARNING")

        if not aggregated:
            for item in self.settings.get("pending_character_additions", []) or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                key = name.lower()
                source = str(item.get("source_chapter", "")).strip()
                aggregated[key] = {
                    "name": name,
                    "gender": str(item.get("gender", "unknown")).strip() or "unknown",
                    "confidence": float(item.get("confidence", 0.0)),
                    "sources": {source} if source else set(),
                }

        self._detected_char_table.setRowCount(0)
        for item in sorted(aggregated.values(), key=lambda val: str(val["name"]).lower()):
            sources = sorted(item["sources"])
            self._insert_detected_character_row(
                name=str(item["name"]),
                gender=str(item["gender"]),
                confidence=float(item["confidence"]),
                source=", ".join(sources),
            )

    def _insert_detected_character_row(
        self,
        *,
        name: str = "",
        gender: str = "unknown",
        confidence: float = 0.0,
        source: str = "",
    ) -> None:
        row = self._detected_char_table.rowCount()
        self._detected_char_table.insertRow(row)
        self._detected_char_table.setItem(row, 0, QTableWidgetItem(name))
        self._detected_char_table.setItem(row, 1, QTableWidgetItem(gender))
        self._detected_char_table.setItem(row, 2, QTableWidgetItem(f"{confidence:.2f}"))
        self._detected_char_table.setItem(row, 3, QTableWidgetItem(source))

    def _on_add_detected_character(self) -> None:
        self._insert_detected_character_row()

    def _on_remove_detected_character(self) -> None:
        selected = self._detected_char_table.selectedItems()
        if not selected:
            return
        rows = sorted({item.row() for item in selected}, reverse=True)
        for row in rows:
            self._detected_char_table.removeRow(row)

    def _on_save_detected_characters(self) -> None:
        pending = []
        clamped_rows = 0
        for row in range(self._detected_char_table.rowCount()):
            name_item = self._detected_char_table.item(row, 0)
            gender_item = self._detected_char_table.item(row, 1)
            confidence_item = self._detected_char_table.item(row, 2)
            source_item = self._detected_char_table.item(row, 3)

            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            gender = (gender_item.text().strip() if gender_item else "unknown") or "unknown"
            try:
                confidence = float(confidence_item.text()) if confidence_item else 0.0
            except (TypeError, ValueError):
                confidence = 0.0
            clamped = max(0.0, min(1.0, confidence))
            if clamped != confidence:
                clamped_rows += 1
            source = source_item.text().strip() if source_item else ""
            pending.append(
                {
                    "name": name,
                    "gender": gender,
                    "confidence": clamped,
                    "source_chapter": source,
                }
            )
        self.settings.set("pending_character_additions", pending)
        self.settings.save()
        if clamped_rows:
            self.log.log(
                f"Saved review character edits ({clamped_rows} confidence value(s) clamped to 0..1).",
                level="WARNING",
            )
            return
        self.log.log("Saved review character edits.", level="SUCCESS")
