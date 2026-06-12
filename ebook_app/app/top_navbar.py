# ebook_app/app/top_navbar.py

from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Signal, Qt


class TopNavBar(QWidget):
    """
    Modern top navigation bar for Ebook Audio Studio.
    Emits:
        navigate(index: int)
    """

    navigate = Signal(int)

    def __init__(self):
        super().__init__()

        self.setObjectName("TopNavBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        # Button labels must match MainWindow page order
        self.buttons = []
        labels = ["Pipeline", "Characters", "Review", "Settings", "Tests"]

        for idx, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, i=idx: self._on_nav(i))
            layout.addWidget(btn)
            self.buttons.append(btn)

        # Default selection
        self.buttons[0].setChecked(True)

        self._apply_stylesheet()

    # --------------------------------------------------------------
    # Navigation handler
    # --------------------------------------------------------------
    def _on_nav(self, index: int):
        # Update button states
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)

        # Emit navigation signal
        self.navigate.emit(index)

    # --------------------------------------------------------------
    # Styling
    # --------------------------------------------------------------
    def _apply_stylesheet(self):
        """
        Minimal dark‑mode friendly style.
        """
        self.setStyleSheet("""
        #TopNavBar {
            background-color: #2b2b2b;
            border-bottom: 1px solid #444;
        }

        QPushButton {
            background: transparent;
            color: #ddd;
            padding: 6px 14px;
            border-radius: 4px;
            font-size: 14px;
        }

        QPushButton:hover {
            background-color: #3a3a3a;
        }

        QPushButton:checked {
            background-color: #5050ff;
            color: white;
        }
        """)
