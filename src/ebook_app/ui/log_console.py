# src/ebook_app/ui/log_console.py
"""Dockable log console widget."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDockWidget,
    QPlainTextEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)


_LEVELS = {
    "INFO":    "#cdd6f4",   # white-ish
    "SUCCESS": "#a6e3a1",   # green
    "WARNING": "#f9e2af",   # yellow
    "ERROR":   "#f38ba8",   # red
    "DEBUG":   "#6c7086",   # grey
}


class LogConsole(QDockWidget):
    """A dockable plain-text log console.

    Usage::

        console = LogConsole(parent=main_window)
        main_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, console)
        console.log("Hello!", level="INFO")
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Log Console", parent)
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setStyleSheet(
            "background-color: #181825; color: #cdd6f4; font-family: monospace;"
        )
        vbox.addWidget(self._text_edit)

        # Toolbar buttons
        toolbar = QWidget()
        hbox = QHBoxLayout(toolbar)
        hbox.setContentsMargins(0, 0, 0, 0)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._text_edit.clear)
        hbox.addStretch()
        hbox.addWidget(clear_btn)
        vbox.addWidget(toolbar)

        self.setWidget(container)

    @Slot(str, str)
    def log(self, message: str, level: str = "INFO") -> None:
        """Append a coloured *message* to the console.

        :param message: The text to display.
        :param level: One of INFO, SUCCESS, WARNING, ERROR, DEBUG.
        """
        colour = _LEVELS.get(level.upper(), _LEVELS["INFO"])
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colour))

        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"[{level.upper()}] {message}\n", fmt)
        self._text_edit.setTextCursor(cursor)
        self._text_edit.ensureCursorVisible()
