# ebook_app/gui/phase_panels/source_method_panel.py
"""Source Method Panel — lets the user choose between web URL and local folder ingestion.

This panel is shown immediately after Phase 1 (project setup) and before
Phase 2 (text retrieval).  It is **not** a numbered pipeline phase; it is a
one-time setup screen that populates ``chapter_urls`` / ``source_type`` /
``index_url`` into the wizard's accumulated phase data so that Phase 2 and the
``ChapterIterator`` can work without modification.

URL flow
────────
1. User clicks "🌐 Web URL (Browser)".
2. A Playwright browser window opens immediately (headless=False).
3. The panel shows a "Confirm Index Page" button.  The user navigates to the
   book's index page in the browser, then clicks "Confirm Index Page".
4. The app captures the current browser URL, saves it via
   ``project_manager.set_index_url()``, then runs ``WebScraper.scrape_index_page()``
   in a background thread.
5. When scanning completes the panel shows the discovered chapter count and a
   scrollable list.  The user clicks "Continue →" to proceed to Phase 2.

Local folder flow
─────────────────
1. User clicks "📁 Local Folder".
2. A native folder-picker dialog opens.
3. ``ChapterIterator.from_folder()`` scans the selected folder immediately.
4. The panel shows the discovered chapter count / list.
5. User clicks "Continue →".
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background thread for browser open + index scan
# ---------------------------------------------------------------------------

class _BrowserScanThread(QThread):
    """Opens the browser, waits for user confirmation, then scans the index."""

    scan_complete = Signal(list)          # list[str] chapter URLs
    scan_error = Signal(str)              # error message
    status_update = Signal(str)           # progress text for the label

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._chapter_urls: List[str] = []

    def run(self) -> None:
        try:
            from ebook_app.text.scrape.browser_scraper import (
                BrowserSessionManager,
                WebScraper,
            )
            # Open the browser session (request_open was already called on the
            # main thread before starting this thread so the token is ready).
            self.status_update.emit("Opening browser — navigate to the index page…")

            scraper = WebScraper(manual_navigation=True)

            def _cb(msg: str) -> None:
                self.status_update.emit(msg)

            # scrape_index_page blocks until the user clicks "Use This Page"
            # in the browser and then crawls the chapter links.
            urls = scraper.scrape_index_page("about:blank", progress_callback=_cb)
            self.scan_complete.emit(urls)
        except Exception as exc:
            logger.error("Browser scan failed: %s", exc, exc_info=True)
            self.scan_error.emit(str(exc))


# ---------------------------------------------------------------------------
# Source Method Panel widget
# ---------------------------------------------------------------------------

class SourceMethodPanel(QWidget):
    """Widget that lets the user choose and configure the chapter source.

    Signals
    -------
    source_ready
        Emitted with a dict of phase data when the source has been configured
        and the user clicks "Continue →".  Keys:
          ``source_type``   – ``"url"`` or ``"file"``
          ``chapter_urls``  – list[str] for URL mode (empty for file mode)
          ``chapter_files`` – list[str] for file mode (empty for URL mode)
          ``index_url``     – str, only meaningful for URL mode
          ``local_folder``  – str, only meaningful for file mode
    cancelled
        Emitted when the user clicks "← Back".
    """

    source_ready = Signal(dict)
    cancelled = Signal()

    def __init__(self, settings: Any, project_manager: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.project_manager = project_manager

        self._chapter_urls: List[str] = []
        self._chapter_files: List[str] = []
        self._queued_chapter_urls: List[str] = []
        self._queued_chapter_files: List[str] = []
        self._source_type: str = ""
        self._index_url: str = ""
        self._local_folder: str = ""

        self._scan_thread: Optional[_BrowserScanThread] = None

        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 12)
        outer.setSpacing(12)

        # Header
        title = QLabel("<h2>Choose Source Method</h2>")
        title.setWordWrap(True)
        outer.addWidget(title)

        desc = QLabel(
            "Select how to import chapter content.\n"
            "• Web URL: opens a browser — navigate to the book's index page and confirm.\n"
            "• Local Folder: point to a folder containing chapter files (.txt / .html)."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888;")
        outer.addWidget(desc)

        # Method buttons
        btn_row = QHBoxLayout()
        self._url_btn = QPushButton("🌐  Web URL (Browser)")
        self._url_btn.setFixedHeight(50)
        self._url_btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 8px 20px;"
            "background-color: #2d7ef7; color: white; border-radius: 6px;"
        )
        self._url_btn.clicked.connect(self._on_url_method)

        self._folder_btn = QPushButton("📁  Local Folder")
        self._folder_btn.setFixedHeight(50)
        self._folder_btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 8px 20px;"
            "background-color: #27ae60; color: white; border-radius: 6px;"
        )
        self._folder_btn.clicked.connect(self._on_folder_method)

        btn_row.addWidget(self._url_btn)
        btn_row.addWidget(self._folder_btn)
        outer.addLayout(btn_row)

        # Status / progress area
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #555; font-style: italic;")
        outer.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setVisible(False)
        outer.addWidget(self._progress_bar)

        # URL confirm button (hidden until browser is open)
        self._confirm_index_btn = QPushButton("✔  Confirm Index Page & Scan Chapters")
        self._confirm_index_btn.setFixedHeight(40)
        self._confirm_index_btn.setStyleSheet(
            "font-size: 13px; font-weight: bold; padding: 6px 16px;"
            "background-color: #e67e22; color: white; border-radius: 5px;"
        )
        self._confirm_index_btn.setVisible(False)
        self._confirm_index_btn.clicked.connect(self._on_confirm_index)
        outer.addWidget(self._confirm_index_btn)

        # Chapter list
        self._chapter_list = QListWidget()
        self._chapter_list.setVisible(False)
        self._chapter_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._chapter_list.itemChanged.connect(self._on_chapter_item_changed)
        outer.addWidget(self._chapter_list, 1)

        # Bottom navigation row
        nav_row = QHBoxLayout()
        self._back_btn = QPushButton("← Back")
        self._back_btn.clicked.connect(self.cancelled.emit)

        self._continue_btn = QPushButton("Continue →")
        self._continue_btn.setEnabled(False)
        self._continue_btn.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; padding: 6px 14px;"
        )
        self._continue_btn.clicked.connect(self._on_continue)

        nav_row.addWidget(self._back_btn)
        nav_row.addStretch()
        nav_row.addWidget(self._continue_btn)
        outer.addLayout(nav_row)

    # ─────────────────────────────────────────────────────────────────────
    # URL flow
    # ─────────────────────────────────────────────────────────────────────

    def _on_url_method(self) -> None:
        self._source_type = "url"
        self._set_buttons_enabled(False)
        self._status_label.setText(
            "Opening browser - navigate to the book's index page, then click Confirm Index Page & Scan Chapters."
        )

        # Request a browser open token from the session manager on the main thread
        try:
            from ebook_app.text.scrape.browser_scraper import BrowserSessionManager
            BrowserSessionManager.request_open()
        except Exception as exc:
            self._set_buttons_enabled(True)
            self._status_label.setText(f"⚠ Could not prepare browser session: {exc}")
            return

        # Show the confirm button — the actual browser open happens when the
        # scan thread starts (which is triggered by _on_confirm_index).
        self._confirm_index_btn.setVisible(True)
        self._status_label.setText(
            "Browser will open when you click Confirm Index Page & Scan Chapters. " "Navigate to the index page first if needed, then confirm."
        )

    def _on_confirm_index(self) -> None:
        self._confirm_index_btn.setEnabled(False)
        self._back_btn.setEnabled(False)
        self._progress_bar.setVisible(True)

        self._scan_thread = _BrowserScanThread(self)
        self._scan_thread.scan_complete.connect(self._on_scan_complete)
        self._scan_thread.scan_error.connect(self._on_scan_error)
        self._scan_thread.status_update.connect(self._status_label.setText)
        self._scan_thread.start()

    def _on_scan_complete(self, urls: List[str]) -> None:
        self._progress_bar.setVisible(False)
        self._chapter_urls = urls

        # Capture the index URL from the browser session
        try:
            from ebook_app.text.scrape.browser_scraper import BrowserSessionManager
            captured = BrowserSessionManager.get_current_url()
            if captured and captured != "about:blank":
                self._index_url = captured
        except Exception:
            pass

        # Persist to project
        if self.project_manager and self._index_url:
            self.project_manager.set_index_url(self._index_url)
        if self.project_manager:
            self.project_manager.set_source_method("url")

        self._show_chapter_list(urls, source_type="url")

    def _on_scan_error(self, error_msg: str) -> None:
        self._progress_bar.setVisible(False)
        self._confirm_index_btn.setEnabled(True)
        self._back_btn.setEnabled(True)
        self._status_label.setText(f"⚠ Scan failed: {error_msg}")
        QMessageBox.warning(self, "Scan Error", f"Chapter scan failed:\n\n{error_msg}")

    # ─────────────────────────────────────────────────────────────────────
    # Local folder flow
    # ─────────────────────────────────────────────────────────────────────

    def _on_folder_method(self) -> None:
        self._source_type = "file"
        folder = QFileDialog.getExistingDirectory(self, "Select folder containing chapter files")
        if not folder:
            return

        self._local_folder = folder
        self._set_buttons_enabled(False)
        self._status_label.setText(f"Scanning folder: {folder}")

        try:
            from ebook_app.pipeline.chapter_iterator import ChapterIterator
            iterator = ChapterIterator.from_folder(
                Path(folder),
                extensions=(".txt", ".html", ".htm"),
            )
            files = [ch.source for ch in iterator.selected_chapters]
            self._chapter_files = files

            if self.project_manager:
                self.project_manager.set_source_method("local_folder", folder)

            self._show_chapter_list(files, source_type="file")
        except Exception as exc:
            self._set_buttons_enabled(True)
            self._status_label.setText(f"⚠ Folder scan failed: {exc}")
            logger.error("Folder scan failed: %s", exc, exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────

    def _show_chapter_list(self, items: List[str], *, source_type: str) -> None:
        n = len(items)
        label = "chapter URLs" if source_type == "url" else "chapter files"
        self._status_label.setText(f"✅ Found {n} {label}. Select which chapters to queue.")

        self._chapter_list.clear()
        for item in items:
            list_item = QListWidgetItem(item)
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            list_item.setCheckState(Qt.CheckState.Checked)
            self._chapter_list.addItem(list_item)
        self._chapter_list.setVisible(True)

        self._sync_queued_selection()
        if n == 0:
            self._set_buttons_enabled(True)
            self._status_label.setText(
                "⚠ No chapters found. Try a different page or folder."
            )

    def _on_chapter_item_changed(self, _item: QListWidgetItem) -> None:
        self._sync_queued_selection()

    def _sync_queued_selection(self) -> None:
        selected_items = [
            self._chapter_list.item(i).text()
            for i in range(self._chapter_list.count())
            if self._chapter_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        if self._source_type == "url":
            self._queued_chapter_urls = selected_items
            self._queued_chapter_files = []
        elif self._source_type == "file":
            self._queued_chapter_files = selected_items
            self._queued_chapter_urls = []
        self._continue_btn.setEnabled(bool(selected_items))

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._url_btn.setEnabled(enabled)
        self._folder_btn.setEnabled(enabled)

    def _on_continue(self) -> None:
        data: dict = {
            "source_type": self._source_type,
            "chapter_urls": list(self._queued_chapter_urls),
            "chapter_files": list(self._queued_chapter_files),
            "index_url": self._index_url,
            "local_folder": self._local_folder,
        }
        selected_count = len(data["chapter_urls"] or data["chapter_files"])
        if self.project_manager:
            self.project_manager.set_selected_range(1, selected_count)
        self.source_ready.emit(data)

    # ─────────────────────────────────────────────────────────────────────
    # Reset
    # ─────────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset the panel to its initial state."""
        self._chapter_urls = []
        self._chapter_files = []
        self._queued_chapter_urls = []
        self._queued_chapter_files = []
        self._source_type = ""
        self._index_url = ""
        self._local_folder = ""

        self._status_label.setText("")
        self._progress_bar.setVisible(False)
        self._confirm_index_btn.setVisible(False)
        self._confirm_index_btn.setEnabled(True)
        self._chapter_list.clear()
        self._chapter_list.setVisible(False)
        self._continue_btn.setEnabled(False)
        self._back_btn.setEnabled(True)
        self._set_buttons_enabled(True)

        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait(2000)
        self._scan_thread = None
