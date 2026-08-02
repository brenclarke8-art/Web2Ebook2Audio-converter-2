# ebook_app/core/main_window.py
"""Main application window.

Layout
──────
  Tab 1: Pipeline Wizard
  Tab 2: Settings
  Bottom: Log console dock
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from ebook_app.core.settings_manager import SettingsManager
from ebook_app.core.project_manager import ProjectManager
from ebook_app.gui.pipeline_wizard import PipelineWizard
from ebook_app.gui.settings_view import SettingsPage

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: SettingsManager,
        project_manager: Optional[ProjectManager] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.project_manager = project_manager or ProjectManager(settings)

        self.setWindowTitle("Web2Ebook2Audio Converter")
        w = int(settings.get("window_width", 1200))
        h = int(settings.get("window_height", 800))
        self.resize(w, h)

        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Central tab widget
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.setCentralWidget(self._tabs)

        # Tab 1: Pipeline Wizard
        self._wizard = PipelineWizard(self.settings, self.project_manager)
        self._wizard.log_message.connect(self._on_log_message)
        self._wizard.pipeline_cancelled.connect(
            lambda: self._on_log_message("Pipeline reset.", "INFO")
        )
        self._wizard.pipeline_complete.connect(
            lambda: self._on_log_message("✅ Pipeline complete!", "SUCCESS")
        )
        self._tabs.addTab(self._wizard, "🔄 Pipeline")

        # Tab 2: Settings
        self._settings_page = SettingsPage(self.settings, log=self)
        self._tabs.addTab(self._settings_page, "⚙ Settings")

        # Log console dock (bottom)
        self._log_dock = self._build_log_dock()
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_dock)

    def _build_log_dock(self) -> QDockWidget:
        from ebook_app.gui.logs_viewer import LogsViewer
        dock = QDockWidget("Logs", self)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self._logs_viewer = LogsViewer()
        dock.setWidget(self._logs_viewer)
        dock.setMinimumHeight(120)
        return dock

    # ─────────────────────────────────────────────────────────────────────

    def _on_log_message(self, message: str, level: str = "INFO") -> None:
        if hasattr(self, "_logs_viewer"):
            self._logs_viewer.append_log(message, level)
        logger.info("[%s] %s", level, message)

    # Used by SettingsPage
    def log(self, message: str, level: str = "INFO") -> None:
        self._on_log_message(message, level)

    def closeEvent(self, event) -> None:
        self.settings.set("window_width", self.width())
        self.settings.set("window_height", self.height())
        self.settings.save()
        event.accept()
