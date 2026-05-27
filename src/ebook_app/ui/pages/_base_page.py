# src/ebook_app/ui/pages/_base_page.py
"""Shared base class for all content pages."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ebook_app.core.settings_manager import SettingsManager
from ebook_app.core.project_manager import ProjectManager
from ebook_app.ui.log_console import LogConsole


class BasePage(QWidget):
    """Base content page.

    All pages receive a reference to the shared :class:`SettingsManager` and
    :class:`LogConsole` so they can persist state and emit log messages.

    :param settings: Shared application settings.
    :param log:      The shared log console.
    :param parent:   Qt parent widget.
    """

    def __init__(
        self,
        *,
        settings: SettingsManager,
        log: LogConsole,
        project_manager: ProjectManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.log = log
        self.project_manager = project_manager

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)

        self._build_ui()

    # ------------------------------------------------------------------
    # Subclasses override this
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Populate the page layout. Override in each page subclass."""
        raise NotImplementedError
