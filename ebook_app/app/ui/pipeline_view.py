# ebook_app/app/ui/pipeline_view.py
"""
Pipeline page — 9-step guided wizard for the full Web → Ebook → Audio pipeline.

Steps:
  1. Project Setup      — create/load project, enter index URL
  2. Browser & Confirm  — open browser, confirm index page
  3. Index Scan         — scrape chapter index, count chapters
  4. Chapter Selection  — pick chapters to scrape (checkbox list)
  5. Scraping           — scrape + clean selected chapters
  6. LLM Setup          — confirm/override LLM settings for this run
  7. LLM Monitor        — run Pass-1/2; stream conversation log
  8. Segment Review     — review and edit speaker/type assignments
  9. TTS Export         — generate audio + EPUB
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

_log = logging.getLogger(__name__)

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ebook_app.app.ui.base_view import BasePage
from ebook_app.app.ui.book_manager import BookManagerWidget

# ---------------------------------------------------------------------------
# Step indices
# ---------------------------------------------------------------------------
_STEP_PROJECT = 0
_STEP_BROWSER = 1
_STEP_INDEX_SCAN = 2
_STEP_CHAPTER_SELECT = 3
_STEP_SCRAPING = 4
_STEP_LLM_SELECT = 5
_STEP_LLM_MONITOR = 6
_STEP_REVIEW = 7
_STEP_TTS = 8
_NUM_STEPS = 9

# Maximum character length to display for each LLM request/response in the conversation log
_CONVERSATION_LOG_MAX_DISPLAY_LENGTH = 500

_STEP_NAMES = [
    "1. Project",
    "2. Browser",
    "3. Index Scan",
    "4. Select Chapters",
    "5. Scraping",
    "6. LLM Setup",
    "7. LLM Monitor",
    "8. Review",
    "9. TTS Export",
]

_STATE_LOCKED = "locked"
_STATE_ACTIVE = "active"
_STATE_DONE = "done"
_STATE_FAILED = "failed"

_STEP_ICON = {
    _STATE_LOCKED: "🔒",
    _STATE_ACTIVE: "⏳",
    _STATE_DONE: "✅",
    _STATE_FAILED: "❌",
}


# ---------------------------------------------------------------------------
# StepProgressBar
# ---------------------------------------------------------------------------

class StepProgressBar(QWidget):
    """Horizontal row of step indicator buttons.

    Completed steps are clickable so the user can jump back to review them.
    Locked/active steps are non-clickable.
    """

    step_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        for i, label in enumerate(_STEP_NAMES):
            btn = QPushButton(f"🔒 {label}")
            btn.setCheckable(False)
            btn.setEnabled(False)
            btn.setMinimumWidth(90)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked, idx=i: self.step_clicked.emit(idx))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()
        self._apply_style()

    def set_state(self, step: int, state: str) -> None:
        if step < 0 or step >= _NUM_STEPS:
            return
        btn = self._buttons[step]
        icon = _STEP_ICON.get(state, "")
        btn.setText(f"{icon} {_STEP_NAMES[step]}")
        clickable = state == _STATE_DONE
        btn.setEnabled(clickable)
        # Highlight active step
        if state == _STATE_ACTIVE:
            btn.setStyleSheet("font-weight:bold; color:#89dceb;")
        elif state == _STATE_DONE:
            btn.setStyleSheet("color:#a6e3a1; text-decoration:underline;")
        elif state == _STATE_FAILED:
            btn.setStyleSheet("color:#f38ba8;")
        else:
            btn.setStyleSheet("color:#888;")

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                padding: 3px 6px;
                border: none;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover:enabled {
                background: #3a3a3a;
            }
        """)


# ---------------------------------------------------------------------------
# _BrowserWorkerThread
# ---------------------------------------------------------------------------

class _BrowserWorkerThread(QThread):
    """Single persistent thread that owns the Playwright browser session.

    Playwright's synchronous API binds greenlet contexts to the thread that
    called ``sync_playwright().start()``.  Using the resulting ``page`` from
    any other thread raises a greenlet context error and the framework
    responds by closing the stale session and opening a fresh browser window.
    This class prevents that: it keeps one background thread alive for the
    entire duration that the browser is needed and funnels every browser
    operation (open, index scan, chapter scraping) through that same thread
    via a task queue.
    """

    # ── Signals ────────────────────────────────────────────────────────
    launched = Signal()
    launch_failed = Signal(str)
    log_message = Signal(str, str)            # message, level
    chapter_progress = Signal(int, int, str)  # current, total, url
    index_scan_complete = Signal(dict)        # {raw_count, valid_count, chapter_urls}
    scrape_complete = Signal()
    task_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        import queue as _queue
        self._queue: _queue.Queue = _queue.Queue()
        self._active = True

    # ── Public helpers ─────────────────────────────────────────────────

    def submit(self, fn, *, description: str = "") -> None:
        """Enqueue *fn* to run on the browser thread.  Starts thread if needed."""
        self._queue.put((fn, description))
        if not self.isRunning():
            self.start()

    def request_stop(self) -> None:
        self._active = False
        self._queue.put(None)

    # ── Convenience submitters ─────────────────────────────────────────

    def open_browser(self, initial_url: str = "") -> None:
        """Request that the Playwright browser be opened."""
        from ebook_app.text.scrape.browser_scraper import BrowserSessionManager

        BrowserSessionManager.request_open()

        def _task() -> None:
            try:
                from ebook_app.text.scrape.browser_scraper import BrowserSessionManager as BSM
                page = BSM.get_page()
                if initial_url:
                    try:
                        page.goto(initial_url, timeout=30_000)
                    except Exception as nav_exc:
                        _log.warning(
                            "Could not navigate to initial URL %s: %s", initial_url, nav_exc
                        )
                self.launched.emit()
            except Exception as exc:
                self.launch_failed.emit(str(exc))

        self.submit(_task, description="open browser")

    def run_index_scan(self, ctrl) -> None:
        """Enqueue an index-scan using *ctrl*."""
        import json as _json

        def _task() -> None:
            try:
                ctrl.scrape_index()
                chapter_urls: list = []
                try:
                    chapters_raw_path = ctrl.work_dir / "chapters_raw.json"
                    if chapters_raw_path.exists():
                        chapters_data = _json.loads(
                            chapters_raw_path.read_text(encoding="utf-8")
                        )
                        chapter_urls = [
                            c.get("source", "") for c in chapters_data if c.get("source")
                        ]
                except Exception:
                    pass
                count = len(chapter_urls)
                self.index_scan_complete.emit(
                    {"raw_count": count, "valid_count": count, "chapter_urls": chapter_urls}
                )
                self.log_message.emit(
                    f"Index scan complete — {count} chapter(s) found.", "SUCCESS"
                )
            except Exception as exc:
                self.task_failed.emit(str(exc))

        self.submit(_task, description="index scan")

    def run_chapter_scrape(self, ctrl, selected_urls: list) -> None:
        """Enqueue chapter scraping for *selected_urls* using *ctrl*."""

        def _task() -> None:
            try:
                # Replace chapter_urls with the exact set chosen in the UI.
                # Reset start/end to 1/0 so scrape_chapters() iterates over all
                # of them without slicing again (the selection was already done).
                ctrl.chapter_urls = list(selected_urls)
                ctrl.selected_start_chapter = 1
                ctrl.selected_end_chapter = 0

                def _progress(current: int, total: int, url: str) -> None:
                    self.chapter_progress.emit(current, total, url)
                    self.log_message.emit(
                        f"Scraping {current}/{total}: {url}", "INFO"
                    )

                ctrl.scrape_chapters(chapter_progress_callback=_progress)
                self.scrape_complete.emit()
                self.log_message.emit("Chapter scraping complete.", "SUCCESS")
            except Exception as exc:
                self.task_failed.emit(str(exc))

        self.submit(_task, description="scrape chapters")

    # ── Thread main loop ───────────────────────────────────────────────

    def run(self) -> None:
        while self._active:
            item = self._queue.get()
            if item is None:
                break
            fn, desc = item
            try:
                fn()
            except Exception as exc:
                _log.error(
                    "_BrowserWorkerThread task '%s' raised: %s", desc, exc, exc_info=True
                )
                self.task_failed.emit(str(exc))


