from PySide6.QtWidgets import QDockWidget, QTextEdit
from PySide6.QtCore import Qt


class LogConsole(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Log Console", parent)

        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("""
            QTextEdit {
                background-color: #111;
                color: #ccc;
                border: none;
                font-family: Consolas, monospace;
                font-size: 13px;
            }
        """)

        self.setWidget(self.text)

    def log(self, message: str):
        self.text.append(message)
        self.text.moveCursor(self.text.textCursor().End)
        
    def clear(self):
        self.text.clear()