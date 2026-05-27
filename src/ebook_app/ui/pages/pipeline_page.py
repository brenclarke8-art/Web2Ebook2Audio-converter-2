# src/ebook_app/ui/pages/pipeline_page.py
"""Pipeline page — run project-aware chapter processing and audio generation."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
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


class PipelinePage(BasePage):
    """Page for running the end-to-end processing pipeline by project."""

    def __init__(self, **kwargs) -> None:
        self._projects: list[dict[str, Any]] = []
        self._current_book_id: str | None = None
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

    def _new_controller(self):
        if not self.project_manager:
            return None
        return self.project_manager.create_pipeline_controller(on_progress=self._update_step)

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

    def _on_check_index(self) -> None:
        if not self._require_project():
            return
        index_url = self._index_url_input.text().strip()
        if not index_url:
            self.log.log("Index URL is required.", level="WARNING")
            return
        self.settings.set("index_url", index_url)
        self.project_manager.set_index_url(index_url)

        controller = self._new_controller()
        if controller is None:
            return
        controller.scrape_index()
        inventory = controller.get_chapter_inventory()
        self.project_manager.set_inventory(
            raw_chapter_count=inventory["raw_count"],
            valid_chapter_count=inventory["valid_count"],
            chapter_urls=controller.chapter_urls,
        )
        self.log.log(
            f"Index checked: raw={inventory['raw_count']}, valid={inventory['valid_count']}.",
            level="SUCCESS",
        )
        self._load_active_project_state()

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
        self.project_manager.set_selected_range(start, end)

        controller = self._new_controller()
        if controller is None:
            return
        controller.set_chapter_range(start, end)

        try:
            controller.scrape_index()
            inventory = controller.get_chapter_inventory()
            self.project_manager.set_inventory(
                raw_chapter_count=inventory["raw_count"],
                valid_chapter_count=inventory["valid_count"],
                chapter_urls=controller.chapter_urls,
            )
            if end > inventory["valid_count"]:
                self.log.log(
                    "Requested end chapter exceeds currently available valid chapters.",
                    level="WARNING",
                )
                self._load_active_project_state()
                return
            controller.scrape_chapters()
            controller.translate_chapters()
            controller.parse_dialogue()
            self.project_manager.set_last_processed_chapter(end)
            self._load_active_project_state()
            self.log.log(
                "Chapter processing completed. Review character suggestions in Settings before audio.",
                level="SUCCESS",
            )
            QMessageBox.information(
                self,
                "Character Review Required",
                "Chapter parsing is complete. Review pending character suggestions and voices in Settings, then click 'Continue Audio + Export'.",
            )
        except Exception as exc:  # pragma: no cover - defensive UI guard
            self.log.log(f"Pipeline failed before audio stage: {exc}", level="ERROR")

    def _on_continue_audio(self) -> None:
        if not self._require_project():
            return
        selected = self.project_manager.get_selected_range()
        start = max(1, int(selected.get("start", 1)))
        end = max(start, int(selected.get("end", 0)) or start)

        self.settings.set("audio_output_mode", self._audio_mode_combo.currentText())
        self.settings.set("character_review_approved", True)
        controller = self._new_controller()
        if controller is None:
            return
        controller.set_chapter_range(start, end)
        try:
            if bool(self.settings.get("multispeaker_enabled", False)):
                controller.multispeaker_tts()
            else:
                controller.batch_tts()
            controller.forced_alignment()
            controller.smil_generation()
            controller.epub_export()
            self.log.log("Audio generation and export complete.", level="SUCCESS")
        except Exception as exc:  # pragma: no cover - defensive UI guard
            self.log.log(f"Audio/export stage failed: {exc}", level="ERROR")

    def _update_step(self, key: str, value: int) -> None:
        if key in self._step_bars:
            self._step_bars[key].setValue(value)
