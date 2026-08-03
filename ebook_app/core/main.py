# ebook_app/core/main.py
"""Entry point for the Web2Ebook2Audio Converter application."""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def main() -> None:
    # Limit OMP thread count before any import that might set it
    os.environ.setdefault("OMP_NUM_THREADS", "4")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Web2Ebook2Audio Converter")
    app.setOrganizationName("brenclarke8-art")

    # Load settings
    from ebook_app.core.settings_manager import SettingsManager
    settings = SettingsManager()

    # Apply theme
    theme = settings.get("theme", "dark")
    if theme == "dark":
        try:
            import qdarkstyle  # type: ignore
            app.setStyleSheet(qdarkstyle.load_stylesheet())
        except ImportError:
            pass  # qdarkstyle optional

    # Prevent Qt from quitting when the startup-checker dialog (the only open
    # window at this point) is closed.  Without this, closing the dialog fires
    # QApplication.quit(), which queues a quit event that causes the subsequent
    # app.exec() call to return immediately — leaving no visible main window.
    app.setQuitOnLastWindowClosed(False)

    # Startup checks (model download, TTS, Ollama, LLM)
    from ebook_app.core.startup_checker import StartupCheckerDialog
    checker = StartupCheckerDialog(settings)
    # start_checks() is also triggered automatically via showEvent, but calling
    # it here first ensures checks are queued before exec() blocks.
    checker.start_checks()
    checker.exec()  # blocks until done or "Proceed Anyway" clicked

    # Re-enable normal quit-on-close behaviour so the app exits when the main
    # window is closed.
    app.setQuitOnLastWindowClosed(True)

    # Launch main window
    from ebook_app.core.main_window import MainWindow
    window = MainWindow(settings)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
