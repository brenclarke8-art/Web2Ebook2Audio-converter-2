from __future__ import annotations

from PySide6.QtCore import Qt

from ebook_app.gui.phase_panels.source_method_panel import SourceMethodPanel


class _DummyProjectManager:
    def __init__(self) -> None:
        self.selected_ranges = []

    def set_selected_range(self, start: int, end: int) -> None:
        self.selected_ranges.append((start, end))


def test_continue_emits_only_checked_url_chapters(qtbot):
    project_manager = _DummyProjectManager()
    panel = SourceMethodPanel(settings={}, project_manager=project_manager)
    qtbot.addWidget(panel)

    payloads = []
    panel.source_ready.connect(payloads.append)

    panel._source_type = "url"
    panel._chapter_urls = ["url-1", "url-2", "url-3"]
    panel._show_chapter_list(panel._chapter_urls, source_type="url")

    panel._chapter_list.item(1).setCheckState(Qt.CheckState.Unchecked)
    panel._on_continue()

    assert payloads == [{
        "source_type": "url",
        "chapter_urls": ["url-1", "url-3"],
        "chapter_files": [],
        "index_url": "",
        "local_folder": "",
    }]
    assert project_manager.selected_ranges == [(1, 2)]


def test_continue_emits_only_checked_file_chapters(qtbot):
    project_manager = _DummyProjectManager()
    panel = SourceMethodPanel(settings={}, project_manager=project_manager)
    qtbot.addWidget(panel)

    payloads = []
    panel.source_ready.connect(payloads.append)

    panel._source_type = "file"
    panel._chapter_files = ["file-1.txt", "file-2.txt"]
    panel._show_chapter_list(panel._chapter_files, source_type="file")

    panel._chapter_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    panel._on_continue()

    assert payloads == [{
        "source_type": "file",
        "chapter_urls": [],
        "chapter_files": ["file-2.txt"],
        "index_url": "",
        "local_folder": "",
    }]
    assert project_manager.selected_ranges == [(1, 1)]
