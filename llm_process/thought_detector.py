# ebook_app/text/segment/thought_detector.py
"""Detect internal thought/monologue segments."""
from __future__ import annotations
import re
from typing import List

from .segment_models import Segment

# Thought markers: italics indicators or common thought phrases
_THOUGHT_PATTERNS = [
    re.compile(r"^\*(.*?)\*$"),          # *italics*
    re.compile(r"^_(.*?)_$"),              # _italics_
    re.compile(r"^'(.*?)'$"),            # 'single quoted'
    re.compile(r"^\((.*?)\)$"),          # (parenthetical)
]


class ThoughtDetector:
    """Identify internal thought/monologue segments."""

    def classify(self, segment: Segment) -> Segment:
        """
        Reclassify a segment as 'thought' if it matches thought patterns.
        Returns the (potentially modified) segment.
        """
        text = segment.text.strip()
        for pattern in _THOUGHT_PATTERNS:
            if pattern.match(text):
                segment.type = "thought"
                break
        return segment

    def classify_all(self, segments: List[Segment]) -> List[Segment]:
        return [self.classify(s) for s in segments]
