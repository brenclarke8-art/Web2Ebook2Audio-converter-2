# ebook_app/app/ui/test_view.py
"""
Test Runner page — run the project's pytest suite from inside the GUI.

Features
--------
* Run all tests or a subset selected from the list.
* Real-world scrape test: enter an index URL, pick index page number and a
  chapter number; the page fetches those URLs and shows the raw/cleaned text
  so anti-scrape behaviour can be inspected live.
* All output streams into the embedded log area in real time.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List

from PySide6.QtCore import QProcess, Qt, Signal, QObject
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ebook_app.app.ui.base_view import BasePage

# ---------------------------------------------------------------------------
# Helper: discover test files relative to the repository root
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Walk up from this file until we find pyproject.toml."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[4]  # last resort


def _discover_test_files(repo: Path) -> List[str]:
    tests_dir = repo / "tests"
    if not tests_dir.is_dir():
        return []
    return sorted(p.name for p in tests_dir.glob("test_*.py"))


# ---------------------------------------------------------------------------
# Test Runner Page
# ---------------------------------------------------------------------------

class TestPage(BasePage):
    """GUI page that runs pytest and a real-world scrape test."""

    def _build_ui(self) -> None:
        self._repo = _repo_root()

        # ── Title ──────────────────────────────────────────────────────────
        title = QLabel("Test Runner")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        self._layout.addWidget(title)

        # ── Main splitter: left = controls, right = output ─────────────────
        splitter = QSplitter(Qt.Horizontal)
        self._layout.addWidget(splitter, stretch=1)

        # ── LEFT panel ────────────────────────────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(10)
        splitter.addWidget(left_panel)

        # Unit-test selector
        tests_group = QGroupBox("Unit Tests")
        tg_layout = QVBoxLayout(tests_group)
        left_layout.addWidget(tests_group)

        sel_row = QHBoxLayout()
        sel_all = QPushButton("Select All")
        sel_none = QPushButton("Clear")
        sel_row.addWidget(sel_all)
        sel_row.addWidget(sel_none)
        sel_row.addStretch()
        tg_layout.addLayout(sel_row)

        self._test_list = QListWidget()
        self._test_list.setSelectionMode(QListWidget.NoSelection)
        for name in _discover_test_files(self._repo):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self._test_list.addItem(item)
        tg_layout.addWidget(self._test_list)

        sel_all.clicked.connect(lambda: self._set_all_checked(Qt.Checked))
        sel_none.clicked.connect(lambda: self._set_all_checked(Qt.Unchecked))

        run_tests_btn = QPushButton("▶  Run Selected Tests")
        run_tests_btn.setStyleSheet("padding:6px 14px; font-weight:bold;")
        run_tests_btn.clicked.connect(self._run_unit_tests)
        left_layout.addWidget(run_tests_btn)

        # Real-world scrape test
        scrape_group = QGroupBox("Real-World Scrape Test")
        sg_layout = QVBoxLayout(scrape_group)
        left_layout.addWidget(scrape_group)

        sg_layout.addWidget(QLabel("Index URL:"))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://example.com/novel/")
        sg_layout.addWidget(self._url_edit)

        page_row = QHBoxLayout()
        page_row.addWidget(QLabel("Index page #:"))
        self._index_page_spin = QSpinBox()
        self._index_page_spin.setRange(1, 9999)
        self._index_page_spin.setValue(1)
        self._index_page_spin.setToolTip(
            "Which pagination page of the index to fetch (1 = first page)."
        )
        page_row.addWidget(self._index_page_spin)
        page_row.addStretch()
        sg_layout.addLayout(page_row)

        ch_row = QHBoxLayout()
        ch_row.addWidget(QLabel("Chapter # to preview:"))
        self._chapter_spin = QSpinBox()
        self._chapter_spin.setRange(1, 9999)
        self._chapter_spin.setValue(1)
        self._chapter_spin.setToolTip(
            "After the index is scraped, fetch this chapter (1-based)."
        )
        ch_row.addWidget(self._chapter_spin)
        ch_row.addStretch()
        sg_layout.addLayout(ch_row)

        self._show_cleaned_cb = QCheckBox("Show cleaned text (not raw HTML)")
        self._show_cleaned_cb.setChecked(True)
        sg_layout.addWidget(self._show_cleaned_cb)

        run_scrape_btn = QPushButton("▶  Run Scrape Test")
        run_scrape_btn.setStyleSheet("padding:6px 14px; font-weight:bold;")
        run_scrape_btn.clicked.connect(self._run_scrape_test)
        sg_layout.addWidget(run_scrape_btn)

        left_layout.addStretch()

        # ── RIGHT panel: output log ────────────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        splitter.addWidget(right_panel)

        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Output"))
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_log)
        log_header.addWidget(clear_btn)
        log_header.addStretch()
        right_layout.addLayout(log_header)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet(
            "font-family: monospace; font-size: 12px; background:#1e1e1e; color:#d4d4d4;"
        )
        right_layout.addWidget(self._output, stretch=1)

        self._status_label = QLabel("")
        right_layout.addWidget(self._status_label)

        splitter.setSizes([340, 700])

        # Process handle
        self._process: QProcess | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_all_checked(self, state: Qt.CheckState) -> None:
        for i in range(self._test_list.count()):
            self._test_list.item(i).setCheckState(state)

    def _checked_test_files(self) -> List[str]:
        result = []
        for i in range(self._test_list.count()):
            item = self._test_list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(str(self._repo / "tests" / item.text()))
        return result

    def _append(self, text: str, colour: str = "#d4d4d4") -> None:
        escaped = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
                .replace(" ", "&nbsp;")
        )
        self._output.append(f'<span style="color:{colour}">{escaped}</span>')

    def _clear_log(self) -> None:
        self._output.clear()
        self._status_label.setText("")

    # ------------------------------------------------------------------
    # Unit test runner (subprocess via QProcess)
    # ------------------------------------------------------------------

    def _run_unit_tests(self) -> None:
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._append("⚠ Tests already running.", "#ffcc00")
            return

        files = self._checked_test_files()
        if not files:
            self._append("No test files selected.", "#ff6666")
            return

        self._clear_log()
        self._append("Running pytest …\n", "#888888")

        env_path = str(self._repo)
        import os
        env = dict(os.environ)
        py_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{env_path}{os.pathsep}{py_path}" if py_path else env_path

        self._process = QProcess(self)
        self._process.setProcessEnvironment(self._make_qenv(env))
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)

        args = ["-m", "pytest", "-v", "--tb=short", "--no-header"] + files
        self._process.start(sys.executable, args)

    def _make_qenv(self, env: dict):
        from PySide6.QtCore import QProcessEnvironment
        qenv = QProcessEnvironment()
        for k, v in env.items():
            qenv.insert(k, v)
        return qenv

    def _on_stdout(self) -> None:
        raw = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in raw.splitlines():
            colour = "#d4d4d4"
            if "PASSED" in line or "passed" in line:
                colour = "#4ec94e"
            elif "FAILED" in line or "ERROR" in line or "error" in line.lower():
                colour = "#ff6666"
            elif "WARNING" in line or "warning" in line.lower():
                colour = "#ffcc00"
            self._append(line, colour)

    def _on_stderr(self) -> None:
        raw = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        for line in raw.splitlines():
            self._append(line, "#ff9944")

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        if exit_code == 0:
            self._status_label.setText("✅  All selected tests passed.")
            self._status_label.setStyleSheet("color:#4ec94e; font-weight:bold;")
        else:
            self._status_label.setText(f"❌  Tests finished with exit code {exit_code}.")
            self._status_label.setStyleSheet("color:#ff6666; font-weight:bold;")

    # ------------------------------------------------------------------
    # Real-world scrape test
    # ------------------------------------------------------------------

    def _run_scrape_test(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            self._append("Please enter an index URL.", "#ff6666")
            return

        index_page = self._index_page_spin.value()
        chapter_num = self._chapter_spin.value()
        show_cleaned = self._show_cleaned_cb.isChecked()

        self._append(f"\n=== Scrape Test ===", "#888888")
        self._append(f"Index URL     : {url}", "#888888")
        self._append(f"Index page #  : {index_page}", "#888888")
        self._append(f"Chapter #     : {chapter_num}", "#888888")

        try:
            from ebook_app.text.scrape.web_scraper import HttpWebScraper

            scraper = HttpWebScraper(request_delay=0.2)

            # Scrape up to `index_page` pages of the index so the user can
            # see whichever page they requested.
            self._append("\nFetching index …", "#888888")
            chapter_urls = scraper.scrape_index_page(
                url,
                max_pages=index_page,
                progress_callback=lambda msg: self._append(f"  {msg}", "#888888"),
            )

            if not chapter_urls:
                self._append("⚠ No chapter URLs detected on this index.", "#ffcc00")
                return

            self._append(
                f"\nFound {len(chapter_urls)} chapter URLs (showing first 10):", "#888888"
            )
            for i, cu in enumerate(chapter_urls[:10], 1):
                self._append(f"  {i}. {cu}", "#a0c8ff")

            # Fetch the requested chapter
            if chapter_num > len(chapter_urls):
                self._append(
                    f"\n⚠ Chapter {chapter_num} out of range "
                    f"(only {len(chapter_urls)} found). Showing last chapter.",
                    "#ffcc00",
                )
                chapter_num = len(chapter_urls)

            target_url = chapter_urls[chapter_num - 1]
            self._append(f"\nFetching chapter {chapter_num}: {target_url}", "#888888")

            chapters = scraper.scrape_chapters(
                [target_url],
                progress_callback=lambda idx, tot, u: self._append(
                    f"  Scraping {idx}/{tot}: {u}", "#888888"
                ),
            )

            if chapters:
                ch = chapters[0]
                self._append(f"\nTitle : {ch.get('title', '(no title)')}", "#a0c8ff")
                if "error" in ch:
                    self._append(f"Error : {ch['error']}", "#ff6666")
                else:
                    content = ch.get("content", "")
                    if not show_cleaned:
                        # Re-fetch raw HTML for inspection
                        try:
                            from ebook_app.text.scrape.base_scraper import BaseScraper
                            raw_html = BaseScraper().fetch(target_url)
                            content = raw_html[:4000] + (
                                "\n… (truncated)" if len(raw_html) > 4000 else ""
                            )
                        except Exception as exc:
                            content = f"(raw fetch failed: {exc})"
                    else:
                        if len(content) > 4000:
                            content = content[:4000] + "\n… (truncated)"

                    self._append(
                        f"\n{'--- Cleaned Text ---' if show_cleaned else '--- Raw HTML ---'}",
                        "#888888",
                    )
                    self._append(content, "#d4d4d4")
                    self._status_label.setText(
                        f"✅  Scrape OK — {len(ch.get('content',''))} chars"
                    )
                    self._status_label.setStyleSheet("color:#4ec94e; font-weight:bold;")
            else:
                self._append("No chapter data returned.", "#ff6666")

        except Exception as exc:
            self._append(f"\n❌ Scrape error: {exc}", "#ff6666")
            self._status_label.setText("❌  Scrape failed.")
            self._status_label.setStyleSheet("color:#ff6666; font-weight:bold;")
            if self.log:
                self.log.log(f"Scrape test error: {exc}", level="ERROR")
