# ebook_app/app/widgets/review_inspector_panel.py

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame
)

from ebook_app.app.widgets.segment_inspector_sidebar import SegmentInspectorSidebar


class ReviewInspectorPanel(QWidget):
    """
    Composite right-side panel that integrates:
        - SegmentInspectorSidebar
        - WaveformPreviewWidget (inside sidebar)
        - JSONDiffViewer (inside sidebar)

    This panel acts as the bridge between ReviewPage and the inspector widgets.

    Emits:
        speaker_changed(name)
        request_open_character(name)
        request_rerun_llm(segment_index)
        request_preview_tts(segment_index)
        text_changed(new_text)
    """

    speaker_changed = Signal(str)
    request_open_character = Signal(str)
    request_rerun_llm = Signal(int)
    request_preview_tts = Signal(int)
    text_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Title
        title = QLabel("Inspector")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # Sidebar (contains waveform + diff + metadata)
        self.sidebar = SegmentInspectorSidebar()
        layout.addWidget(self.sidebar, 1)

        # Forward signals
        self.sidebar.speaker_changed.connect(self.speaker_changed)
        self.sidebar.request_open_character.connect(self.request_open_character)
        self.sidebar.request_rerun_llm.connect(self.request_rerun_llm)
        self.sidebar.request_preview_tts.connect(self.request_preview_tts)
        self.sidebar.text_changed.connect(self.text_changed)

    # ==================================================================
    # Public API
    # ==================================================================
    def load_character_db(self, character_db: list[dict]):
        """Load character DB into the inspector."""
        self.sidebar.load_character_db(character_db)

    def load_segment(self, segment_index: int, segment: dict,
                     pass2_json: dict, final_json: dict):
        """Load a segment into the inspector."""
        self.sidebar.load_segment(segment_index, segment, pass2_json, final_json)

    def load_waveform(self, wav_path: str):
        """Load waveform for preview."""
        self.sidebar.load_waveform(wav_path)

    def clear(self):
        """Clear inspector contents."""
        self.sidebar.text_edit.clear()
        self.sidebar.json_diff.clear()
        self.sidebar.waveform.samples = []
        self.sidebar.waveform.update()
