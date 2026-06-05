# src/ebook_app/ui/pages/pipeline_page.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QProgressBar, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Slot

from ebook_app.pipeline.pipeline_controller import PipelineController


class PipelinePage(QWidget):
    """
    UI for controlling the full 7‑phase pipeline:
        1. Scrape Index
        2. Scrape Chapters
        3. Pass‑1 Extraction
        4. Pass‑2 Classification
        5. Chapter Rebuild
        6. TTS Generation
        7. EPUB Build
    """

    def __init__(self, settings, log, project_manager):
        super().__init__()

        self.settings = settings
        self.log_console = log
        self.project_manager = project_manager

        # Pipeline controller (created per project)
        self.controller: PipelineController | None = None

        # --------------------------------------------------------------
        # Layout
        # --------------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Title
        title = QLabel("Pipeline")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # --------------------------------------------------------------
        # Chapter list
        # --------------------------------------------------------------
        self.chapter_list = QListWidget()
        self.chapter_list.setMinimumHeight(180)
        layout.addWidget(self.chapter_list)

        # --------------------------------------------------------------
        # Buttons row
        # --------------------------------------------------------------
        btn_row = QHBoxLayout()
        layout.addLayout(btn_row)

        self.btn_scrape_index = QPushButton("1. Scrape Index")
        self.btn_scrape_chapters = QPushButton("2. Scrape Chapters")
        self.btn_pass1 = QPushButton("3. Pass‑1 Extraction")
        self.btn_pass2 = QPushButton("4. Pass‑2 Classification")
        self.btn_rebuild = QPushButton("5. Rebuild Chapters")
        self.btn_tts = QPushButton("6. Generate TTS")
        self.btn_epub = QPushButton("7. Build EPUB")

        for b in [
            self.btn_scrape_index, self.btn_scrape_chapters,
            self.btn_pass1, self.btn_pass2,
            self.btn_rebuild, self.btn_tts, self.btn_epub
        ]:
            btn_row.addWidget(b)

        # --------------------------------------------------------------
        # Run full pipeline button
        # --------------------------------------------------------------
        self.btn_run_all = QPushButton("Run Full Pipeline")
        self.btn_run_all.setStyleSheet("font-weight: bold; padding: 6px;")
        layout.addWidget(self.btn_run_all)

        # --------------------------------------------------------------
        # Progress bar
        # --------------------------------------------------------------
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        # --------------------------------------------------------------
        # Connect signals
        # --------------------------------------------------------------
        self.btn_scrape_index.clicked.connect(self._run_scrape_index)
        self.btn_scrape_chapters.clicked.connect(self._run_scrape_chapters)
        self.btn_pass1.clicked.connect(self._run_pass1)
        self.btn_pass2.clicked.connect(self._run_pass2)
        self.btn_rebuild.clicked.connect(self._run_rebuild)
        self.btn_tts.clicked.connect(self._run_tts)
        self.btn_epub.clicked.connect(self._run_epub)
        self.btn_run_all.clicked.connect(self._run_full_pipeline)

        # Load initial chapter list
        self.refresh_chapter_list()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_controller(self):
        if self.controller is None:
            self.controller = self.project_manager.create_pipeline_controller()
            self.controller.set_progress_callback(self._on_progress)

    def refresh_chapter_list(self):
        """
        Reload chapters_raw.json and update the list.
        """
        self.chapter_list.clear()
        chapters = self.project_manager.load_chapter_index()

        if not chapters:
            self.chapter_list.addItem("No chapters found.")
            return

        for idx, ch in enumerate(chapters):
            title = ch.get("title", f"Chapter {idx+1}")
            item = QListWidgetItem(f"{idx+1:03d} — {title}")
            self.chapter_list.addItem(item)

    # ------------------------------------------------------------------
    # Progress callback
    # ------------------------------------------------------------------

    @Slot(str, int)
    def _on_progress(self, phase: str, percent: int):
        self.progress.setValue(percent)
        self.log_console.log(f"[{phase}] {percent}%")

    # ------------------------------------------------------------------
    # Pipeline phase handlers
    # ------------------------------------------------------------------

    def _run_scrape_index(self):
        self._ensure_controller()
        self.log_console.log("Running: Scrape Index")
        self.controller.scrape_index()
        self.refresh_chapter_list()

    def _run_scrape_chapters(self):
        self._ensure_controller()
        self.log_console.log("Running: Scrape Chapters")
        self.controller.scrape_chapters()

    def _run_pass1(self):
        self._ensure_controller()
        self.log_console.log("Running: Pass‑1 Extraction")
        self.controller.pass1_extraction()

    def _run_pass2(self):
        self._ensure_controller()
        self.log_console.log("Running: Pass‑2 Classification")
        self.controller.pass2_classification()

    def _run_rebuild(self):
        self._ensure_controller()
        self.log_console.log("Running: Chapter Rebuild")
        self.controller.smart_review_dialogue()

    def _run_tts(self):
        self._ensure_controller()
        self.log_console.log("Running: TTS Generation")
        self.controller.tts_generate()

    def _run_epub(self):
        self._ensure_controller()
        self.log_console.log("Running: EPUB Build")
        self.controller.epub_build()

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def _run_full_pipeline(self):
        self._ensure_controller()
        self.log_console.log("Running FULL PIPELINE…")

        self.controller.scrape_index()
        self.controller.scrape_chapters()
        self.controller.pass1_extraction()
        self.controller.pass2_classification()
        self.controller.smart_review_dialogue()
        self.controller.tts_generate()
        self.controller.epub_build()

        self.log_console.log("FULL PIPELINE COMPLETE.")
