# src/ebook_app/ui/pages/scraper_page.py
"""Scraper page — configure and trigger web-novel scraping."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ebook_app.services.scraping_service import ScrapingService, _BROWSER_SCRAPER_AVAILABLE
from ebook_app.ui.pages._base_page import BasePage


class ScraperPage(BasePage):
    """Page for configuring the web scraper and starting a scrape job."""

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._service = ScrapingService(settings=self.settings)
        self._chapter_urls: list[str] = []
        self._scraped_chapters: list[dict] = []

        # Wrap in a scroll area so the page is usable at small window heights
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        inner = QVBoxLayout(container)
        inner.setContentsMargins(0, 0, 8, 0)
        inner.setSpacing(12)
        scroll.setWidget(container)
        self._layout.addWidget(scroll)

        # ── Source ──────────────────────────────────────────────────────
        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Index URL:"))
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://example.com/novel/index")
        saved_url = self.settings.get("index_url", "")
        if saved_url:
            self._url_input.setText(str(saved_url))
        url_row.addWidget(self._url_input)
        source_layout.addLayout(url_row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Scraper mode:"))
        self._http_radio = QRadioButton("HTTP (fast, no JS)")
        self._browser_radio = QRadioButton("Browser / Playwright (JS sites)")
        if not _BROWSER_SCRAPER_AVAILABLE:
            self._browser_radio.setEnabled(False)
            self._browser_radio.setToolTip(
                "Playwright is not installed. Run:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium"
            )
        self._http_radio.setChecked(True)
        self._http_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self._http_radio)
        mode_row.addWidget(self._browser_radio)
        mode_row.addStretch()
        source_layout.addLayout(mode_row)

        inner.addWidget(source_group)

        # ── Browser Options ─────────────────────────────────────────────
        self._browser_group = QGroupBox("Browser Options")
        browser_layout = QVBoxLayout(self._browser_group)

        headless_row = QHBoxLayout()
        self._headless_check = QCheckBox("Headless (no window)")
        self._headless_check.setChecked(
            not bool(self.settings.get("scraper_use_browser_gui", False))
        )
        headless_row.addWidget(self._headless_check)
        self._manual_nav_check = QCheckBox("Allow manual navigation (bypass popups/login)")
        self._manual_nav_check.setChecked(
            bool(self.settings.get("scraper_manual_navigation", False))
        )
        headless_row.addWidget(self._manual_nav_check)
        headless_row.addStretch()
        browser_layout.addLayout(headless_row)

        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("Max index pages:"))
        self._max_pages_spin = QSpinBox()
        self._max_pages_spin.setRange(1, 500)
        self._max_pages_spin.setValue(int(self.settings.get("scraper_max_index_pages", 50)))
        opt_row.addWidget(self._max_pages_spin)
        opt_row.addWidget(QLabel("Timeout (s):"))
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(5, 300)
        self._timeout_spin.setValue(int(self.settings.get("scraper_browser_timeout_sec", 30)))
        opt_row.addWidget(self._timeout_spin)
        opt_row.addStretch()
        browser_layout.addLayout(opt_row)

        css_row = QHBoxLayout()
        css_row.addWidget(QLabel("CSS selectors:"))
        self._css_input = QLineEdit()
        self._css_input.setPlaceholderText(
            "e.g. .chapter-content, #chapter-text  (comma-separated, leave blank for auto)"
        )
        self._css_input.setText(str(self.settings.get("scraper_css_selectors", "") or ""))
        css_row.addWidget(self._css_input)
        browser_layout.addLayout(css_row)

        excl_row = QHBoxLayout()
        excl_row.addWidget(QLabel("Exclude selectors:"))
        self._excl_input = QLineEdit()
        self._excl_input.setPlaceholderText("e.g. .ads, #sidebar  (comma-separated)")
        self._excl_input.setText(
            str(self.settings.get("scraper_exclude_selectors", "") or "")
        )
        excl_row.addWidget(self._excl_input)
        browser_layout.addLayout(excl_row)

        inner.addWidget(self._browser_group)
        self._browser_group.setVisible(False)

        # ── HTTP delay (shown in HTTP mode) ─────────────────────────────
        self._http_group = QGroupBox("HTTP Options")
        http_layout = QHBoxLayout(self._http_group)
        http_layout.addWidget(QLabel("Request delay (ms):"))
        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 10000)
        self._delay_spin.setValue(int(self.settings.get("scraper_delay_ms", 500)))
        http_layout.addWidget(self._delay_spin)
        http_layout.addWidget(QLabel("Max index pages:"))
        self._http_max_pages_spin = QSpinBox()
        self._http_max_pages_spin.setRange(1, 500)
        self._http_max_pages_spin.setValue(int(self.settings.get("scraper_max_index_pages", 50)))
        http_layout.addWidget(self._http_max_pages_spin)
        http_layout.addStretch()
        inner.addWidget(self._http_group)

        # ── Actions ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._scrape_index_btn = QPushButton("🔍 Scrape Index")
        self._scrape_index_btn.setToolTip("Discover chapter URLs from the index page")
        self._scrape_index_btn.clicked.connect(self._on_scrape_index)
        self._scrape_chapters_btn = QPushButton("📥 Scrape Chapters")
        self._scrape_chapters_btn.setToolTip("Download all chapters in the URL list")
        self._scrape_chapters_btn.clicked.connect(self._on_scrape_chapters)
        self._scrape_chapters_btn.setEnabled(False)
        self._cancel_btn = QPushButton("✖ Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._save_chapters_btn = QPushButton("💾 Save Chapters (JSON)")
        self._save_chapters_btn.setEnabled(False)
        self._save_chapters_btn.clicked.connect(self._on_save_chapters)
        btn_row.addWidget(self._scrape_index_btn)
        btn_row.addWidget(self._scrape_chapters_btn)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._save_chapters_btn)
        btn_row.addStretch()
        inner.addLayout(btn_row)

        # ── Progress ─────────────────────────────────────────────────────
        prog_group = QGroupBox("Progress")
        prog_layout = QVBoxLayout(prog_group)
        self._status_label = QLabel("Ready.")
        self._status_label.setWordWrap(True)
        prog_layout.addWidget(self._status_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)   # indeterminate initially
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        prog_layout.addWidget(self._progress_bar)
        inner.addWidget(prog_group)

        # ── Chapter URL list (from index scrape) ─────────────────────────
        url_list_group = QGroupBox("Discovered Chapter URLs")
        url_list_layout = QVBoxLayout(url_list_group)
        self._url_count_label = QLabel("0 URLs discovered.")
        url_list_layout.addWidget(self._url_count_label)
        self._url_list = QListWidget()
        self._url_list.setMaximumHeight(180)
        self._url_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        url_list_layout.addWidget(self._url_list)
        url_list_btn_row = QHBoxLayout()
        self._clear_urls_btn = QPushButton("Clear")
        self._clear_urls_btn.clicked.connect(self._on_clear_urls)
        self._load_urls_btn = QPushButton("Load from file…")
        self._load_urls_btn.clicked.connect(self._on_load_urls)
        url_list_btn_row.addWidget(self._clear_urls_btn)
        url_list_btn_row.addWidget(self._load_urls_btn)
        url_list_btn_row.addStretch()
        url_list_layout.addLayout(url_list_btn_row)
        inner.addWidget(url_list_group)

        # ── Chapter download status ───────────────────────────────────────
        ch_status_group = QGroupBox("Chapter Download Status")
        ch_status_layout = QVBoxLayout(ch_status_group)
        self._ch_done_label = QLabel("0 / 0 chapters downloaded.")
        ch_status_layout.addWidget(self._ch_done_label)
        self._ch_list = QListWidget()
        self._ch_list.setMaximumHeight(200)
        ch_status_layout.addWidget(self._ch_list)
        inner.addWidget(ch_status_group)

        inner.addStretch()

        # Wire service signals
        self._service.progress_changed.connect(self._on_progress_msg)
        self._service.chapter_progress.connect(self._on_chapter_progress)
        self._service.index_ready.connect(self._on_index_ready)
        self._service.chapters_ready.connect(self._on_chapters_ready)
        self._service.error_occurred.connect(self._on_error)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _use_browser(self) -> bool:
        return self._browser_radio.isChecked()

    def _sync_settings_from_ui(self) -> None:
        """Push current UI values into settings so _build_scraper reads them."""
        url = self._url_input.text().strip()
        if url:
            self.settings.set("index_url", url)
        if self._use_browser():
            self.settings.set(
                "scraper_use_browser_gui", not self._headless_check.isChecked()
            )
            self.settings.set(
                "scraper_manual_navigation", self._manual_nav_check.isChecked()
            )
            self.settings.set("scraper_max_index_pages", self._max_pages_spin.value())
            self.settings.set("scraper_browser_timeout_sec", self._timeout_spin.value())
            self.settings.set("scraper_css_selectors", self._css_input.text().strip())
            self.settings.set("scraper_exclude_selectors", self._excl_input.text().strip())
        else:
            self.settings.set("scraper_delay_ms", self._delay_spin.value())
            self.settings.set(
                "scraper_max_index_pages", self._http_max_pages_spin.value()
            )

    def _set_busy(self, busy: bool) -> None:
        self._scrape_index_btn.setEnabled(not busy)
        self._scrape_chapters_btn.setEnabled(not busy and bool(self._chapter_urls))
        self._cancel_btn.setEnabled(busy)
        self._progress_bar.setVisible(busy)
        if busy:
            self._progress_bar.setRange(0, 0)

    # ------------------------------------------------------------------
    # Slots / Handlers
    # ------------------------------------------------------------------

    def _on_mode_changed(self) -> None:
        browser = self._use_browser()
        self._browser_group.setVisible(browser)
        self._http_group.setVisible(not browser)

    def _on_scrape_index(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            self.log.log("Please enter an index URL.", level="WARNING")
            return
        self._sync_settings_from_ui()
        self._url_list.clear()
        self._chapter_urls = []
        self._url_count_label.setText("Scanning…")
        self._status_label.setText(f"Scraping index from {url}…")
        self._set_busy(True)
        self.log.log(f"Scraping index from: {url}", level="INFO")
        self._service.scrape_index(url, use_browser=self._use_browser())

    def _on_scrape_chapters(self) -> None:
        if not self._chapter_urls:
            self.log.log("No chapter URLs. Run 'Scrape Index' first.", level="WARNING")
            return
        self._sync_settings_from_ui()
        self._ch_list.clear()
        self._scraped_chapters = []
        total = len(self._chapter_urls)
        self._ch_done_label.setText(f"0 / {total} chapters downloaded.")
        self._status_label.setText(f"Downloading {total} chapters…")
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._set_busy(True)
        self.log.log(f"Scraping {total} chapters…", level="INFO")
        self._service.scrape_chapters(self._chapter_urls, use_browser=self._use_browser())

    def _on_cancel(self) -> None:
        self._service.cancel()
        self._status_label.setText("Cancelled.")
        self._progress_bar.setValue(0)
        self._set_busy(False)
        self.log.log("Scraping cancelled.", level="WARNING")

    def _on_progress_msg(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _on_chapter_progress(self, current: int, total: int, url: str) -> None:
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(current)
        short_url = url if len(url) <= 80 else url[:77] + "…"
        self._status_label.setText(f"[{current}/{total}] {short_url}")
        item = QListWidgetItem(f"⏳ [{current}/{total}] {url}")
        item.setForeground(Qt.GlobalColor.gray)
        self._ch_list.addItem(item)
        self._ch_list.scrollToBottom()

    def _on_index_ready(self, urls: list) -> None:
        self._chapter_urls = urls
        self._url_list.clear()
        for url in urls:
            self._url_list.addItem(url)
        count = len(urls)
        self._url_count_label.setText(f"{count} chapter URL{'s' if count != 1 else ''} discovered.")
        self._status_label.setText(f"✅ Index scraped — {count} chapter URLs found.")
        self._set_busy(False)
        self._scrape_chapters_btn.setEnabled(count > 0)
        self.log.log(f"Index scrape complete: {count} chapter URLs.", level="SUCCESS")

    def _on_chapters_ready(self, chapters: list) -> None:
        self._scraped_chapters = chapters
        total = len(chapters)
        errors = sum(1 for c in chapters if c.get("error"))

        # Update chapter status list — replace ⏳ entries with ✅/❌
        self._ch_list.clear()
        for ch in chapters:
            url = ch.get("url", "")
            title = ch.get("title", "")
            err = ch.get("error", "")
            if err:
                item = QListWidgetItem(f"❌ {title or url}  — {err}")
                item.setForeground(Qt.GlobalColor.red)
            else:
                item = QListWidgetItem(f"✅ {title or url}")
                item.setForeground(Qt.GlobalColor.green)
            self._ch_list.addItem(item)

        success = total - errors
        self._ch_done_label.setText(
            f"{success} / {total} chapters downloaded"
            + (f"  ({errors} errors)" if errors else "") + "."
        )
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(total)
        self._status_label.setText(
            f"✅ Chapters scraped: {success}/{total} OK."
            if not errors
            else f"⚠ Chapters scraped: {success}/{total} OK, {errors} errors."
        )
        self._save_chapters_btn.setEnabled(total > 0)
        self._set_busy(False)
        self.log.log(
            f"Chapter scrape complete: {success}/{total} OK"
            + (f", {errors} errors" if errors else ""),
            level="SUCCESS" if not errors else "WARNING",
        )

    def _on_error(self, msg: str) -> None:
        self._status_label.setText(f"🔴 Error: {msg}")
        self._set_busy(False)
        self.log.log(f"Scraper error: {msg}", level="ERROR")

    def _on_clear_urls(self) -> None:
        self._chapter_urls = []
        self._url_list.clear()
        self._url_count_label.setText("0 URLs discovered.")
        self._scrape_chapters_btn.setEnabled(False)

    def _on_load_urls(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Chapter URLs", "", "JSON files (*.json);;Text files (*.txt)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            if path.endswith(".json"):
                data = json.loads(text)
                if isinstance(data, list):
                    urls = [str(u) for u in data]
                elif isinstance(data, dict) and "urls" in data:
                    urls = [str(u) for u in data["urls"]]
                else:
                    raise ValueError("Expected a JSON list or {\"urls\": [...]} object.")
            else:
                urls = [line.strip() for line in text.splitlines() if line.strip()]
            self._chapter_urls = urls
            self._url_list.clear()
            for u in urls:
                self._url_list.addItem(u)
            count = len(urls)
            self._url_count_label.setText(f"{count} URL{'s' if count != 1 else ''} loaded.")
            self._scrape_chapters_btn.setEnabled(count > 0)
            self.log.log(f"Loaded {count} chapter URLs from {path}", level="INFO")
        except Exception as exc:
            self.log.log(f"Failed to load URLs: {exc}", level="ERROR")

    def _on_save_chapters(self) -> None:
        if not self._scraped_chapters:
            return
        output_dir = self.settings.get("output_dir", ".")
        default_path = str(Path(output_dir) / "chapters.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Chapters JSON", default_path, "JSON files (*.json)"
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(self._scraped_chapters, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.log.log(f"Saved {len(self._scraped_chapters)} chapters to {path}", level="SUCCESS")
        except Exception as exc:
            self.log.log(f"Failed to save chapters: {exc}", level="ERROR")
