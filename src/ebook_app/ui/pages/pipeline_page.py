# src/ebook_app/ui/pages/pipeline_page.py
"""Pipeline page — run the full end-to-end processing pipeline."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ebook_app.ui.pages._base_page import BasePage


_STEPS = [
    ("scrape_index",    "1. Scrape index"),
    ("scrape_chapters", "2. Scrape chapters"),
    ("translate",       "3. Translate"),
    ("parse_dialogue",  "4. Parse dialogue"),
    ("tts",             "5. TTS synthesis"),
    ("alignment",       "6. Forced alignment"),
    ("smil",            "7. Build SMIL"),
    ("export",          "8. Export EPUB3"),
]


class PipelinePage(BasePage):
    """Page for running the full automated pipeline end-to-end.

    TODO: wire each step to its corresponding service/controller call.
    """

    def _build_ui(self) -> None:
        info_group = QGroupBox("Pipeline Steps")
        vbox = QVBoxLayout(info_group)

        self._step_bars: dict[str, QProgressBar] = {}
        for key, label in _STEPS:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFixedHeight(16)
            self._step_bars[key] = bar
            row.addWidget(bar)
            vbox.addLayout(row)

        self._layout.addWidget(info_group)

        btn_row = QHBoxLayout()
        self._run_all_btn = QPushButton("▶  Run Full Pipeline")
        self._run_all_btn.clicked.connect(self._on_run_all)
        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self._run_all_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        self._layout.addStretch()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_run_all(self) -> None:
        """Placeholder: run the full pipeline via PipelineController."""
        self.log.log("Starting full pipeline… (not yet implemented)", level="INFO")
        self._run_all_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        # TODO: PipelineController.run_all(progress_callback=self._update_step)

    def _on_stop(self) -> None:
        """Placeholder: abort the running pipeline."""
        self.log.log("Pipeline stopped.", level="WARNING")
        self._run_all_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        # TODO: PipelineController.stop()

    def _update_step(self, key: str, value: int) -> None:
        """Update the progress bar for pipeline step *key* to *value* (0–100)."""
        if key in self._step_bars:
            self._step_bars[key].setValue(value)
