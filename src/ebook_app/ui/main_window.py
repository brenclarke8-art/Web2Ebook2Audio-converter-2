# src/ebook_app/ui/main_window.py
"""PySide6 main application window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from ebook_app.core.settings_manager import SettingsManager
from ebook_app.ui.log_console import LogConsole
from ebook_app.ui.top_navbar import TopNavBar
from ebook_app.ui.pages.scraper_page import ScraperPage
from ebook_app.ui.pages.translator_page import TranslatorPage
from ebook_app.ui.pages.tts_page import TTSPage
from ebook_app.ui.pages.epub_export_page import EpubExportPage
from ebook_app.ui.pages.pipeline_page import PipelinePage
from ebook_app.ui.pages.chapter_preview_page import ChapterPreviewPage
from ebook_app.ui.pages.settings_page import SettingsPage


_APP_STYLE = """
QMainWindow {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-size: 13px;
}
"""


class MainWindow(QMainWindow):
    """Main window: top nav bar + stacked page area + dockable log console.

    :param settings: Application :class:`~ebook_app.core.settings_manager.SettingsManager`.
    """

    def __init__(self, settings: SettingsManager) -> None:
        super().__init__()
        self.settings = settings

        self.setWindowTitle("Ebook Audio Studio")
        self.resize(1280, 800)
        self.setStyleSheet(_APP_STYLE)

        # Central widget
        central = QWidget()
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Navigation bar
        self._navbar = TopNavBar(parent=central)
        self._navbar.page_requested.connect(self._switch_page)
        vbox.addWidget(self._navbar)

        # Stacked page area
        self._stack = QStackedWidget()
        vbox.addWidget(self._stack)

        self.setCentralWidget(central)

        # Log console (dockable, bottom)
        self._log_console = LogConsole(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_console)
        self._log_console.setVisible(True)

        # Build pages
        self._pages: dict[str, QWidget] = {}
        self._register_pages()

        # Show the first page
        self._switch_page("scraper")

    # ------------------------------------------------------------------
    # Page registration
    # ------------------------------------------------------------------

    def _register_pages(self) -> None:
        page_map = {
            "scraper":         ScraperPage(settings=self.settings, log=self._log_console),
            "translator":      TranslatorPage(settings=self.settings, log=self._log_console),
            "tts":             TTSPage(settings=self.settings, log=self._log_console),
            "epub_export":     EpubExportPage(settings=self.settings, log=self._log_console),
            "pipeline":        PipelinePage(settings=self.settings, log=self._log_console),
            "chapter_preview": ChapterPreviewPage(settings=self.settings, log=self._log_console),
            "settings":        SettingsPage(settings=self.settings, log=self._log_console),
        }
        for key, widget in page_map.items():
            self._stack.addWidget(widget)
            self._pages[key] = widget

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _switch_page(self, key: str) -> None:
        """Switch the stacked widget to the page identified by *key*."""
        if key in self._pages:
            self._stack.setCurrentWidget(self._pages[key])
            self._navbar.set_active_page(key)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "INFO") -> None:
        """Proxy to :meth:`LogConsole.log`."""
        self._log_console.log(message, level=level)
