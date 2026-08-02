# ebook_app/app/widgets/__init__.py
from .segment_table import SegmentTable
from .character_editor import CharacterEditor
from .chapter_selector import ChapterSelector
from .speaker_dropdown import SpeakerDropdown
from .confidence_bar import ConfidenceBar

__all__ = [
    "SegmentTable", "CharacterEditor", "ChapterSelector",
    "SpeakerDropdown", "ConfidenceBar",
]
