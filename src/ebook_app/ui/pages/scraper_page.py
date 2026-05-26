# src/ebook_app/ui/pages/scraper_page.py
"""Scraper page — configure and trigger web-novel scraping."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ebook_app.ui.pages._base_page import BasePage


class ScraperPage(BasePage):
    """Page for configuring the web scraper and starting a scrape job.

    TODO: wire to ScrapingService when implemented.
    """

    def _build_ui(self) -> None:
        # --- Source URL group ---
        url_group = QGroupBox("Source")
        url_layout = QVBoxLayout(url_group)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Index URL:"))
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://example.com/novel/index")
        url_row.addWidget(self._url_input)
        url_layout.addLayout(url_row)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("Request delay (ms):"))
        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 10000)
        self._delay_spin.setValue(int(self.settings.get("scraper_delay_ms", 500)))
        delay_row.addWidget(self._delay_spin)
        delay_row.addStretch()
        url_layout.addLayout(delay_row)

        self._layout.addWidget(url_group)

        # --- Output group ---
        output_group = QGroupBox("Output")
        output_layout = QHBoxLayout(output_group)
        output_layout.addWidget(QLabel("Output directory:"))
        self._output_dir_input = QLineEdit()
        self._output_dir_input.setText(str(self.settings.get("output_dir", "")))
        output_layout.addWidget(self._output_dir_input)
        self._layout.addWidget(output_group)

        # --- Action buttons ---
        btn_row = QHBoxLayout()
        self._scrape_index_btn = QPushButton("Scrape Index")
        self._scrape_chapters_btn = QPushButton("Scrape Chapters")
        self._scrape_index_btn.clicked.connect(self._on_scrape_index)
        self._scrape_chapters_btn.clicked.connect(self._on_scrape_chapters)
        btn_row.addWidget(self._scrape_index_btn)
        btn_row.addWidget(self._scrape_chapters_btn)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        self._layout.addStretch()

    # ------------------------------------------------------------------
    # Handlers — TODO: replace placeholders with real service calls
    # ------------------------------------------------------------------

    def _on_scrape_index(self) -> None:
        """Placeholder: scrape chapter index from the configured URL."""
        url = self._url_input.text().strip()
        if not url:
            self.log.log("No URL specified.", level="WARNING")
            return
        self.log.log(f"Scraping index from: {url}", level="INFO")
        # TODO: start ScrapingService.scrape_index(url)

    def _on_scrape_chapters(self) -> None:
        """Placeholder: download all chapters listed in the scraped index."""
        self.log.log("Scraping chapters… (not yet implemented)", level="INFO")
        # TODO: start ScrapingService.scrape_chapters()
