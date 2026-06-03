# src/ebook_app/ui/pages/pipeline_page.py
"""Pipeline page — run project-aware chapter processing and audio generation."""

from __future__ import annotations

import copy
import hashlib
import html
import json
from functools import partial
from pathlib import Path
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
from ebook_app.models.voice_catalog import KOKORO_VOICE_LIST
from ebook_app.pipeline_contracts import chapter_id as make_chapter_id


# ----------------------------------------------------------------------
# NEW PIPELINE STEPS (UI progress bars)
# ----------------------------------------------------------------------
_STEPS = [
    ("scrape_index", "1. Scrape index"),
    ("scrape_chapters", "2. Scrape chapters"),
    ("clean_chapters", "3. Clean chapters"),
    ("llm_semantic_analysis", "4. LLM semantic analysis"),
    ("normalize_llm_output", "5. Normalize LLM output"),
    ("smart_review_dialogue", "6. Smart review (dialogue + characters)"),
    ("tts_generate", "7. Generate audio"),
    ("epub_build", "8. Build EPUB3"),
]
_SEGMENT_TYPE_OPTIONS = ["narration", "dialogue", "thought"]
_NO_REVIEW_SEGMENTS_MSG = "No semantic segments available for review."


class _PipelineWorker(QThread):
    """
    Background worker that runs the new pipeline phases off the main GUI thread.
    """

    step_progress = Signal(str, int)   # step_key, 0-100
    log_message = Signal(str, str)     # message, level
    inventory_ready = Signal(dict)     # {raw_count, valid_count, chapter_urls}
    finished_ok = Signal(str, str)     # mode, human-readable result message
    failed = Signal(str)               # error message
    cancelled = Signal(str)            # cancellation message

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
        self._ctrl = None
        self._cancel_requested = False

    def request_stop(self) -> None:
        self._cancel_requested = True
        ctrl = self._ctrl
        if ctrl is not None and hasattr(ctrl, "stop"):
            try:
                ctrl.stop()
            except Exception:
                pass

    def _abort_if_cancelled(self) -> bool:
        if not self._cancel_requested:
            return False
        signal = getattr(self, "cancelled", None)
        if signal is not None and hasattr(signal, "emit"):
            signal.emit("Pipeline cancelled by user.")
        return True

    def run(self) -> None:
        try:
            ctrl = self._pm.create_pipeline_controller(
                on_progress=lambda k, v: self.step_progress.emit(k, v)
            )
            if ctrl is None:
                self.failed.emit("No project loaded.")
                return
            self._ctrl = ctrl
            if hasattr(ctrl, "start"):
                ctrl.start()

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
        finally:
            self._ctrl = None

    # --------------------------------------------------------------
    # Mode implementations
    # --------------------------------------------------------------

    def _run_check_index(self, ctrl) -> None:
        if self._abort_if_cancelled():
            return
        self.log_message.emit("Checking index…", "INFO")
        ctrl.scrape_index()
        if self._abort_if_cancelled():
            return
        inventory = ctrl.get_chapter_inventory()
        self.inventory_ready.emit({
            "raw_count": inventory["raw_count"],
            "valid_count": inventory["valid_count"],
            "chapter_urls": ctrl.chapter_urls,
        })
        self.finished_ok.emit(
            self.CHECK_INDEX,
            f"Index: raw={inventory['raw_count']}, valid={inventory['valid_count']}."
        )

    def _hydrate_cached_index(self, ctrl) -> dict | None:
        get_chapter_urls = getattr(self._pm, "get_chapter_urls", None)
        if not callable(get_chapter_urls):
            return None

        cached_urls = list(get_chapter_urls() or [])
        if not cached_urls:
            return None

        ctrl.chapter_urls = cached_urls

        get_inventory = getattr(self._pm, "get_inventory", None)
        inventory = get_inventory() if callable(get_inventory) else {}
        raw_count = int(inventory.get("raw_chapter_count", len(cached_urls)))
        valid_count = len(cached_urls)

        self.log_message.emit(
            f"Using cached index inventory ({valid_count} valid chapters).",
            "INFO",
        )
        self.inventory_ready.emit(
            {
                "raw_count": raw_count,
                "valid_count": valid_count,
                "chapter_urls": cached_urls,
            }
        )
        return {"raw_count": raw_count, "valid_count": valid_count}

    def _run_to_review(self, ctrl) -> None:
        if self._abort_if_cancelled():
            return
        ctrl.set_chapter_range(self._start, self._end)

        # Phase 1–2
        inventory = self._hydrate_cached_index(ctrl)
        if inventory is None:
            self.log_message.emit("Scraping index…", "INFO")
            ctrl.scrape_index()
            if self._abort_if_cancelled():
                return
            inventory = ctrl.get_chapter_inventory()
            self.inventory_ready.emit({
                "raw_count": inventory["raw_count"],
                "valid_count": inventory["valid_count"],
                "chapter_urls": ctrl.chapter_urls,
            })

        if self._end > inventory["valid_count"]:
            self.failed.emit("Requested end chapter exceeds available valid chapters.")
            return

        self.log_message.emit("Scraping chapters…", "INFO")
        ctrl.scrape_chapters()
        if self._abort_if_cancelled():
            return

        # Phase 3
        self.log_message.emit("Cleaning chapters…", "INFO")
        ctrl.clean_chapters()
        if self._abort_if_cancelled():
            return

        # Phase 4–5
        self.log_message.emit("Running LLM semantic analysis…", "INFO")
        ctrl.llm_semantic_analysis()
        if self._abort_if_cancelled():
            return

        self.log_message.emit("Normalizing LLM output…", "INFO")
        ctrl.normalize_llm_output()
        if self._abort_if_cancelled():
            return

        self.log_message.emit("Smart reviewing dialogue…", "INFO")
        ctrl.smart_review_dialogue()
        if self._abort_if_cancelled():
            return

        # Check if any chapters require manual review
        review_plan_path = ctrl.work_dir / "semantic_review_plan.json"
        needs_review = []
        if review_plan_path.exists():
            with open(review_plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
                needs_review = plan.get("needs_review", [])

        if needs_review:
            self.log_message.emit(
                f"Chapters requiring manual review: {needs_review}",
                "WARNING"
            )

        self.finished_ok.emit(
            self.RUN_TO_REVIEW,
            "Processing complete. Review detected characters in the Review tab before audio."
        )

    def _run_continue_audio(self, ctrl) -> None:
        if self._abort_if_cancelled():
            return
        ctrl.set_chapter_range(self._start, self._end)

        self.log_message.emit("Finalizing reviewed chapters...", "INFO")
        ctrl.smart_review_dialogue()
        if self._abort_if_cancelled():
            return

        # Phase 7
        self.log_message.emit("Generating TTS audio…", "INFO")
        ctrl.tts_generate()
        if self._abort_if_cancelled():
            return

        # Phase 8
        self.log_message.emit("Building EPUB3…", "INFO")
        ctrl.epub_build()
        if self._abort_if_cancelled():
            return

        self.finished_ok.emit(
            self.CONTINUE_AUDIO,
            "Audio generation and EPUB export complete."
        )

class PipelinePage(BasePage):
    """Page for running the end-to-end processing pipeline by project."""

    def __init__(self, **kwargs) -> None:
        self._projects: list[dict[str, Any]] = []
        self._current_book_id: str | None = None
        self._worker: _PipelineWorker | None = None
        self._review_chapters: list[dict[str, Any]] = []
        self._review_stage_chapter_combos: list[QComboBox] = []
        self._review_stage_views: dict[str, QTextEdit] = {}
        self._syncing_review_combo = False
        self._current_review_chapter_id: str | None = None
        self._current_review_segments: list[dict[str, Any]] = []
        self._current_review_row_segment_indexes: list[int] = []
        self._current_review_segment_file: Path | None = None
        self._segment_preview_view: QTextEdit | None = None
        super().__init__(**kwargs)
        self._reload_projects()

    def _build_ui(self) -> None:
        self._tabs = QTabWidget()
        self._layout.addWidget(self._tabs)

        # --------------------------------------------------------------
        # PIPELINE TAB
        # --------------------------------------------------------------
        pipeline_tab = QWidget()
        pipeline_layout = QVBoxLayout(pipeline_tab)

        # -------------------------
        # Project selection
        # -------------------------
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

        # Create project form
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

        # -------------------------
        # Inventory + chapter range
        # -------------------------
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

        # Scraper options
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

        # -------------------------
        # Action buttons
        # -------------------------
        action_row = QHBoxLayout()

        self._check_index_btn = QPushButton("Check Index")
        self._check_index_btn.clicked.connect(self._on_check_index)

        self._run_selected_btn = QPushButton("Run to Review (Scrape → Clean → Semantic)")
        self._run_selected_btn.clicked.connect(self._on_run_to_review)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop_pipeline)
        self._stop_btn.setEnabled(False)

        action_row.addWidget(self._check_index_btn)
        action_row.addWidget(self._run_selected_btn)
        action_row.addWidget(self._stop_btn)
        action_row.addStretch()

        inventory_layout.addRow("", action_row)
        pipeline_layout.addWidget(inventory_group)

        # -------------------------
        # Pipeline step progress bars
        # -------------------------
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

        # --------------------------------------------------------------
        # REVIEW TAB
        # --------------------------------------------------------------
        review_tab = QWidget()
        self._build_review_tab(review_tab)

        llm_log_tab = QWidget()
        self._build_llm_log_tab(llm_log_tab)

        self._tabs.addTab(pipeline_tab, "Pipeline")
        self._tabs.addTab(review_tab, "Review")
        self._tabs.addTab(llm_log_tab, "LLM Communication")


    def _build_review_tab(self, tab: QWidget) -> None:
        outer = QVBoxLayout(tab)

        # --------------------------------------------------------------
        # Chapter selector + refresh
        # --------------------------------------------------------------
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Chapter:"))

        self._review_chapter_combo = QComboBox()
        self._review_chapter_combo.currentIndexChanged.connect(self._on_review_chapter_combo_changed)
        controls.addWidget(self._review_chapter_combo, 1)

        self._review_refresh_btn = QPushButton("Refresh")
        self._review_refresh_btn.clicked.connect(self._refresh_review_data)
        controls.addWidget(self._review_refresh_btn)

        outer.addLayout(controls)

        # --------------------------------------------------------------
        # Splitter: Left = cleaned/semantic text, Right = characters
        # --------------------------------------------------------------
        splitter = QSplitter()

        # -------------------------
        # LEFT SIDE: Chapter text
        # -------------------------
        chapter_group = QGroupBox("Chapter Content (cleaned → semantic → final)")
        chapter_layout = QVBoxLayout(chapter_group)

        self._review_stage_views = {}
        self._review_stage_chapter_combos = []
        self._review_stage_tabs = QTabWidget()
        for key, label in [
            ("scraped", "Scraped"),
            ("cleaned_final", "Cleaned Final"),
            ("semantic", "Semantic Segments"),
            ("final_segments", "Final Segments"),
        ]:
            page, chapter_combo, stage_view = self._build_review_stage_page()
            chapter_combo.currentIndexChanged.connect(self._on_review_stage_chapter_changed)
            self._review_stage_chapter_combos.append(chapter_combo)
            self._review_stage_views[key] = stage_view
            self._review_stage_tabs.addTab(page, label)
        chapter_layout.addWidget(self._review_stage_tabs)

        splitter.addWidget(chapter_group)

        # -------------------------
        # RIGHT SIDE: Detected characters
        # -------------------------
        detected_group = QGroupBox("Detected Characters (LLM + DB)")
        detected_layout = QVBoxLayout(detected_group)

        self._detected_char_table = QTableWidget(0, 5)
        self._detected_char_table.setHorizontalHeaderLabels(
            ["Name", "Gender", "Voice", "Confidence", "Source Chapter(s)"]
        )

        # Column sizing
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
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self._detected_char_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )

        detected_layout.addWidget(self._detected_char_table)

        # Buttons for character editing
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

        segments_group = QGroupBox("Semantic Segments (speaker + type review)")
        segments_layout = QVBoxLayout(segments_group)
        self._segment_table = QTableWidget(0, 3)
        self._segment_table.setHorizontalHeaderLabels(["Text", "Speaker", "Type"])
        self._segment_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._segment_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._segment_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        segments_layout.addWidget(self._segment_table)

        segments_layout.addWidget(QLabel("Current Review Preview"))
        self._segment_preview_view = QTextEdit()
        self._segment_preview_view.setReadOnly(True)
        segments_layout.addWidget(self._segment_preview_view)

        segment_btns = QHBoxLayout()
        self._segment_save_btn = QPushButton("Save Segment Review Changes")
        self._segment_save_btn.clicked.connect(self._on_save_segment_speakers)
        segment_btns.addWidget(self._segment_save_btn)

        self._segment_recheck_btn = QPushButton("Dialogue Recheck (LLM + Manual Context)")
        self._segment_recheck_btn.clicked.connect(self._on_recheck_dialogue)
        segment_btns.addWidget(self._segment_recheck_btn)

        self._continue_audio_btn = QPushButton("Confirm Chapter Review + Continue Audio + Export")
        self._continue_audio_btn.clicked.connect(self._on_confirm_review_and_continue)
        segment_btns.addWidget(self._continue_audio_btn)
        segment_btns.addStretch()
        segments_layout.addLayout(segment_btns)
        outer.addWidget(segments_group)

        # Default message
        default_msg = "Run 'Run to Review' to load chapter review content."
        for view in self._review_stage_views.values():
            view.setPlainText(default_msg)
        self._set_segment_preview_text(default_msg)

    def _build_review_stage_page(self) -> tuple[QWidget, QComboBox, QTextEdit]:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Chapter:"))
        chapter_combo = QComboBox()
        controls.addWidget(chapter_combo, 1)
        layout.addLayout(controls)

        text_view = QTextEdit()
        text_view.setReadOnly(True)
        layout.addWidget(text_view)
        return page, chapter_combo, text_view

    def _build_llm_log_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)

        controls = QHBoxLayout()
        self._llm_log_refresh_btn = QPushButton("Refresh")
        self._llm_log_refresh_btn.clicked.connect(self._refresh_llm_log)
        controls.addWidget(self._llm_log_refresh_btn)
        controls.addStretch()
        layout.addLayout(controls)

        self._llm_log_view = QTextEdit()
        self._llm_log_view.setReadOnly(True)
        self._llm_log_view.setFontFamily("Courier")
        layout.addWidget(self._llm_log_view)

    def _refresh_llm_log(self) -> None:
        if not self.project_manager or not self.project_manager.current_book_id:
            self._llm_log_view.setPlainText("No project loaded.")
            return
        work_dir = self.project_manager.get_work_dir()
        if work_dir is None:
            self._llm_log_view.setPlainText("No project work directory available.")
            return
        log_path = work_dir / "llm_communication.jsonl"
        if not log_path.exists():
            self._llm_log_view.setPlainText("No LLM communication log found. Run the pipeline first.")
            return
        try:
            content = log_path.read_text(encoding="utf-8")
        except Exception as exc:
            self._llm_log_view.setPlainText(f"Error reading log: {exc}")
            return
        lines = content.strip().splitlines()
        formatted_parts: list[str] = []
        for line in lines:
            try:
                record = json.loads(line)
                formatted_parts.append(json.dumps(record, indent=2, ensure_ascii=False))
            except Exception:
                formatted_parts.append(line)
        self._llm_log_view.setPlainText("\n\n---\n\n".join(formatted_parts) if formatted_parts else "(empty)")

    def _set_review_stage_chapter_index(self, index: int) -> None:
        self._syncing_review_combo = True
        try:
            for combo in self._review_stage_chapter_combos:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
        finally:
            self._syncing_review_combo = False

    def _on_review_chapter_combo_changed(self, index: int) -> None:
        self._set_review_stage_chapter_index(index)
        self._on_review_chapter_changed(index)

    def _on_review_stage_chapter_changed(self, index: int) -> None:
        if self._syncing_review_combo:
            return
        self._review_chapter_combo.setCurrentIndex(index)

    def _populate_review_chapter_combo(self, combo: QComboBox, chapters: list[dict[str, Any]]) -> None:
        combo.blockSignals(True)
        combo.clear()
        for i, chapter in enumerate(chapters):
            title = str(chapter.get("title", "")).strip() or f"Chapter {i + 1}"
            combo.addItem(f"{i + 1}. {title}", i)
        combo.blockSignals(False)

    def _set_stage_plain_text(self, stage: str, text: str) -> None:
        view = self._review_stage_views.get(stage)
        if view is not None:
            view.setPlainText(text)

    def _set_segment_preview_text(self, text: str) -> None:
        if self._segment_preview_view is not None:
            self._segment_preview_view.setPlainText(text)

    def _set_segment_preview_html(self, value: str) -> None:
        if self._segment_preview_view is not None:
            self._segment_preview_view.setHtml(value)

    def _segments_to_html(self, segments: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            seg_type = str(seg.get("type", "narration")).strip().lower() or "narration"
            speaker = str(seg.get("speaker", "narrator")).strip() or "narrator"
            color = self._speaker_color(speaker)
            text_html = html.escape(text)
            speaker_html = html.escape(speaker.upper())
            if seg_type == "narration":
                lines.append(f"<p style='margin:0 0 8px 0'>{text_html}</p>")
            else:
                lines.append(
                    f"<p style='margin:0 0 8px 0'>"
                    f"<span style='background:{color};padding:1px 6px;border-radius:4px'>[{speaker_html}]</span> "
                    f"{text_html}</p>"
                )
        return "".join(lines)

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
        self._refresh_llm_log()

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
        self._stop_btn.setEnabled(not enabled)

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
        worker.cancelled.connect(self._on_worker_cancelled)
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
            self._refresh_llm_log()
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

    def _on_worker_cancelled(self, message: str) -> None:
        self._worker = None
        self._set_buttons_enabled(True)
        self._load_active_project_state()
        self.log.log(message, level="WARNING")

    def _on_stop_pipeline(self) -> None:
        worker = self._worker
        if worker is None or not self._is_busy():
            self.log.log("No active pipeline operation to stop.", level="WARNING")
            self._stop_btn.setEnabled(False)
            return
        worker.request_stop()
        self.log.log("Stop requested. Current phase will halt shortly.", level="WARNING")
        self._stop_btn.setEnabled(False)
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

        self.settings.set("character_review_approved", False)
        self._persist_scraper_options()
        self.project_manager.set_selected_range(start, end)

        self.log.log("Starting pipeline (scrape → clean → semantic)…", level="INFO")

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

        self.settings.set("character_review_approved", True)

        self.log.log("Starting audio generation and EPUB build…", level="INFO")

        self._start_worker(
            _PipelineWorker(
                self.project_manager,
                self.settings,
                _PipelineWorker.CONTINUE_AUDIO,
                start_ch=start,
                end_ch=end,
            )
        )

    # ------------------------------------------------------------------
    # Progress bar update
    # ------------------------------------------------------------------

    def _update_step(self, key: str, value: int) -> None:
        if key in self._step_bars:
            self._step_bars[key].setValue(value)

    # ------------------------------------------------------------------
    # Review Tab Data Loading
    # ------------------------------------------------------------------

    def _refresh_review_data(self) -> None:
        """
        Loads chapter list + triggers loading of cleaned/semantic text
        and detected characters.
        """
        if not self.project_manager or not self.project_manager.current_book_id:
            self._review_chapter_combo.clear()
            for combo in self._review_stage_chapter_combos:
                combo.clear()
            self._review_chapters = []
            self._set_stage_plain_text("scraped", "Load or create a book project to review chapter content.")
            self._set_stage_plain_text("semantic", "Load or create a book project to review chapter content.")
            self._set_stage_plain_text("cleaned_final", "Load or create a book project to review chapter content.")
            self._set_stage_plain_text("final_segments", "Load or create a book project to review chapter content.")
            self._set_segment_preview_text("Load or create a book project to review semantic segments.")
            self._detected_char_table.setRowCount(0)
            self._segment_table.setRowCount(0)
            return

        selected_chapter_idx = self._review_chapter_combo.currentData()
        chapters = self.project_manager.get_chapters() or []
        self._review_chapters = chapters
        self._load_detected_characters()

        # Populate chapter dropdowns
        self._populate_review_chapter_combo(self._review_chapter_combo, chapters)
        for combo in self._review_stage_chapter_combos:
            self._populate_review_chapter_combo(combo, chapters)

        if not chapters:
            self._set_stage_plain_text("scraped", "No scraped chapters found yet.")
            self._set_stage_plain_text("semantic", "No LLM output found yet.")
            self._set_stage_plain_text("cleaned_final", "No normalized LLM output found yet.")
            self._set_stage_plain_text("final_segments", "No final review found yet.")
            self._set_segment_preview_text("No semantic segments available for review yet.")
        else:
            index_to_use = 0
            if isinstance(selected_chapter_idx, int):
                found = self._review_chapter_combo.findData(selected_chapter_idx)
                if found >= 0:
                    index_to_use = found
            self._review_chapter_combo.blockSignals(True)
            self._review_chapter_combo.setCurrentIndex(index_to_use)
            self._review_chapter_combo.blockSignals(False)
            self._on_review_chapter_combo_changed(index_to_use)

    def _on_review_chapter_changed(self, index: int) -> None:
        """
        Loads scraped/LLM/final review sources for a chapter.
        """
        self._current_review_chapter_id = None
        self._current_review_segment_file = None
        self._current_review_segments = []
        self._current_review_row_segment_indexes = []
        self._segment_table.setRowCount(0)

        if index < 0 or index >= len(self._review_chapters):
            self._set_stage_plain_text("scraped", "")
            self._set_stage_plain_text("cleaned_final", "")
            self._set_stage_plain_text("semantic", "")
            self._set_stage_plain_text("final_segments", "")
            self._set_segment_preview_text("")
            return

        chapter = self._review_chapters[index]
        work_dir = self.project_manager.get_work_dir()
        if work_dir is None:
            self._set_stage_plain_text("scraped", "[No project work directory available.]")
            self._set_stage_plain_text("cleaned_final", "[No project work directory available.]")
            self._set_stage_plain_text("semantic", "[No project work directory available.]")
            self._set_stage_plain_text("final_segments", "[No project work directory available.]")
            self._set_segment_preview_text("[No project work directory available.]")
            return
        chapter_id = self._chapter_id_for_offset(index)
        self._current_review_chapter_id = chapter_id

        # 1. Raw scraped content
        raw_scrape = work_dir / f"{chapter_id}_raw.txt"
        if raw_scrape.exists():
            scraped_content = raw_scrape.read_text(encoding="utf-8").strip()
        else:
            scraped_content = str(chapter.get("content", "")).strip()
        self._set_stage_plain_text("scraped", scraped_content or "[No content available for this chapter.]")

        # 2. LLM output (raw LLM segments)
        segments: list[dict[str, Any]] = []
        chapter_info_file = work_dir / f"{chapter_id}_llm_raw.json"
        if chapter_info_file.exists():
            try:
                ch_data = json.loads(chapter_info_file.read_text(encoding="utf-8"))
                segments = [copy.deepcopy(seg) for seg in ch_data.get("segments", []) if isinstance(seg, dict)]
            except Exception:
                segments = []
        if segments:
            semantic_view = self._review_stage_views.get("semantic")
            if semantic_view is not None:
                semantic_view.setHtml(self._segments_to_html(segments))
        else:
            self._set_stage_plain_text("semantic", "[No LLM output available for this chapter.]")

        # 3. Normalized LLM output
        normalized_segments: list[dict[str, Any]] = []
        normalized_file = work_dir / f"{chapter_id}_llm_normalized.json"
        if normalized_file.exists():
            try:
                normalized_data = json.loads(normalized_file.read_text(encoding="utf-8"))
                normalized_segments = [
                    copy.deepcopy(seg)
                    for seg in normalized_data.get("segments", [])
                    if isinstance(seg, dict)
                ]
            except Exception:
                normalized_segments = []
        normalized_view = self._review_stage_views.get("cleaned_final")
        if normalized_view is not None:
            if normalized_segments:
                normalized_view.setHtml(self._segments_to_html(normalized_segments))
                self._load_review_segments(normalized_file, normalized_segments)
            else:
                normalized_view.setPlainText("[No normalized LLM output available for this chapter.]")
                if segments:
                    self._load_review_segments(chapter_info_file, segments)
                else:
                    self._set_segment_preview_text("[No semantic segments available for review in this chapter.]")

        # 4. final review before TTS
        self._refresh_final_review_view(chapter_id)

    def _load_review_segments(self, chapter_info_file: Path, segments: list[dict[str, Any]]) -> None:
        self._current_review_segment_file = chapter_info_file
        self._current_review_segments = [dict(seg) for seg in segments]
        self._current_review_row_segment_indexes = []
        self._segment_table.setRowCount(0)

        speakers = ["narrator", *self._detected_character_names()]

        for seg_index, seg in enumerate(self._current_review_segments):
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            seg_type = str(seg.get("type", "narration")).strip() or "narration"
            speaker = str(seg.get("speaker", "narrator")).strip() or "narrator"

            row = self._segment_table.rowCount()
            self._segment_table.insertRow(row)
            self._current_review_row_segment_indexes.append(seg_index)

            text_item = QTableWidgetItem(text)
            self._segment_table.setItem(row, 0, text_item)

            speaker_combo = QComboBox()
            speaker_combo.addItems(speakers)
            if speaker not in speakers:
                speaker_combo.addItem(speaker)
            speaker_combo.setCurrentText(speaker)
            speaker_combo.currentTextChanged.connect(self._render_current_segments_preview)
            self._segment_table.setCellWidget(row, 1, speaker_combo)

            type_combo = QComboBox()
            type_combo.addItems(_SEGMENT_TYPE_OPTIONS)
            if seg_type not in _SEGMENT_TYPE_OPTIONS:
                type_combo.addItem(seg_type)
            type_combo.setCurrentText(seg_type)
            type_combo.currentTextChanged.connect(self._render_current_segments_preview)
            self._segment_table.setCellWidget(row, 2, type_combo)

        self._render_current_segments_preview()

    def _detected_character_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for row in range(self._detected_char_table.rowCount()):
            item = self._detected_char_table.item(row, 0)
            if item is None:
                continue
            name = item.text().strip()
            key = name.lower()
            if name and key not in seen:
                names.append(name)
                seen.add(key)
        return names

    def _refresh_segment_speaker_options(self) -> None:
        if self._segment_table.rowCount() <= 0:
            return
        speakers = ["narrator", *self._detected_character_names()]
        for row in range(self._segment_table.rowCount()):
            widget = self._segment_table.cellWidget(row, 1)
            if not isinstance(widget, QComboBox):
                continue
            current = widget.currentText().strip() or "narrator"
            widget.blockSignals(True)
            widget.clear()
            widget.addItems(speakers)
            if current not in speakers:
                widget.addItem(current)
            widget.setCurrentText(current)
            widget.blockSignals(False)
        self._render_current_segments_preview()

    def _speaker_color(self, speaker: str) -> str:
        key = (speaker or "narrator").strip().lower()
        digest = hashlib.md5(key.encode("utf-8")).hexdigest()
        hue = int(digest[:8], 16) % 360
        return f"hsl({hue}, 60%, 78%)"

    def _render_current_segments_preview(self) -> None:
        if self._segment_table.rowCount() <= 0:
            self._set_segment_preview_text(_NO_REVIEW_SEGMENTS_MSG)
            return
        preview_segments = self._collect_review_segments_from_table()
        if preview_segments:
            self._set_segment_preview_html(self._segments_to_html(preview_segments))
        else:
            self._set_segment_preview_text(_NO_REVIEW_SEGMENTS_MSG)

    @staticmethod
    def _normalize_segment_type(value: str) -> str:
        seg_type = (value or "").strip().lower()
        return seg_type if seg_type in _SEGMENT_TYPE_OPTIONS else "narration"

    def _collect_review_segments_from_table(self) -> list[dict[str, Any]]:
        updated_segments = copy.deepcopy(self._current_review_segments)
        for row in range(self._segment_table.rowCount()):
            text_item = self._segment_table.item(row, 0)
            speaker_widget = self._segment_table.cellWidget(row, 1)
            type_widget = self._segment_table.cellWidget(row, 2)
            text = text_item.text().strip() if text_item else ""
            if not text:
                continue
            speaker = (
                speaker_widget.currentText().strip()
                if isinstance(speaker_widget, QComboBox)
                else "narrator"
            ) or "narrator"
            seg_type = (
                self._normalize_segment_type(type_widget.currentText())
                if isinstance(type_widget, QComboBox)
                else "narration"
            )
            if row >= len(self._current_review_row_segment_indexes):
                continue
            seg_index = self._current_review_row_segment_indexes[row]
            if not (0 <= seg_index < len(updated_segments)):
                continue
            updated = updated_segments[seg_index]
            updated["text"] = text
            updated["type"] = seg_type
            updated["speaker"] = speaker
            if "speaker_confidence" in updated:
                updated["speaker_confidence"] = 1.0
        return updated_segments

    def _on_save_segment_speakers(self) -> None:
        chapter_id = self._current_review_chapter_id
        if not chapter_id:
            self.log.log("Select a chapter first.", level="WARNING")
            return
        if self._segment_table.rowCount() <= 0:
            self.log.log("No semantic segments to save for this chapter.", level="WARNING")
            return

        updated_segments = self._collect_review_segments_from_table()
        work_dir = self.project_manager.get_work_dir()
        if work_dir is None:
            self.log.log("Project work directory is not available.", level="ERROR")
            return
        info_path = work_dir / f"{chapter_id}_llm_raw.json"
        if info_path.exists():
            data = json.loads(info_path.read_text(encoding="utf-8"))
            data["segments"] = updated_segments
            info_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        normalized_path = work_dir / f"{chapter_id}_llm_normalized.json"
        if normalized_path.exists():
            data = json.loads(normalized_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["segments"] = updated_segments
            else:
                data = {"chapter_id": chapter_id, "segments": updated_segments}
            normalized_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        root_final_paths = [work_dir / f"{chapter_id}_chapter_info_final.json"]
        for path in root_final_paths:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["segments"] = updated_segments
            else:
                data = updated_segments
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        self._current_review_segments = updated_segments
        self.log.log("Saved segment review edits for chapter review.", level="SUCCESS")
        self._render_current_segments_preview()
        self._refresh_final_review_view(chapter_id)

    def _on_confirm_review_and_continue(self) -> None:
        if self._detected_char_table.rowCount() > 0:
            self._on_save_detected_characters()
        if self._segment_table.rowCount() > 0:
            self._on_save_segment_speakers()
        self._on_continue_audio()

    def _on_recheck_dialogue(self) -> None:
        if not self._require_project():
            return
        chapter_id = self._current_review_chapter_id
        if not chapter_id:
            self.log.log("Select a chapter first.", level="WARNING")
            return
        if self._segment_table.rowCount() <= 0:
            self.log.log("No segment edits available to recheck.", level="WARNING")
            return

        # Persist the latest manual edits first.
        self._on_save_segment_speakers()
        manual_hints = []
        for seg in self._current_review_segments:
            text = str(seg.get("text", "")).strip()
            speaker = str(seg.get("speaker", "")).strip()
            seg_type = str(seg.get("type", "dialogue")).strip().lower()
            if not text or not speaker:
                continue
            manual_hints.append({"text": text, "speaker": speaker, "type": seg_type})

        ctrl = self.project_manager.create_pipeline_controller()
        if ctrl is None:
            self.log.log("Unable to initialize pipeline controller.", level="ERROR")
            return
        selected = self.project_manager.get_selected_range()
        ctrl.set_chapter_range(
            int(selected.get("start", 1) or 1),
            int(selected.get("end", 0) or 0),
        )
        self.log.log("Running dialogue recheck with your manual corrections…", level="INFO")
        result = ctrl.recheck_dialogue_with_manual_context(chapter_id, manual_hints)
        self.log.log(
            f"Dialogue recheck complete for {result['chapter_id']}: "
            f"{result['segment_count']} segments, {result['character_count']} characters.",
            level="SUCCESS",
        )
        current_index = self._review_chapter_combo.currentIndex()
        self._on_review_chapter_changed(current_index)

    # ------------------------------------------------------------------
    # Character Loading (Phase 6)
    # ------------------------------------------------------------------

    def _load_detected_characters(self) -> None:
        """
        Loads characters from:
        - chXXX_llm_normalized.json
        - pending_character_additions
        - character_db
        """
        aggregated: dict[str, dict[str, Any]] = {}
        work_dir = self.project_manager.get_work_dir()

        for char in self._load_character_database_entries():
            name = str(char.get("name", "")).strip()
            if not name:
                continue
            key = name.lower()
            gender = self._normalize_gender(str(char.get("gender", "other")).strip())
            aggregated[key] = {
                "name": name,
                "gender": gender,
                "voice": str(char.get("voice", "")).strip() or self._default_voice_for_gender(gender),
                "confidence": 1.0,
                "sources": set(),
                "description": str(char.get("description", "")).strip(),
            }

        # --------------------------------------------------------------
        # Load normalized characters from each chapter
        # --------------------------------------------------------------
        if work_dir:
            for idx in range(len(self._review_chapters)):
                chapter_id = self._chapter_id_for_offset(idx)
                norm_path = work_dir / f"{chapter_id}_llm_normalized.json"
                if not norm_path.exists():
                    continue

                try:
                    data = json.loads(norm_path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                for char in data.get("characters", []):
                    name = str(char.get("name", "")).strip()
                    if not name:
                        continue

                    key = name.lower()
                    gender = self._normalize_gender(str(char.get("gender", "other")).strip())
                    confidence = float(char.get("confidence", 0.0))

                    existing = aggregated.get(key)
                    if existing is None:
                        aggregated[key] = {
                            "name": name,
                            "gender": gender,
                            "voice": self._default_voice_for_gender(gender),
                            "confidence": confidence,
                            "sources": {chapter_id},
                            "description": "",
                        }
                    else:
                        existing["sources"].add(chapter_id)
                        if confidence > existing["confidence"]:
                            existing["confidence"] = confidence
                        if not existing.get("voice"):
                            existing["voice"] = self._default_voice_for_gender(gender)
                        if existing.get("gender") in {"", "other"}:
                            existing["gender"] = gender

        # --------------------------------------------------------------
        # Add pending characters (legacy fallback)
        # --------------------------------------------------------------
        for item in self.settings.get("pending_character_additions", []) or []:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            key = name.lower()
            gender = self._normalize_gender(str(item.get("gender", "other")).strip())
            voice = str(item.get("voice", "")).strip() or self._default_voice_for_gender(gender)
            confidence = float(item.get("confidence", 0.0))
            source = str(item.get("source_chapter", "")).strip()

            aggregated[key] = {
                "name": name,
                "gender": gender,
                "voice": voice,
                "confidence": confidence,
                "sources": {source} if source else set(),
                "description": "",
            }

        # --------------------------------------------------------------
        # Populate table
        # --------------------------------------------------------------
        self._detected_char_table.setRowCount(0)
        for item in sorted(aggregated.values(), key=lambda v: v["name"].lower()):
            self._insert_detected_character_row(
                name=item["name"],
                gender=item["gender"],
                voice=item["voice"],
                confidence=item["confidence"],
                source=", ".join(sorted(item["sources"])),
            )
        self._refresh_segment_speaker_options()

    def _chapter_id_for_offset(self, offset: int) -> str:
        selected = self.project_manager.get_selected_range() if self.project_manager else {}
        start = max(1, int(selected.get("start", 1)))
        return make_chapter_id(offset, start_index=start)
    # ------------------------------------------------------------------
    # Character table helpers (Phase 6)
    # ------------------------------------------------------------------

    def _insert_detected_character_row(
        self,
        *,
        name: str = "",
        gender: str = "other",
        voice: str = "",
        confidence: float = 0.0,
        source: str = "",
    ) -> None:
        """
        Inserts a row into the detected-character table.
        Voice column uses a dropdown populated from KOKORO_VOICE_LIST.
        """
        row = self._detected_char_table.rowCount()
        self._detected_char_table.insertRow(row)

        # Name
        self._detected_char_table.setItem(row, 0, QTableWidgetItem(name))

        # Gender dropdown
        gender_combo = QComboBox()
        gender_combo.addItems(["male", "other", "female"])
        normalized_gender = self._normalize_gender(gender)
        gender_combo.setCurrentText(normalized_gender)
        self._detected_char_table.setCellWidget(row, 1, gender_combo)

        # Voice dropdown
        voice_combo = QComboBox()
        voice_combo.addItems(KOKORO_VOICE_LIST)

        selected_voice = voice.strip() or self._default_voice_for_gender(normalized_gender)
        if selected_voice in KOKORO_VOICE_LIST:
            voice_combo.setCurrentText(selected_voice)

        self._detected_char_table.setCellWidget(row, 2, voice_combo)

        # Confidence
        conf_item = QTableWidgetItem(f"{float(confidence):.2f}")
        self._detected_char_table.setItem(row, 3, conf_item)

        # Source chapters
        self._detected_char_table.setItem(row, 4, QTableWidgetItem(source))

        gender_combo.currentTextChanged.connect(
            partial(self._on_detected_gender_changed, voice_combo=voice_combo)
        )

    def _default_voice_for_gender(self, gender: str) -> str:
        """
        Returns the default voice for a given gender, using settings:
        - default_male_voice
        - default_female_voice
        - narrator_voice (fallback)
        """
        gender_lc = (gender or "").strip().lower()
        if gender_lc == "male":
            return self.settings.get("default_male_voice", "am_adam")
        if gender_lc == "female":
            return self.settings.get("default_female_voice", "af_bella")
        return self.settings.get("narrator_voice", "af_heart")

    @staticmethod
    def _normalize_gender(gender: str) -> str:
        gender_lc = (gender or "").strip().lower()
        if gender_lc == "male":
            return "male"
        if gender_lc == "female":
            return "female"
        return "other"

    def _on_detected_gender_changed(self, gender: str, voice_combo: QComboBox) -> None:
        if not isinstance(voice_combo, QComboBox):
            return
        preferred = self._default_voice_for_gender(gender)
        if preferred in KOKORO_VOICE_LIST:
            voice_combo.setCurrentText(preferred)

    # ------------------------------------------------------------------
    # Character editing actions
    # ------------------------------------------------------------------

    def _on_add_detected_character(self) -> None:
        """
        Adds a blank row for manual character entry.
        """
        self._insert_detected_character_row()

    def _on_remove_detected_character(self) -> None:
        """
        Removes selected rows from the detected-character table.
        """
        selected = self._detected_char_table.selectedItems()
        if not selected:
            return

        rows = sorted({item.row() for item in selected}, reverse=True)
        for row in rows:
            self._detected_char_table.removeRow(row)

    def _on_save_detected_characters(self) -> None:
        """
        Saves detected characters into the canonical project character database.
        """
        character_db: list[dict[str, Any]] = []
        clamped_rows = 0
        existing_descriptions = {
            str(item.get("name", "")).strip().lower(): str(item.get("description", "")).strip()
            for item in self._load_character_database_entries()
            if str(item.get("name", "")).strip()
        }

        for row in range(self._detected_char_table.rowCount()):
            name_item = self._detected_char_table.item(row, 0)
            gender_widget = self._detected_char_table.cellWidget(row, 1)
            voice_widget = self._detected_char_table.cellWidget(row, 2)
            confidence_item = self._detected_char_table.item(row, 3)
            source_item = self._detected_char_table.item(row, 4)

            name = name_item.text().strip() if name_item else ""
            if not name:
                continue

            if isinstance(gender_widget, QComboBox):
                gender = self._normalize_gender(gender_widget.currentText())
            else:
                gender = "other"

            voice = (
                voice_widget.currentText().strip()
                if isinstance(voice_widget, QComboBox)
                else self._default_voice_for_gender(gender)
            )

            # Confidence clamping
            try:
                confidence = float(confidence_item.text()) if confidence_item else 0.0
            except (TypeError, ValueError):
                confidence = 0.0

            clamped = max(0.0, min(1.0, confidence))
            if confidence != clamped:
                clamped_rows += 1

            source = source_item.text().strip() if source_item else ""

            character_db.append(
                {
                    "name": name,
                    "gender": gender,
                    "voice": voice,
                    "confidence": clamped,
                    "source_chapter": source,
                    "description": existing_descriptions.get(name.lower(), ""),
                }
            )

        canonical_character_db = [
            {
                "name": item["name"],
                "gender": item["gender"],
                "voice": item["voice"],
                "description": item.get("description", ""),
            }
            for item in character_db
        ]

        character_db_path = self._character_db_path()
        if character_db_path is not None:
            character_db_path.parent.mkdir(parents=True, exist_ok=True)
            character_db_path.write_text(
                json.dumps(canonical_character_db, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        self.settings.set("character_db", canonical_character_db)
        self.settings.set("pending_character_additions", [])
        self.settings.save()

        if clamped_rows:
            self.log.log(
                f"Saved character edits ({clamped_rows} confidence values clamped to 0..1).",
                level="WARNING",
            )
        else:
            self.log.log("Saved character edits.", level="SUCCESS")
        self._refresh_segment_speaker_options()

    def _character_db_path(self) -> Path | None:
        if not self.project_manager:
            return None
        work_dir = self.project_manager.get_work_dir()
        if work_dir is None:
            return None
        return work_dir / "character_database.json"

    def _load_character_database_entries(self) -> list[dict[str, Any]]:
        path = self._character_db_path()
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = []
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        data = self.settings.get("character_db", []) or []
        return [item for item in data if isinstance(item, dict)]

    def _refresh_final_review_view(self, chapter_id: str) -> None:
        final_view = self._review_stage_views.get("final_segments")
        if final_view is None or not self.project_manager:
            return
        work_dir = self.project_manager.get_work_dir()
        if work_dir is None:
            final_view.setPlainText("[No project work directory available.]")
            return
        candidate = work_dir / f"{chapter_id}_chapter_info_final.json"
        final_segments: list[dict[str, Any]] = []
        if candidate.exists():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            payload_segments = payload.get("segments", []) if isinstance(payload, dict) else []
            final_segments = [copy.deepcopy(seg) for seg in payload_segments if isinstance(seg, dict)]
        if final_segments:
            final_view.setHtml(self._segments_to_html(final_segments))
        else:
            final_view.setPlainText("[No final segments available for this chapter yet.]")