# ---------------------------------------------------------------------------
# _PipelineWorker
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _PipelineWorker  (non-browser operations only)
# ---------------------------------------------------------------------------

class _PipelineWorker(QThread):
    # ── Modes ──────────────────────────────────────────────────────────
    RUN_TO_REVIEW = "run_to_review"
    CONTINUE_AUDIO = "continue_audio"
    RUN_LLM = "run_llm"                   # Phases 3+4

    # ── Signals ────────────────────────────────────────────────────────
    log_message = Signal(str, str)
    inventory_ready = Signal(dict)
    finished_ok = Signal(str, str)
    failed = Signal(str)
    cancelled = Signal(str)
    conversation_message = Signal(str, str)   # role, content

    def __init__(
        self,
        *,
        project_manager,
        settings,
        mode,
        start_ch: int = 1,
        end_ch: int = 0,
        llm_url_override: str = "",
        llm_model_override: str = "",
    ):
        super().__init__()
        self.project_manager = project_manager
        self.settings = settings
        self.mode = mode
        self._start = start_ch
        self._end = end_ch
        self._llm_url_override = llm_url_override
        self._llm_model_override = llm_model_override
        self._cancel_requested = False

    def request_stop(self) -> None:
        self._cancel_requested = True

    def _abort_if_cancelled(self) -> bool:
        if self._cancel_requested:
            self.cancelled.emit("Pipeline cancelled by user.")
            return True
        return False

    # ── Mode: RUN_TO_REVIEW (legacy full run — kept for compatibility) ──
    def _run_to_review(self, ctrl) -> None:
        import json as _json

        cached_urls = list(getattr(self.project_manager, "get_chapter_urls", lambda: [])() or [])
        cached_inventory = getattr(self.project_manager, "get_inventory", lambda: {})() or {}
        if cached_urls:
            raw_count = int(cached_inventory.get("raw_chapter_count") or len(cached_urls))
            valid_count = int(cached_inventory.get("valid_chapter_count") or 0)
            if valid_count <= 0 or valid_count > len(cached_urls):
                valid_count = len(cached_urls)
            ctrl.chapter_urls = list(cached_urls)
            self.inventory_ready.emit(
                {"raw_count": raw_count, "valid_count": valid_count, "chapter_urls": cached_urls}
            )
        else:
            ctrl.scrape_index()
            work_dir = getattr(self.project_manager, "get_work_dir", lambda: None)()
            chapter_urls: list = []
            if work_dir is not None:
                chapters_raw_path = work_dir / "chapters_raw.json"
                if chapters_raw_path.exists():
                    try:
                        chapters_data = _json.loads(chapters_raw_path.read_text(encoding="utf-8"))
                        chapter_urls = [c.get("source", "") for c in chapters_data if c.get("source")]
                    except Exception:
                        pass
            count = len(chapter_urls)
            self.inventory_ready.emit(
                {"raw_count": count, "valid_count": count, "chapter_urls": chapter_urls}
            )

        if self._abort_if_cancelled():
            return

        ctrl.scrape_chapters()
        if self._abort_if_cancelled():
            return

        ctrl.pass1_extraction()
        if self._abort_if_cancelled():
            return

        ctrl.pass2_classification()
        self.finished_ok.emit(
            self.RUN_TO_REVIEW,
            "Processing complete. Review detected characters in the Review tab before audio.",
        )

    # ── Mode: CONTINUE_AUDIO ──────────────────────────────────────────
    def _run_continue_audio(self, ctrl) -> None:
        ctrl.smart_review_dialogue()
        ctrl.tts_generate()
        ctrl.epub_build()

    # ── Mode: RUN_LLM ─────────────────────────────────────────────────
    def _run_llm(self, ctrl) -> None:
        # Apply LLM overrides for this run
        if self._llm_url_override:
            ctrl.llm_client.base_url = self._llm_url_override
        if self._llm_model_override:
            ctrl.llm_client.model = self._llm_model_override

        def _on_conv(role: str, content: str) -> None:
            self.conversation_message.emit(role, content)

        ctrl.set_conversation_callback(_on_conv)
        ctrl.pass1_extraction()
        if self._abort_if_cancelled():
            return
        ctrl.pass2_classification()
        self.finished_ok.emit(
            self.RUN_LLM,
            "LLM classification complete.",
        )

    # ── Main run entry ────────────────────────────────────────────────
    def run(self) -> None:
        try:
            ctrl = self.project_manager.create_pipeline_controller()
            if self.mode == self.RUN_TO_REVIEW:
                self._run_to_review(ctrl)
            elif self.mode == self.CONTINUE_AUDIO:
                self._run_continue_audio(ctrl)
                self.finished_ok.emit(self.CONTINUE_AUDIO, "Audio generation complete.")
            elif self.mode == self.RUN_LLM:
                self._run_llm(ctrl)
        except Exception as exc:
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# PipelinePage  —  9-step wizard
# ---------------------------------------------------------------------------

