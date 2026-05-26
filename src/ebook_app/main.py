# src/ebook_app/main.py
"""Application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from ebook_app.ui.main_window import MainWindow
from ebook_app.core.settings_manager import SettingsManager


def main() -> None:
    """Launch the Ebook Audio Studio application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Ebook Audio Studio")
    app.setOrganizationName("EbookAudioStudio")

    settings = SettingsManager()
    window = MainWindow(settings)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
