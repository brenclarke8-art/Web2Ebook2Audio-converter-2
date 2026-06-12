# ebook_app/app/widgets/segment_inspector_sidebar.py

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QHBoxLayout, QFrame
)

from ebook_app.app.widgets.speaker_dropdown import SpeakerDropdown
from ebook_app.app.widgets.waveform_preview_widget import WaveformPreviewWidget
from ebook_app.app.widgets.json_diff_viewer import JSONDiffViewer


class SegmentInspectorSidebar(QWidget):
    """
    A right-side metadata panel for inspecting and editing a single segment.

    Features:
        - Paragraph ID
        - Type
        - Speaker (SpeakerDropdown)
        - Text (editable)
        - Confidence
        - Character metadata (aliases, description)
        - Waveform preview
        - JSON diff viewer
        - Buttons:
            - Open in Character DB
            - Preview TTS
            - Re-run LLM classification

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

        self.segment_index = None
        self.current_segment = {}
        self.character_db = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # --------------------------------------------------------------
        # Title
        # --------------------------------------------------------------
        title = QLabel("Segment Inspector")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # --------------------------------------------------------------
        # Paragraph ID
        # --------------------------------------------------------------
        self.lbl_pid = QLabel("Paragraph ID: -")
        layout.addWidget(self.lbl_pid)

        # --------------------------------------------------------------
        # Type
        # --------------------------------------------------------------
        self.lbl_type = QLabel("Type: -")
        layout.addWidget(self.lbl_type)

        # --------------------------------------------------------------
        # Speaker dropdown
        # --------------------------------------------------------------
        self.speaker_dropdown = SpeakerDropdown()
        self.speaker_dropdown.speaker_selected.connect(self._on_speaker_selected)
        self.speaker_dropdown.add_new_character_requested.connect(self._on_add_new_character)
        layout.addWidget(self.speaker_dropdown)

        # --------------------------------------------------------------
        # Text editor
        # --------------------------------------------------------------
        layout.addWidget(QLabel("Text:"))
        self.text_edit = QTextEdit()
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit)

        # --------------------------------------------------------------
        # Confidence
        # --------------------------------------------------------------
        self.lbl_conf = QLabel("Confidence: -")
        layout.addWidget(self.lbl_conf)

        # --------------------------------------------------------------
        # Character metadata
        # --------------------------------------------------------------
        self.lbl_aliases = QLabel("Aliases: -")
        self.lbl_desc = QLabel("Description: -")
        self.lbl_desc.setWordWrap(True)

        layout.addWidget(self.lbl_aliases)
        layout.addWidget(self.lbl_desc)

        # --------------------------------------------------------------
        # Buttons
        # --------------------------------------------------------------
        btn_row = QHBoxLayout()
        layout.addLayout(btn_row)

        self.btn_open_char = QPushButton("Open Character DB")
        self.btn_preview_tts = QPushButton("Preview TTS")
        self.btn_rerun_llm = QPushButton("Re-run LLM")

        btn_row.addWidget(self.btn_open_char)
        btn_row.addWidget(self.btn_preview_tts)
        btn_row.addWidget(self.btn_rerun_llm)

        self.btn_open_char.clicked.connect(self._emit_open_character)
        self.btn_preview_tts.clicked.connect(self._emit_preview_tts)
        self.btn_rerun_llm.clicked.connect(self._emit_rerun_llm)

        # --------------------------------------------------------------
        # Separator
        # --------------------------------------------------------------
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # --------------------------------------------------------------
        # Waveform preview
        # --------------------------------------------------------------
        self.waveform = WaveformPreviewWidget()
        layout.addWidget(self.waveform)

        # --------------------------------------------------------------
        # JSON diff viewer
        # --------------------------------------------------------------
        self.json_diff = JSONDiffViewer()
        layout.addWidget(self.json_diff, 1)

        layout.addStretch()

    # ==================================================================
    # Public API
    # ==================================================================
    def load_character_db(self, character_db: list[dict]):
        """Load character DB for speaker dropdown + metadata."""
        self.character_db = character_db
        self.speaker_dropdown.load_characters(character_db)

    def load_segment(self, segment_index: int, segment: dict,
                     pass2_json: dict, final_json: dict):
        """
        Load a segment and its metadata into the inspector.
        """
        self.segment_index = segment_index
        self.current_segment = segment

        # Basic fields
        pid = segment.get("paragraph_id", "-")
        typ = segment.get("type", "-")
        speaker = segment.get("speaker", "")
        text = segment.get("text", "")
        conf = segment.get("confidence", None)

        self.lbl_pid.setText(f"Paragraph ID: {pid}")
        self.lbl_type.setText(f"Type: {typ}")
        self.text_edit.setPlainText(text)

        if conf is not None:
            self.lbl_conf.setText(f"Confidence: {conf:.2f}")
        else:
            self.lbl_conf.setText("Confidence: -")

        # Speaker dropdown
        self.speaker_dropdown.set_current_speaker(speaker)

        # Character metadata
        char = self._find_character(speaker)
        if char:
            aliases = ", ".join(char.get("aliases", []))
            desc = char.get("description", "")
            self.lbl_aliases.setText(f"Aliases: {aliases or '-'}")
            self.lbl_desc.setText(f"Description: {desc or '-'}")
        else:
            self.lbl_aliases.setText("Aliases: -")
            self.lbl_desc.setText("Description: -")

        # JSON diff
        self.json_diff.load_json(pass2_json, final_json)

    def load_waveform(self, wav_path: str):
        """Load waveform for preview."""
        self.waveform.load_wav(wav_path)

    # ==================================================================
    # Internal helpers
    # ==================================================================
    def _find_character(self, name: str):
        for char in self.character_db:
            if char.get("name") == name:
                return char
        return None

    # ==================================================================
    # Signal handlers
    # ==================================================================
    def _on_speaker_selected(self, name: str):
        self.speaker_changed.emit(name)

    def _on_add_new_character(self):
        self.request_open_character.emit("__new__")

    def _on_text_changed(self):
        self.text_changed.emit(self.text_edit.toPlainText())

    def _emit_open_character(self):
        speaker = self.current_segment.get("speaker", "")
        if speaker:
            self.request_open_character.emit(speaker)

    def _emit_preview_tts(self):
        if self.segment_index is not None:
            self.request_preview_tts.emit(self.segment_index)

    def _emit_rerun_llm(self):
        if self.segment_index is not None:
            self.request_rerun_llm.emit(self.segment_index)
