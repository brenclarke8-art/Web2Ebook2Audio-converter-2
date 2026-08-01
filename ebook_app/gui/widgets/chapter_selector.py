# ebook_app/app/widgets/chapter_selector.py

from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox
from PySide6.QtCore import Signal


class ChapterSelector(QWidget):
    """
    Reusable chapter selector widget.
    Emits:
        chapter_changed(chapter_id: str)
    """

    chapter_changed = Signal(str)

    def __init__(self, project_manager, parent=None):
        super().__init__(parent)

        self.project_manager = project_manager

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Chapter:"))

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._emit_change)
        layout.addWidget(self.combo, 1)

        self.reload()

    def reload(self):
        self.combo.clear()
        chapters = self.project_manager.load_chapter_index()

        for idx, ch in enumerate(chapters):
            title = ch.get("title", f"Chapter {idx+1}")
            chapter_id = f"ch{idx+1:03d}"
            self.combo.addItem(f"{idx+1:03d} — {title}", chapter_id)

    def _emit_change(self, index):
        chapter_id = self.combo.currentData()
        if chapter_id:
            self.chapter_changed.emit(chapter_id)
