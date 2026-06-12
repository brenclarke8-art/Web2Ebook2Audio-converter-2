# ebook_app/app/main_window.py

from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget
)
from PySide6.QtCore import Qt

from ebook_app.app.state.book_state import ProjectManager
from ebook_app.app.top_navbar import TopNavBar
from ebook_app.app.ui.logs_viewer import LogConsole

# Pages
from ebook_app.app.ui.pipeline_view import PipelinePage
from ebook_app.app.ui.character_view import CharacterDBPage
from ebook_app.app.ui.review_view import ReviewPage
from ebook_app.app.ui.settings_view import SettingsPage


class MainWindow(QMainWindow):
    """
    Main application window for Ebook Audio Studio.
    Hosts:
        - Top navigation bar
        - Stacked pages
        - Log console dock
        - ProjectManager
    """

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.project_manager = ProjectManager(settings)

        # --------------------------------------------------------------
        # Window setup
        # --------------------------------------------------------------
        self.setWindowTitle("Ebook Audio Studio")
        self.resize(
            self.settings.get("window_width", 1280),
            self.settings.get("window_height", 800)
        )

        # --------------------------------------------------------------
        # Central widget + layout
        # --------------------------------------------------------------
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # --------------------------------------------------------------
        # Top navigation bar
        # --------------------------------------------------------------
        self.navbar = TopNavBar()
        layout.addWidget(self.navbar)

        # --------------------------------------------------------------
        # Stacked pages container
        # --------------------------------------------------------------
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)

        # --------------------------------------------------------------
        # Log console dock
        # --------------------------------------------------------------
        self.log_console = LogConsole(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_console)

        # --------------------------------------------------------------
        # Instantiate pages
        # --------------------------------------------------------------
        _page_kwargs = {
            "settings": self.settings,
            "log": self.log_console,
            "project_manager": self.project_manager,
        }

        self.pipeline_page = PipelinePage(**_page_kwargs)
        self.character_page = CharacterDBPage(**_page_kwargs)
        self.review_page = ReviewPage(**_page_kwargs)
        self.settings_page = SettingsPage(**_page_kwargs)

        # Order MUST match TopNavBar indices:
        # 0 = Pipeline
        # 1 = Characters
        # 2 = Review
        # 3 = Settings
        self.pages.addWidget(self.pipeline_page)     # 0
        self.pages.addWidget(self.character_page)    # 1
        self.pages.addWidget(self.review_page)       # 2
        self.pages.addWidget(self.settings_page)     # 3

        # --------------------------------------------------------------
        # Navigation wiring
        # --------------------------------------------------------------
        self.navbar.navigate.connect(self.pages.setCurrentIndex)

    # --------------------------------------------------------------
    # Logging helper
    # --------------------------------------------------------------
    def log(self, msg: str):
        self.log_console.log(msg)

    # --------------------------------------------------------------
    # Window close handling
    # --------------------------------------------------------------
    def closeEvent(self, event):
        # Close project
        self.project_manager.close_project()

        # Save window geometry
        self.settings.set("window_width", self.width())
        self.settings.set("window_height", self.height())

        super().closeEvent(event)
