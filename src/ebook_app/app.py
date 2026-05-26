from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
import sys

from ebook_app.ui.main_window import MainWindow
from ebook_app.core.settings_manager import SettingsManager

settings = SettingsManager()


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("Ebook Audio Studio")

    window = MainWindow(settings)
    window.show()

    sys.exit(app.exec())

