from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ebook_app.ui.pages._base_page import BasePage


class ReviewPage(BasePage):
    def __init__(self, *, settings, log, project_manager=None, parent=None):
        self.current_chapter_id = None
        self.pass2_segments = []
        self.final_segments = []
        super().__init__(settings=settings, log=log, project_manager=project_manager, parent=parent)

    def _build_ui(self):
        self._layout.addWidget(QLabel('Review & Dialogue Inspector'))

    def _on_chapter_changed(self, chapter_id: str):
        self.current_chapter_id = chapter_id

    def _save_final_chapter(self):
        if not self.current_chapter_id or not self.project_manager:
            return
        self.project_manager.save_final_chapter(self.current_chapter_id, {'segments': self.final_segments or self.pass2_segments})
        self.log.log(f'Saved final chapter {self.current_chapter_id}', level='SUCCESS')
