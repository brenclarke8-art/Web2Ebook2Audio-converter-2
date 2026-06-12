# ebook_app/text/segment/dialogue_detector.py
"""Rule-based dialogue detection — splits text into dialogue and narration segments."""
from __future__ import annotations
import re
from typing import List

from .segment_models import Segment


# Common dialogue markers
_DIALOGUE_OPEN = re.compile(r'^\s*[""'「『【（《<]')
_DIALOGUE_LINE = re.compile(r'[""'「』】）》>]')


class DialogueDetector:
    """Detect and extract dialogue segments using punctuation heuristics."""

    def __init__(self, min_dialogue_length: int = 3):
        self.min_dialogue_length = min_dialogue_length

    def detect(self, text: str) -> List[Segment]:
        """
        Split *text* into alternating narration/dialogue segments.
        Returns a flat list of Segment objects.
        """
        segments: List[Segment] = []
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        for i, para in enumerate(paragraphs):
            seg_type = "dialogue" if self._is_dialogue(para) else "narration"
            segments.append(Segment(
                text=para,
                type=seg_type,
                paragraph_id=f"p{i}",
            ))
        return segments

    def _is_dialogue(self, line: str) -> bool:
        return bool(_DIALOGUE_OPEN.match(line)) and bool(_DIALOGUE_LINE.search(line))
