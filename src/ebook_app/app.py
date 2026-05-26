# src/ebook_app/app.py
"""Top-level application widget — wires together main window and settings."""

from ebook_app.core.settings_manager import SettingsManager
from ebook_app.ui.main_window import MainWindow


class EbookAudioStudioApp(MainWindow):
    """Root application window.

    Loads user settings and injects them into the main window on startup.
    """

    def __init__(self) -> None:
        self.settings = SettingsManager()
        super().__init__(settings=self.settings)
