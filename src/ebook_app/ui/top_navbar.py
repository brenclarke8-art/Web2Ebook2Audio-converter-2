from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout
from PySide6.QtCore import Signal, Qt


class TopNavBar(QWidget):
    navigate = Signal(int)

    def __init__(self):
        super().__init__()

        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
            }
            QPushButton {
                background: transparent;
                color: #cccccc;
                padding: 12px 20px;
                border: none;
                font-size: 15px;
            }
            QPushButton:hover {
                color: white;
            }
            QPushButton:checked {
                color: white;
                border-bottom: 2px solid #0078d4;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(20)

        self.buttons = []

        labels = ["Pipeline", "Settings"]
        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, idx=i: self._on_nav(idx))
            layout.addWidget(btn)
            self.buttons.append(btn)

        self.buttons[0].setChecked(True)

    def _on_nav(self, index: int):
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)
        self.navigate.emit(index)