class PipelinePage(BasePage):
    def __init__(self, *, settings, log, project_manager=None, parent=None):
        self._worker = None
        # Single persistent browser thread — owns the Playwright session for the
        # entire duration that the browser is needed (open → index scan → scraping).
        self._browser_thread: Optional[_BrowserWorkerThread] = None
        self._step_states: list[str] = [_STATE_LOCKED] * _NUM_STEPS
        # Runtime review state (used by segment-editing helpers)
        self._current_review_chapter_id: str = ""
        self._current_review_segments: list = []
        self._current_review_row_segment_indexes: list = []
        super().__init__(settings=settings, log=log, project_manager=project_manager, parent=parent)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Title row
        title_row = QHBoxLayout()
        title_lbl = QLabel("Pipeline Wizard")
        title_lbl.setStyleSheet("font-size:18px; font-weight:bold;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        self._layout.addLayout(title_row)

        # Step progress bar
        self._step_bar = StepProgressBar()
        self._step_bar.step_clicked.connect(self._go_to_step)
        self._layout.addWidget(self._step_bar)

        # Shared status label (underneath progress bar)
        self._status_label = QLabel("Load or create a project to begin.")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: steelblue; padding: 2px 4px;")
        self._layout.addWidget(self._status_label)

        # Stacked step pages
        self._step_stack = QStackedWidget()
        self._layout.addWidget(self._step_stack, stretch=1)

        # Build each step and add to stack
        self._step_stack.addWidget(self._build_step_project())      # 0
        self._step_stack.addWidget(self._build_step_browser())      # 1
        self._step_stack.addWidget(self._build_step_index_scan())   # 2
        self._step_stack.addWidget(self._build_step_chapter_sel())  # 3
        self._step_stack.addWidget(self._build_step_scraping())     # 4
        self._step_stack.addWidget(self._build_step_llm_select())   # 5
        self._step_stack.addWidget(self._build_step_llm_monitor())  # 6
        self._step_stack.addWidget(self._build_step_review())       # 7
        self._step_stack.addWidget(self._build_step_tts())          # 8

        # Wire project-manager signals
        if self.project_manager:
            self.project_manager.project_loaded.connect(self._on_project_loaded)
            self.project_manager.chapters_updated.connect(self._refresh_chapter_counts)

        # Activate step 1
        self._go_to_step(_STEP_PROJECT)

    # ------------------------------------------------------------------
    # Step 1 — Project Setup
    # ------------------------------------------------------------------

    def _build_step_project(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(12)

        vbox.addWidget(QLabel("<b>Step 1 — Project Setup</b>"))
        vbox.addWidget(QLabel(
            "Create a new project or select an existing one from the library, "
            "then enter the novel index URL and click <i>Open Project &amp; Continue</i>."
        ))

        # Book library
        self._book_manager = BookManagerWidget(self.project_manager)
        self._book_manager.book_opened.connect(self._on_project_opened)
        vbox.addWidget(self._book_manager)

        # Active project form
        proj_group = QGroupBox("Active Project")
        proj_form = QFormLayout(proj_group)

        self._proj_title_label = QLabel("—")
        proj_form.addRow("Title:", self._proj_title_label)
        self._proj_author_label = QLabel("—")
        proj_form.addRow("Author:", self._proj_author_label)

        url_row = QHBoxLayout()
        self._index_url_edit = QLineEdit()
        self._index_url_edit.setPlaceholderText("https://example.com/novel/")
        url_row.addWidget(self._index_url_edit)
        self._save_url_btn = QPushButton("Save URL")
        self._save_url_btn.clicked.connect(self._on_save_index_url)
        url_row.addWidget(self._save_url_btn)
        proj_form.addRow("Index URL:", url_row)

        vbox.addWidget(proj_group)

        # Advance button
        self._step1_continue_btn = QPushButton("Open Project & Continue →")
        self._step1_continue_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._step1_continue_btn.setEnabled(False)
        self._step1_continue_btn.clicked.connect(self._on_step1_continue)
        vbox.addWidget(self._step1_continue_btn)
        vbox.addStretch()
        return w

    # ------------------------------------------------------------------
    # Step 2 — Browser & Index Confirm
    # ------------------------------------------------------------------

    def _build_step_browser(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(12)

        vbox.addWidget(QLabel("<b>Step 2 — Browser &amp; Index Page Confirmation</b>"))
        self._step2_info_lbl = QLabel(
            "The browser will open to the index URL. Navigate or log in if required, "
            "then click <i>Confirm Index Page</i> to continue."
        )
        self._step2_info_lbl.setWordWrap(True)
        vbox.addWidget(self._step2_info_lbl)

        self._step2_browser_status = QLabel("Browser not yet opened.")
        self._step2_browser_status.setStyleSheet("color: steelblue; font-style: italic;")
        vbox.addWidget(self._step2_browser_status)

        btn_row = QHBoxLayout()
        self._open_browser_btn = QPushButton("🌐 Open Browser")
        self._open_browser_btn.clicked.connect(self._on_open_browser)
        btn_row.addWidget(self._open_browser_btn)

        self._confirm_index_btn = QPushButton("✅ Confirm Index Page →")
        self._confirm_index_btn.setEnabled(False)
        self._confirm_index_btn.setStyleSheet("font-weight:bold;")
        self._confirm_index_btn.clicked.connect(self._on_step2_confirm)
        btn_row.addWidget(self._confirm_index_btn)
        btn_row.addStretch()
        vbox.addLayout(btn_row)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self._go_to_step(_STEP_PROJECT))
        vbox.addWidget(back_btn)
        vbox.addStretch()
        return w

    # ------------------------------------------------------------------
    # Step 3 — Index Scan
    # ------------------------------------------------------------------

    def _build_step_index_scan(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(12)

        vbox.addWidget(QLabel("<b>Step 3 — Chapter Index Scan</b>"))
        vbox.addWidget(QLabel(
            "Scan the index page to discover all chapter URLs. "
            "The browser scraper will follow pagination automatically."
        ))

        self._ch_count_label = QLabel("Not scanned yet.")
        self._ch_count_label.setStyleSheet("font-weight: bold;")
        vbox.addWidget(self._ch_count_label)

        self._index_chapters_btn = QPushButton("🔍 Scan Chapter Index")
        self._index_chapters_btn.setStyleSheet("padding:8px 16px;")
        self._index_chapters_btn.clicked.connect(self._on_index_chapters)
        vbox.addWidget(self._index_chapters_btn)

        self._step3_stop_btn = QPushButton("⛔ Stop")
        self._step3_stop_btn.setEnabled(False)
        self._step3_stop_btn.clicked.connect(self._on_stop_pipeline)
        vbox.addWidget(self._step3_stop_btn)

        self._step3_continue_btn = QPushButton("Proceed to Chapter Selection →")
        self._step3_continue_btn.setEnabled(False)
        self._step3_continue_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._step3_continue_btn.clicked.connect(self._on_step3_continue)
        vbox.addWidget(self._step3_continue_btn)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self._go_to_step(_STEP_BROWSER))
        vbox.addWidget(back_btn)
        vbox.addStretch()
        return w

    # ------------------------------------------------------------------
    # Step 4 — Chapter Selection
    # ------------------------------------------------------------------

    def _build_step_chapter_sel(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        vbox.addWidget(QLabel("<b>Step 4 — Select Chapters to Scrape</b>"))
        vbox.addWidget(QLabel(
            "Check the chapters you want to include. Use the quick-range spinboxes "
            "to select a contiguous range, then click <i>Apply Range</i>."
        ))

        # Quick range row
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Range — Start:"))
        self._start_ch_spin = QSpinBox()
        self._start_ch_spin.setRange(1, 9999)
        self._start_ch_spin.setValue(1)
        range_row.addWidget(self._start_ch_spin)
        range_row.addWidget(QLabel("End (0 = all):"))
        self._end_ch_spin = QSpinBox()
        self._end_ch_spin.setRange(0, 9999)
        self._end_ch_spin.setValue(0)
        range_row.addWidget(self._end_ch_spin)
        apply_range_btn = QPushButton("Apply Range")
        apply_range_btn.clicked.connect(self._on_apply_chapter_range)
        range_row.addWidget(apply_range_btn)
        range_row.addStretch()
        vbox.addLayout(range_row)

        # Toolbar buttons
        toolbar = QHBoxLayout()
        sel_all_btn = QPushButton("☑ Select All")
        sel_all_btn.clicked.connect(self._on_chapter_select_all)
        toolbar.addWidget(sel_all_btn)
        desel_all_btn = QPushButton("☐ Deselect All")
        desel_all_btn.clicked.connect(self._on_chapter_deselect_all)
        toolbar.addWidget(desel_all_btn)
        toolbar.addStretch()
        vbox.addLayout(toolbar)

        # Chapter checklist inside a scroll area
        self._chapter_list_table = QTableWidget(0, 3)
        self._chapter_list_table.setHorizontalHeaderLabels(["☑", "#", "URL / Title"])
        header = self._chapter_list_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._chapter_list_table.verticalHeader().setVisible(False)
        self._chapter_list_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        vbox.addWidget(self._chapter_list_table, stretch=1)

        self._selected_count_lbl = QLabel("0 chapters selected.")
        vbox.addWidget(self._selected_count_lbl)

        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("▶  Start Scraping Selected Chapters")
        self._run_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._run_btn.clicked.connect(self._on_run_scrape)
        btn_row.addWidget(self._run_btn)
        self._stop_btn = QPushButton("⛔  Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("color:#f38ba8;")
        self._stop_btn.clicked.connect(self._on_stop_pipeline)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        vbox.addLayout(btn_row)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self._go_to_step(_STEP_INDEX_SCAN))
        vbox.addWidget(back_btn)
        return w

    # ------------------------------------------------------------------
    # Step 5 — Scraping
    # ------------------------------------------------------------------

    def _build_step_scraping(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        vbox.addWidget(QLabel("<b>Step 5 — Scraping &amp; Text Cleaning</b>"))

        self._scrape_progress_lbl = QLabel("Waiting to start…")
        self._scrape_progress_lbl.setWordWrap(True)
        vbox.addWidget(self._scrape_progress_lbl)

        self._scrape_progress_bar = QProgressBar()
        self._scrape_progress_bar.setRange(0, 100)
        self._scrape_progress_bar.setValue(0)
        vbox.addWidget(self._scrape_progress_bar)

        # Preview tabs (populated after scraping completes)
        preview_lbl = QLabel("Chapter preview (available after scraping completes):")
        vbox.addWidget(preview_lbl)
        self._scrape_preview_tabs = QTabWidget()
        vbox.addWidget(self._scrape_preview_tabs, stretch=1)

        btn_row = QHBoxLayout()
        self._step5_continue_btn = QPushButton("Confirm &amp; Continue to LLM →")
        self._step5_continue_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._step5_continue_btn.setEnabled(False)
        self._step5_continue_btn.clicked.connect(self._on_step5_continue)
        btn_row.addWidget(self._step5_continue_btn)
        btn_row.addStretch()
        vbox.addLayout(btn_row)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self._go_to_step(_STEP_CHAPTER_SELECT))
        vbox.addWidget(back_btn)
        return w

    # ------------------------------------------------------------------
    # Step 6 — LLM Setup
    # ------------------------------------------------------------------

    def _build_step_llm_select(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(12)

        vbox.addWidget(QLabel("<b>Step 6 — LLM Selection &amp; Configuration</b>"))
        vbox.addWidget(QLabel(
            "Review the LLM settings below. You can override them for this run only "
            "(changes here do not affect global Settings)."
        ))

        llm_group = QGroupBox("LLM Settings (this run)")
        llm_form = QFormLayout(llm_group)

        self._llm_provider_combo = QComboBox()
        for p in ("ollama_local", "openai_cloud", "external_cloud"):
            self._llm_provider_combo.addItem(p)
        llm_form.addRow("Provider:", self._llm_provider_combo)

        self._llm_url_edit = QLineEdit()
        self._llm_url_edit.setPlaceholderText("http://127.0.0.1:11434")
        llm_form.addRow("URL:", self._llm_url_edit)

        self._llm_model_edit = QLineEdit()
        self._llm_model_edit.setPlaceholderText("e.g. mistral")
        llm_form.addRow("Model:", self._llm_model_edit)

        vbox.addWidget(llm_group)

        self._step6_start_btn = QPushButton("▶  Start LLM Processing")
        self._step6_start_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._step6_start_btn.clicked.connect(self._on_step6_start_llm)
        vbox.addWidget(self._step6_start_btn)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self._go_to_step(_STEP_SCRAPING))
        vbox.addWidget(back_btn)
        vbox.addStretch()
        return w

    # ------------------------------------------------------------------
    # Step 7 — LLM Conversation Monitor
    # ------------------------------------------------------------------

    def _build_step_llm_monitor(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        vbox.addWidget(QLabel("<b>Step 7 — LLM Processing Monitor</b>"))

        self._llm_progress_lbl = QLabel("LLM classification running…")
        self._llm_progress_lbl.setWordWrap(True)
        vbox.addWidget(self._llm_progress_lbl)

        self._llm_progress_bar = QProgressBar()
        self._llm_progress_bar.setRange(0, 0)  # indeterminate
        vbox.addWidget(self._llm_progress_bar)

        conv_lbl = QLabel("Conversation log:")
        vbox.addWidget(conv_lbl)

        self._conversation_log = QPlainTextEdit()
        self._conversation_log.setReadOnly(True)
        self._conversation_log.setStyleSheet(
            "font-family: monospace; font-size: 11px; background: #1e1e2e; color: #cdd6f4;"
        )
        vbox.addWidget(self._conversation_log, stretch=1)

        btn_row = QHBoxLayout()
        self._step7_continue_btn = QPushButton("Continue to Segment Review →")
        self._step7_continue_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._step7_continue_btn.setEnabled(False)
        self._step7_continue_btn.clicked.connect(self._on_step7_continue)
        btn_row.addWidget(self._step7_continue_btn)
        btn_row.addStretch()
        vbox.addLayout(btn_row)
        return w

    # ------------------------------------------------------------------
    # Step 8 — Segment Review
    # ------------------------------------------------------------------

    def _build_step_review(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        vbox.addWidget(QLabel("<b>Step 8 — Final Segment Review</b>"))
        vbox.addWidget(QLabel(
            "Review and edit the speaker and segment-type assignments for each chapter. "
            "Save your edits before proceeding to TTS."
        ))

        # Chapter selector
        ch_row = QHBoxLayout()
        ch_row.addWidget(QLabel("Chapter:"))
        self._review_chapter_combo = QComboBox()
        self._review_chapter_combo.setMinimumWidth(280)
        self._review_chapter_combo.currentIndexChanged.connect(self._on_review_chapter_changed)
        ch_row.addWidget(self._review_chapter_combo)
        reload_btn = QPushButton("↺ Reload")
        reload_btn.clicked.connect(self._load_review_chapter_list)
        ch_row.addWidget(reload_btn)
        ch_row.addStretch()
        vbox.addLayout(ch_row)

        # Segment table
        self._segment_table = QTableWidget(0, 3)
        self._segment_table.setHorizontalHeaderLabels(["Text", "Speaker", "Type"])
        seg_header = self._segment_table.horizontalHeader()
        seg_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        seg_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        seg_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._segment_table.setAlternatingRowColors(True)
        self._segment_table.verticalHeader().setVisible(False)
        vbox.addWidget(self._segment_table, stretch=1)

        # Detected characters table
        char_group = QGroupBox("Detected Characters")
        char_vbox = QVBoxLayout(char_group)
        self._detected_char_table = QTableWidget(0, 5)
        self._detected_char_table.setHorizontalHeaderLabels(
            ["Name", "Gender", "Voice", "Confidence", "First in"]
        )
        det_hdr = self._detected_char_table.horizontalHeader()
        det_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        det_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        det_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._detected_char_table.setAlternatingRowColors(True)
        self._detected_char_table.verticalHeader().setVisible(False)
        char_vbox.addWidget(self._detected_char_table)
        vbox.addWidget(char_group)

        # Action buttons
        action_row = QHBoxLayout()
        save_seg_btn = QPushButton("💾 Save Segment Edits")
        save_seg_btn.clicked.connect(self._on_save_segment_speakers)
        action_row.addWidget(save_seg_btn)
        save_char_btn = QPushButton("💾 Save Character Edits")
        save_char_btn.clicked.connect(self._on_save_detected_characters)
        action_row.addWidget(save_char_btn)
        recheck_btn = QPushButton("🔄 Re-check Dialogue")
        recheck_btn.clicked.connect(self._on_recheck_dialogue)
        action_row.addWidget(recheck_btn)
        action_row.addStretch()
        vbox.addLayout(action_row)

        self._step8_tts_btn = QPushButton("▶  Save &amp; Send to TTS →")
        self._step8_tts_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._step8_tts_btn.clicked.connect(self._on_step8_send_tts)
        vbox.addWidget(self._step8_tts_btn)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self._go_to_step(_STEP_LLM_MONITOR))
        vbox.addWidget(back_btn)
        return w

    # ------------------------------------------------------------------
    # Step 9 — TTS Export
    # ------------------------------------------------------------------

    def _build_step_tts(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(12)

        vbox.addWidget(QLabel("<b>Step 9 — TTS Audio &amp; EPUB Export</b>"))

        self._tts_progress_lbl = QLabel("Ready to generate audio.")
        self._tts_progress_lbl.setWordWrap(True)
        vbox.addWidget(self._tts_progress_lbl)

        self._tts_progress_bar = QProgressBar()
        self._tts_progress_bar.setRange(0, 100)
        vbox.addWidget(self._tts_progress_bar)

        self._tts_output_lbl = QLabel("Output: —")
        self._tts_output_lbl.setWordWrap(True)
        vbox.addWidget(self._tts_output_lbl)

        btn_row = QHBoxLayout()
        self._tts_generate_btn = QPushButton("▶  Generate Audio + EPUB")
        self._tts_generate_btn.setStyleSheet("padding:8px 16px; font-weight:bold;")
        self._tts_generate_btn.clicked.connect(self._on_generate_tts)
        btn_row.addWidget(self._tts_generate_btn)
        self._tts_stop_btn = QPushButton("⛔  Stop")
        self._tts_stop_btn.setEnabled(False)
        self._tts_stop_btn.setStyleSheet("color:#f38ba8;")
        self._tts_stop_btn.clicked.connect(self._on_stop_pipeline)
        btn_row.addWidget(self._tts_stop_btn)
        btn_row.addStretch()
        vbox.addLayout(btn_row)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self._go_to_step(_STEP_REVIEW))
        vbox.addWidget(back_btn)
        vbox.addStretch()
        return w

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------

    def _go_to_step(self, step: int) -> None:
        """Navigate the wizard to the given step index."""
        if step < 0 or step >= _NUM_STEPS:
            return
        self._step_stack.setCurrentIndex(step)
        # Update states: previously-done steps keep their state; active step gets active
        for i in range(_NUM_STEPS):
            if i == step:
                self._step_states[i] = _STATE_ACTIVE
                self._step_bar.set_state(i, _STATE_ACTIVE)
            elif self._step_states[i] == _STATE_ACTIVE:
                # Leave previously active as done (already passed through)
                self._step_states[i] = _STATE_LOCKED
                self._step_bar.set_state(i, _STATE_LOCKED)
            else:
                self._step_bar.set_state(i, self._step_states[i])

    def _mark_step_done(self, step: int) -> None:
        self._step_states[step] = _STATE_DONE
        self._step_bar.set_state(step, _STATE_DONE)

    def _mark_step_failed(self, step: int) -> None:
        self._step_states[step] = _STATE_FAILED
        self._step_bar.set_state(step, _STATE_FAILED)

    def _advance_to(self, next_step: int, current_step: int) -> None:
        self._mark_step_done(current_step)
        self._go_to_step(next_step)

    # ------------------------------------------------------------------
    # Step 1 handlers
    # ------------------------------------------------------------------

    def _on_project_opened(self, book_id: str) -> None:
        self._load_active_project_state()

    def _on_project_loaded(self, book_id: str) -> None:
        self._load_active_project_state()

    def _load_active_project_state(self) -> None:
        if not self.project_manager or not self.project_manager.current_book_id:
            self._step1_continue_btn.setEnabled(False)
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

        # Pre-fill LLM settings from global settings
        self._llm_url_edit.setText(
            self.settings.get("llm_url", self.settings.get("dialogue_llm_url", "")) or ""
        )
        self._llm_model_edit.setText(
            self.settings.get("llm_model", self.settings.get("dialogue_llm_model", "")) or ""
        )
        provider = self.settings.get("llm_provider", "ollama_local") or "ollama_local"
        idx = self._llm_provider_combo.findText(provider)
        if idx >= 0:
            self._llm_provider_combo.setCurrentIndex(idx)

        self._step1_continue_btn.setEnabled(True)
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
            self._ch_count_label.setText("Not scraped yet.")
        title = self._proj_title_label.text()
        self._status_label.setText(
            f"Project: <b>{title}</b> — {valid} chapter(s) available"
        )

    def _on_save_index_url(self) -> None:
        if not self.project_manager or not self.project_manager.current_book_id:
            return
        url = self._index_url_edit.text().strip()
        self.project_manager.set_index_url(url)
        self.settings.set("index_url", url)
        self.log.log(f"Index URL saved: {url}", level="SUCCESS")

    def _on_step1_continue(self) -> None:
        if not self.project_manager or not self.project_manager.current_book_id:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return
        self._on_save_index_url()
        self._advance_to(_STEP_BROWSER, _STEP_PROJECT)
        # Auto-open browser when entering step 2
        self._on_open_browser()

    # ------------------------------------------------------------------
    # Step 2 handlers
    # ------------------------------------------------------------------

    def _ensure_browser_thread(self) -> _BrowserWorkerThread:
        """Return (creating if necessary) the persistent browser worker thread."""
        if self._browser_thread is None or not self._browser_thread.isRunning():
            bt = _BrowserWorkerThread(parent=self)
            bt.launched.connect(self._on_browser_launched)
            bt.launch_failed.connect(self._on_browser_launch_failed)
            bt.log_message.connect(lambda msg, lvl: self.log.log(msg, level=lvl))
            bt.chapter_progress.connect(self._on_chapter_progress)
            bt.index_scan_complete.connect(self._on_index_scan_complete)
            bt.scrape_complete.connect(self._on_scrape_complete)
            bt.task_failed.connect(self._on_browser_task_failed)
            self._browser_thread = bt
        return self._browser_thread

    def _on_open_browser(self) -> None:
        try:
            from ebook_app.text.scrape.browser_scraper import PLAYWRIGHT_AVAILABLE
        except ImportError as exc:
            self.log.log(f"Failed to import browser scraper: {exc}", level="ERROR")
            QMessageBox.critical(self, "Import Error", f"Could not import browser scraper:\n\n{exc}")
            return

        if not PLAYWRIGHT_AVAILABLE:
            msg = (
                "Playwright is not installed.\n\n"
                "Install it with:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
            self.log.log(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium",
                level="ERROR",
            )
            QMessageBox.critical(self, "Playwright Not Installed", msg)
            return

        # If the browser thread is already running a task, don't re-open
        bt = self._browser_thread
        if bt is not None and bt.isRunning() and not bt._queue.empty():
            self.log.log("Browser is already launching.", level="INFO")
            return

        self._status_label.setStyleSheet("color: steelblue;")
        self._status_label.setText("🌐 Opening browser…")
        self.log.log("Launching browser window…", level="INFO")
        self._open_browser_btn.setEnabled(False)

        index_url = self._index_url_edit.text().strip()
        self._ensure_browser_thread().open_browser(initial_url=index_url)

    def _on_browser_launched(self) -> None:
        self._open_browser_btn.setEnabled(True)
        self._confirm_index_btn.setEnabled(True)
        self._step2_browser_status.setText(
            "🌐 Browser is open. Navigate or log in if needed, then click Confirm Index Page."
        )
        self._status_label.setStyleSheet("color: steelblue;")
        self._status_label.setText(
            "🌐 Browser open. Navigate to the correct index page, then confirm."
        )
        self.log.log(
            "Browser opened. Navigate to the correct index page if needed, then click Confirm Index Page.",
            level="SUCCESS",
        )

    def _on_browser_launch_failed(self, error: str) -> None:
        self._open_browser_btn.setEnabled(True)
        self._confirm_index_btn.setEnabled(False)
        self._step2_browser_status.setText(f"❌ Browser launch failed: {error}")
        self._status_label.setStyleSheet("color: red;")
        self._status_label.setText("Browser launch failed.")
        self.log.log(f"Failed to open browser: {error}", level="ERROR")
        QMessageBox.critical(self, "Browser Error", f"Could not open browser:\n\n{error}")

    def _on_browser_task_failed(self, error: str) -> None:
        self._set_buttons_enabled(True)
        self._status_label.setStyleSheet("color: #f38ba8;")
        self._status_label.setText(f"❌ Browser error: {error}")
        self.log.log(f"Browser task failed: {error}", level="ERROR")
        QMessageBox.critical(self, "Browser Error", f"Browser task failed:\n\n{error}")

    def _on_step2_confirm(self) -> None:
        self._advance_to(_STEP_INDEX_SCAN, _STEP_BROWSER)

    # ------------------------------------------------------------------
    # Step 3 handlers
    # ------------------------------------------------------------------

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

        ctrl = self.project_manager.create_pipeline_controller()
        if ctrl is None:
            QMessageBox.critical(self, "Error", "Could not create pipeline controller.")
            self._set_buttons_enabled(True)
            return

        self.log.log("Scraping index page for chapter URLs…", level="INFO")
        self._ensure_browser_thread().run_index_scan(ctrl)

    def _on_index_scan_complete(self, data: dict) -> None:
        """Slot called from _BrowserWorkerThread when index scan finishes."""
        raw = data.get("raw_count", 0)
        valid = data.get("valid_count", 0)
        self._on_inventory_ready(data)
        self._set_buttons_enabled(True)
        self._status_label.setStyleSheet("color: #a6e3a1;")
        self._status_label.setText(f"✅ Index scan complete — {valid} chapter(s) found.")
        if valid > 0:
            self._step3_continue_btn.setEnabled(True)
        self._load_active_project_state()

    def _on_step3_continue(self) -> None:
        self._populate_chapter_checklist()
        self._advance_to(_STEP_CHAPTER_SELECT, _STEP_INDEX_SCAN)

    # ------------------------------------------------------------------
    # Step 4 handlers
    # ------------------------------------------------------------------

    def _populate_chapter_checklist(self) -> None:
        """Fill the chapter checklist table from the cached inventory."""
        self._chapter_list_table.setRowCount(0)
        if not self.project_manager:
            return
        urls = list(self.project_manager.get_chapter_urls() or [])
        if not urls:
            # Fallback: read from chapters_raw.json
            work_dir = self.project_manager.get_work_dir()
            if work_dir:
                raw_path = work_dir / "chapters_raw.json"
                if raw_path.exists():
                    try:
                        chapters = json.loads(raw_path.read_text(encoding="utf-8"))
                        urls = [c.get("source", "") for c in chapters if c.get("source")]
                    except Exception:
                        pass

        self._chapter_list_table.setRowCount(len(urls))
        for row, url in enumerate(urls):
            chk = QCheckBox()
            chk.setChecked(True)
            chk.stateChanged.connect(self._update_selected_count)
            self._chapter_list_table.setCellWidget(row, 0, chk)
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._chapter_list_table.setItem(row, 1, num_item)
            url_item = QTableWidgetItem(url)
            url_item.setFlags(url_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._chapter_list_table.setItem(row, 2, url_item)

        self._update_selected_count()

    def _update_selected_count(self) -> None:
        total = self._chapter_list_table.rowCount()
        selected = sum(
            1 for row in range(total)
            if self._get_chapter_checkbox(row) and self._get_chapter_checkbox(row).isChecked()
        )
        self._selected_count_lbl.setText(f"{selected} of {total} chapters selected.")

    def _get_chapter_checkbox(self, row: int) -> Optional[QCheckBox]:
        w = self._chapter_list_table.cellWidget(row, 0)
        return w if isinstance(w, QCheckBox) else None

    def _on_chapter_select_all(self) -> None:
        for row in range(self._chapter_list_table.rowCount()):
            chk = self._get_chapter_checkbox(row)
            if chk:
                chk.setChecked(True)

    def _on_chapter_deselect_all(self) -> None:
        for row in range(self._chapter_list_table.rowCount()):
            chk = self._get_chapter_checkbox(row)
            if chk:
                chk.setChecked(False)

    def _on_apply_chapter_range(self) -> None:
        start = self._start_ch_spin.value() - 1  # 0-indexed
        end = self._end_ch_spin.value()
        total = self._chapter_list_table.rowCount()
        if end == 0:
            end = total
        for row in range(total):
            chk = self._get_chapter_checkbox(row)
            if chk:
                chk.setChecked(start <= row < end)
        self._update_selected_count()

    def _get_selected_urls(self) -> List[str]:
        urls = []
        for row in range(self._chapter_list_table.rowCount()):
            chk = self._get_chapter_checkbox(row)
            if chk and chk.isChecked():
                item = self._chapter_list_table.item(row, 2)
                if item:
                    urls.append(item.text())
        return urls

    def _on_run_scrape(self) -> None:
        if self._is_busy():
            QMessageBox.warning(self, "Busy", "A pipeline task is already running.")
            return
        if not self.project_manager or not self.project_manager.current_book_id:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return

        selected_urls = self._get_selected_urls()
        if not selected_urls:
            QMessageBox.warning(self, "No Chapters", "Please select at least one chapter to scrape.")
            return

        # Save chapter range into project for resumability
        start = self._start_ch_spin.value()
        end_val = self._end_ch_spin.value()
        self.project_manager.set_selected_range(start, end_val)

        ctrl = self.project_manager.create_pipeline_controller()
        if ctrl is None:
            QMessageBox.critical(self, "Error", "Could not create pipeline controller.")
            return

        self._set_buttons_enabled(False)
        self._go_to_step(_STEP_SCRAPING)
        self._scrape_progress_lbl.setText(f"⏳ Scraping {len(selected_urls)} chapter(s)…")
        self._scrape_progress_bar.setRange(0, len(selected_urls))
        self._scrape_progress_bar.setValue(0)
        # Clear previous preview tabs
        while self._scrape_preview_tabs.count():
            self._scrape_preview_tabs.removeTab(0)

        self.log.log(f"Scraping {len(selected_urls)} selected chapters.", level="INFO")
        # Route through the browser thread so all Playwright calls stay on one thread.
        self._ensure_browser_thread().run_chapter_scrape(ctrl, selected_urls)

    def _on_chapter_progress(self, current: int, total: int, url: str) -> None:
        """Update step 5 progress bar/label from the browser thread."""
        self._scrape_progress_bar.setRange(0, total)
        self._scrape_progress_bar.setValue(current)
        self._scrape_progress_lbl.setText(f"⏳ Scraping {current}/{total}: {url}")

    def _on_scrape_complete(self) -> None:
        """Called when _BrowserWorkerThread finishes chapter scraping."""
        n = self._scrape_progress_bar.maximum()
        self._scrape_progress_bar.setValue(n)
        msg = f"Scraping complete — {n} chapter(s) scraped."
        self._scrape_progress_lbl.setText(f"✅ {msg}")
        self._step5_continue_btn.setEnabled(True)
        self._mark_step_done(_STEP_CHAPTER_SELECT)
        self._set_buttons_enabled(True)
        self._populate_scrape_preview()
        self._load_active_project_state()
        self.log.log(msg, level="SUCCESS")
        self._status_label.setStyleSheet("color: #a6e3a1;")
        self._status_label.setText(f"✅ {msg}")

    # ------------------------------------------------------------------
    # Step 5 handlers
    # ------------------------------------------------------------------

    def _on_step5_continue(self) -> None:
        self._advance_to(_STEP_LLM_SELECT, _STEP_SCRAPING)

    def _populate_scrape_preview(self) -> None:
        """Populate the preview tabs with scraped/cleaned text after scraping."""
        while self._scrape_preview_tabs.count():
            self._scrape_preview_tabs.removeTab(0)
        work_dir = self.project_manager.get_work_dir() if self.project_manager else None
        if not work_dir:
            return
        for raw_file in sorted(work_dir.glob("ch*_raw.txt")):
            chapter_id = raw_file.name.replace("_raw.txt", "")
            tab = QWidget()
            tab_vbox = QVBoxLayout(tab)
            tab_vbox.setContentsMargins(4, 4, 4, 4)
            raw_edit = QPlainTextEdit()
            raw_edit.setReadOnly(True)
            raw_edit.setPlainText(raw_file.read_text(encoding="utf-8", errors="replace"))
            cleaned_file = work_dir / f"{chapter_id}_cleaned.txt"
            cleaned_edit = QPlainTextEdit()
            cleaned_edit.setReadOnly(True)
            if cleaned_file.exists():
                cleaned_edit.setPlainText(cleaned_file.read_text(encoding="utf-8", errors="replace"))
            inner_tabs = QTabWidget()
            inner_tabs.addTab(raw_edit, "Scraped")
            inner_tabs.addTab(cleaned_edit, "Cleaned")
            tab_vbox.addWidget(inner_tabs)
            self._scrape_preview_tabs.addTab(tab, chapter_id)

    # ------------------------------------------------------------------
    # Step 6 handlers
    # ------------------------------------------------------------------

    def _on_step6_start_llm(self) -> None:
        if self._is_busy():
            QMessageBox.warning(self, "Busy", "A pipeline task is already running.")
            return
        if not self.project_manager or not self.project_manager.current_book_id:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return

        llm_url = self._llm_url_edit.text().strip()
        llm_model = self._llm_model_edit.text().strip()

        self._go_to_step(_STEP_LLM_MONITOR)
        self._llm_progress_lbl.setText("⏳ Running LLM classification…")
        self._llm_progress_bar.setRange(0, 0)
        self._conversation_log.clear()
        self._step7_continue_btn.setEnabled(False)

        self._worker = _PipelineWorker(
            project_manager=self.project_manager,
            settings=self.settings,
            mode=_PipelineWorker.RUN_LLM,
            llm_url_override=llm_url,
            llm_model_override=llm_model,
        )
        self._worker.finished_ok.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.cancelled.connect(self._on_worker_cancelled)
        self._worker.log_message.connect(lambda msg, lvl: self.log.log(msg, level=lvl))
        self._worker.conversation_message.connect(self._on_conversation_message)
        self._worker.start()
        self.log.log("LLM classification started.", level="INFO")

    # ------------------------------------------------------------------
    # Step 7 handlers
    # ------------------------------------------------------------------

    def _on_conversation_message(self, role: str, content: str) -> None:
        """Append an LLM conversation turn to the monitor log."""
        if role == "request":
            prefix = "→ [REQUEST]"
            color = "#89dceb"
        else:
            prefix = "← [RESPONSE]"
            color = "#a6e3a1"
        # Truncate long content for display
        display = content[:_CONVERSATION_LOG_MAX_DISPLAY_LENGTH] + ("…" if len(content) > _CONVERSATION_LOG_MAX_DISPLAY_LENGTH else "")
        self._conversation_log.appendPlainText(f"{prefix}\n{display}\n{'─' * 60}")

    def _on_step7_continue(self) -> None:
        self._load_review_chapter_list()
        self._advance_to(_STEP_REVIEW, _STEP_LLM_MONITOR)

    # ------------------------------------------------------------------
    # Step 8 handlers
    # ------------------------------------------------------------------

    def _load_review_chapter_list(self) -> None:
        self._review_chapter_combo.blockSignals(True)
        self._review_chapter_combo.clear()
        work_dir = self.project_manager.get_work_dir() if self.project_manager else None
        if work_dir:
            for p in sorted(work_dir.glob("ch*_pass2.json")):
                chapter_id = p.name.replace("_pass2.json", "")
                self._review_chapter_combo.addItem(chapter_id, userData=chapter_id)
        self._review_chapter_combo.blockSignals(False)
        if self._review_chapter_combo.count() > 0:
            self._review_chapter_combo.setCurrentIndex(0)
            self._on_review_chapter_changed(0)

    def _on_review_chapter_changed(self, index: int) -> None:
        if index < 0 or not self.project_manager:
            return
        chapter_id = self._review_chapter_combo.itemData(index)
        if not chapter_id:
            return
        self._current_review_chapter_id = chapter_id
        self._populate_segment_table(chapter_id)

    def _populate_segment_table(self, chapter_id: str) -> None:
        """Load pass2 segments for chapter_id into _segment_table."""
        segments = list(self.project_manager.load_pass2_segments(chapter_id))
        self._current_review_segments = segments
        self._current_review_row_segment_indexes = list(range(len(segments)))

        from ebook_app.tts.voice_catalog import KOKORO_VOICE_LIST
        char_names = ["narrator"] + [
            e.get("name", "") for e in self._load_character_database_entries() if e.get("name")
        ]

        self._segment_table.setRowCount(len(segments))
        for row, seg in enumerate(segments):
            text_item = QTableWidgetItem(str(seg.get("text", "")))
            text_item.setFlags(text_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._segment_table.setItem(row, 0, text_item)

            spk_combo = QComboBox()
            for n in char_names:
                spk_combo.addItem(n)
            current_spk = seg.get("speaker", "narrator")
            idx = spk_combo.findText(current_spk)
            if idx < 0:
                spk_combo.addItem(current_spk)
                idx = spk_combo.count() - 1
            spk_combo.setCurrentIndex(idx)
            self._segment_table.setCellWidget(row, 1, spk_combo)

            type_combo = QComboBox()
            for t in ("narration", "dialogue", "thought"):
                type_combo.addItem(t)
            cur_type = self._normalize_segment_type(seg.get("type", "narration"))
            type_combo.setCurrentText(cur_type)
            self._segment_table.setCellWidget(row, 2, type_combo)

    def _on_step8_send_tts(self) -> None:
        self._on_save_segment_speakers()
        self._advance_to(_STEP_TTS, _STEP_REVIEW)

    # ------------------------------------------------------------------
    # Step 9 handlers
    # ------------------------------------------------------------------

    def _on_generate_tts(self) -> None:
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
        self._tts_progress_lbl.setText("⏳ Generating audio + EPUB…")
        self._tts_progress_bar.setRange(0, 0)

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
        self.log.log("Audio generation started.", level="INFO")

    # ------------------------------------------------------------------
    # Shared pipeline run helpers
    # ------------------------------------------------------------------

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable/disable the primary action buttons in the active step."""
        for btn in (
            self._index_chapters_btn,
            self._run_btn,
            self._stop_btn,
            self._tts_generate_btn,
        ):
            try:
                if btn is self._stop_btn:
                    btn.setEnabled(not enabled)
                else:
                    btn.setEnabled(enabled)
            except RuntimeError:
                # Qt widget was deleted (C++ object lifetime mismatch); skip safely
                pass

    def _is_busy(self) -> bool:
        worker_running = False
        if self._worker is not None:
            try:
                worker_running = bool(self._worker.isRunning())
            except RuntimeError:
                self._worker = None

        browser_busy = False
        if self._browser_thread is not None:
            try:
                browser_busy = bool(self._browser_thread.isRunning() and not self._browser_thread._queue.empty())
            except RuntimeError:
                self._browser_thread = None

        return worker_running or browser_busy

    def _on_stop_pipeline(self) -> None:
        stopped_any = False
        if self._worker is not None:
            try:
                if self._worker.isRunning():
                    self._worker.request_stop()
                    stopped_any = True
            except RuntimeError:
                self._worker = None
        if self._browser_thread is not None:
            try:
                if self._browser_thread.isRunning():
                    self._browser_thread.request_stop()
                    stopped_any = True
            except RuntimeError:
                self._browser_thread = None
        if stopped_any:
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
        self._status_label.setText(f"⏳ Index scraped — {valid} chapters found.")
        # Enable step 3 continue button
        if valid > 0:
            self._step3_continue_btn.setEnabled(True)

    def _on_worker_finished(self, mode: str, message: str) -> None:
        worker = self._worker
        self._worker = None
        if self.project_manager and worker is not None:
            self.project_manager.set_last_processed_chapter(getattr(worker, "_end", 0))
        self._set_buttons_enabled(True)
        self._load_active_project_state()
        self.log.log(message, level="SUCCESS")
        lbl = getattr(self, "_status_label", None)
        if lbl is not None:
            lbl.setStyleSheet("color: #a6e3a1;")
            lbl.setText(f"✅ {message}")

        if mode == _PipelineWorker.RUN_LLM:
            self._llm_progress_bar.setRange(0, 100)
            self._llm_progress_bar.setValue(100)
            self._llm_progress_lbl.setText(f"✅ {message}")
            self._step7_continue_btn.setEnabled(True)
            self._mark_step_done(_STEP_LLM_SELECT)

        elif mode == _PipelineWorker.CONTINUE_AUDIO:
            self._tts_progress_bar.setRange(0, 100)
            self._tts_progress_bar.setValue(100)
            self._tts_progress_lbl.setText(f"✅ {message}")
            work_dir = self.project_manager.get_work_dir() if self.project_manager else None
            if work_dir:
                self._tts_output_lbl.setText(f"Output: {work_dir}")
            self._mark_step_done(_STEP_TTS)

        elif mode == _PipelineWorker.RUN_TO_REVIEW:
            QMessageBox.information(
                self,
                "Ready for Review",
                "Scraping and chapter parsing are complete. Review scraped text and detected "
                "characters in the Review tab, then click 'Generate Audio + Epub' when ready.",
            )

    def _on_worker_failed(self, error: str) -> None:
        self._worker = None
        self._set_buttons_enabled(True)
        self._status_label.setStyleSheet("color: #f38ba8;")
        self._status_label.setText(f"❌ Pipeline error: {error}")
        self.log.log(f"Pipeline failed: {error}", level="ERROR")
        QMessageBox.critical(self, "Pipeline Error", f"Pipeline failed:\n\n{error}")

    def _on_worker_cancelled(self, message: str) -> None:
        self._worker = None
        self._set_buttons_enabled(True)
        self._status_label.setStyleSheet("color: #f9e2af;")
        self._status_label.setText(f"⚠ {message}")
        self.log.log(message, level="WARNING")

    # ------------------------------------------------------------------
    # Legacy pipeline entry (kept for backward compatibility / direct call)
    # ------------------------------------------------------------------

    def _on_run_to_review(self) -> None:
        """Legacy single-click run to review (used by any external callers)."""
        if self._is_busy():
            QMessageBox.warning(self, "Busy", "A pipeline task is already running.")
            return
        if not self.project_manager or not self.project_manager.current_book_id:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return
        self._on_save_index_url()
        start_ch = self._start_ch_spin.value()
        end_ch = self._end_ch_spin.value()
        self.project_manager.set_selected_range(start_ch, end_ch)

        self._set_buttons_enabled(False)
        self._status_label.setText("⏳ Running: scraping chapters + LLM classification…")
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
        self.log.log("Begin Scrape: scraping chapters + classification.", level="INFO")

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
        """No-op placeholder; override in subclasses that render a final preview."""

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
        """No-op placeholder; override to refresh combo boxes after character DB changes."""

    def _refresh_review_data(self) -> None:
        """No-op placeholder; override to reload review data when pipeline finishes."""

    def _require_project(self) -> bool:
        """Return True if a project is loaded; warn and return False otherwise."""
        if self.project_manager and self.project_manager.current_book_id:
            return True
        QMessageBox.warning(self, "No Project", "Please open or create a project first.")
        return False

    def _default_voice_for_gender(self, gender: str) -> str:
        male = self.settings.get("default_male_voice", "am_adam") or "am_adam"
        female = self.settings.get("default_female_voice", "af_heart") or "af_heart"
        narrator = self.settings.get("narrator_voice", "af_narrator") or "af_narrator"
        if gender == "male":
            return male
        if gender == "female":
            return female
        return narrator

