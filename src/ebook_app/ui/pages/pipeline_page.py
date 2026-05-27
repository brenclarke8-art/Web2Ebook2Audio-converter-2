# src/ebook_app/ui/pages/pipeline_page.py
"""Pipeline page — run project-aware chapter processing and audio generation."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
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
        super().__init__(**kwargs)
        self._reload_projects()

    def _build_ui(self) -> None:
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
        self._layout.addWidget(project_group)

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

        self._manual_nav_check = QCheckBox("Allow manual navigation for protection/popups")
        self._manual_nav_check.setChecked(bool(self.settings.get("scraper_manual_navigation", False)))
        inventory_layout.addRow("Manual navigation:", self._manual_nav_check)

        self._manual_nav_timeout_spin = QSpinBox()
        self._manual_nav_timeout_spin.setRange(5, 900)
        self._manual_nav_timeout_spin.setValue(
            int(self.settings.get("scraper_manual_navigation_timeout_sec", 120))
        )
        inventory_layout.addRow("Manual nav window (sec):", self._manual_nav_timeout_spin)

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
        self._layout.addWidget(inventory_group)

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
        self._layout.addWidget(steps_group)
        self._layout.addStretch()

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

        valid_count = max(1, int(inventory.get("valid_chapter_count", 1)))
        self._start_spin.setRange(1, valid_count)
        self._end_spin.setRange(1, valid_count)
        start = max(1, int(selected_range.get("start", 1)))
        end = int(selected_range.get("end", 0)) or valid_count
        start = min(start, valid_count)
        end = min(max(start, end), valid_count)
        self._start_spin.setValue(start)
        self._end_spin.setValue(end)

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
        self.settings.set("scraper_use_browser_gui", self._browser_gui_check.isChecked())
        self.settings.set("scraper_manual_navigation", self._manual_nav_check.isChecked())
        self.settings.set(
            "scraper_manual_navigation_timeout_sec",
            int(self._manual_nav_timeout_spin.value()),
        )
        self.settings.set("scraper_max_index_pages", int(self._max_index_pages_spin.value()))

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
            QMessageBox.information(
                self,
                "Character Review Required",
                "Chapter parsing is complete. Review pending character suggestions "
                "and voices in Settings, then click 'Continue Audio + Export'.",
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
