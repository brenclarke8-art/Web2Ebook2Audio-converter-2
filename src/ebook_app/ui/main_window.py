from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget
)
from PySide6.QtCore import Qt

from ebook_app.core.project_manager import ProjectManager
from ebook_app.ui.top_navbar import TopNavBar
from ebook_app.ui.pages.settings_page import SettingsPage
from ebook_app.ui.log_console import LogConsole
from ebook_app.ui.pages.pipeline_page import PipelinePage

class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.project_manager = ProjectManager(settings)

        self.setWindowTitle("Ebook Audio Studio")
        self.resize(
            self.settings.get("window_width"),
            self.settings.get("window_height")
         )

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top navigation bar
        self.navbar = TopNavBar()
        layout.addWidget(self.navbar)

        # Stacked pages
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)

        # Logging console dock (must be created before pages so it can be passed in)
        self.log_console = LogConsole(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_console)

        # Add pages — order must match TopNavBar label indices:
        # 0=Pipeline, 1=Settings
        _page_kwargs = {
            "settings": self.settings,
            "log": self.log_console,
            "project_manager": self.project_manager,
        }
        self.pipeline_page = PipelinePage(**_page_kwargs)
        self.settings_page = SettingsPage(**_page_kwargs)

        self.pages.addWidget(self.pipeline_page)        # 0
        self.pages.addWidget(self.settings_page)        # 1

        # Connect nav buttons
        self.navbar.navigate.connect(self.pages.setCurrentIndex)

    def log(self, msg: str):
        self.log_console.log(msg)

    def closeEvent(self, event):
        # Close current project and save state
        self.project_manager.close_project()

        # Save window settings
        self.settings.set("window_width", self.width())
        self.settings.set("window_height", self.height())
        super().closeEvent(event)
