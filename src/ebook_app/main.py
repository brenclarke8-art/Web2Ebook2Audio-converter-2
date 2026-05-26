# src/ebook_app/main.py
"""Application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from ebook_app.app import EbookAudioStudioApp


def main() -> None:
    """Launch the Ebook Audio Studio application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Ebook Audio Studio")
    app.setOrganizationName("EbookAudioStudio")

    window = EbookAudioStudioApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
