# ebook_app/app/ui/character_view.py
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ebook_app.app.ui.base_view import BasePage


class CharacterDBPage(BasePage):
    def __init__(self, *, settings, log, project_manager=None, parent=None):
        self.character_db = []
        self.current_index = None
        super().__init__(settings=settings, log=log, project_manager=project_manager, parent=parent)

    def _build_ui(self):
        self._layout.addWidget(QLabel('Character Database'))
        self.load_character_db()

    def load_character_db(self):
        if self.project_manager and hasattr(self.project_manager, 'load_character_db'):
            self.character_db = self.project_manager.load_character_db()
        else:
            self.character_db = []
