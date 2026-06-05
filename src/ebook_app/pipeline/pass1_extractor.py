# src/ebook_app/pipeline/pass1_extractor.py
"""
Pass‑1 Extractor
----------------
Deterministic, regex/heuristic-based extraction of candidate dialogue/thought/
narration segments from cleaned chapter text.

This pass:
    - NEVER uses an LLM
    - NEVER infers speaker or gender
    - NEVER classifies segment type
    - NEVER merges or splits based on semantics

It ONLY:
    - Splits cleaned text into paragraphs
    - Identifies candidate dialogue lines
    - Extracts minimal context (prev/next paragraph)
    - Assigns paragraph_id
    - Returns plain dict segments for Pass‑2 classification
"""

from __future__ import annotations

import re
from typing import List, Dict


class Pass1Extractor:
    """
    Deterministic first-pass extractor.

    Output format (list of dicts):
    [
        {
            "text": "...",
            "paragraph_id": 12,
            "context_before": "...",
            "context_after": "..."
        }
    ]
    """

    # Basic dialogue detection patterns
    DIALOGUE_PATTERNS = [
        re.compile(r'^["“].+["”]\s*$'),          # “Quoted dialogue”
        re.compile(r'^".+?"'),                   # "Quoted dialogue"
        re.compile(r'^[A-Z][a-z]+: '),           # Name: dialogue
        re.compile(r'^\w+\s*—'),                 # Word — dialogue
    ]

    # Paragraph splitter: cleaned text uses normalized newlines
    PARAGRAPH_SPLIT_RE = re.compile(r'\n{2,}|\r{2,}')

    def extract(self, text: str, chapter_id: str) -> List[Dict]:
        """
        Extract candidate segments from cleaned chapter text.

        Parameters
        ----------
        text : str
            Cleaned chapter text (from scrape_chapters()).
        chapter_id : str
            Chapter identifier (e.g., "ch001").

        Returns
        -------
        List[Dict]
            List of segment dictionaries.
        """
        if not text or not text.strip():
            return []

        # Split into paragraphs
        raw_paragraphs = self.PARAGRAPH_SPLIT_RE.split(text)
        paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

        segments: List[Dict] = []

        for idx, para in enumerate(paragraphs):
            paragraph_id = idx

            # Determine context
            context_before = paragraphs[idx - 1] if idx > 0 else ""
            context_after = paragraphs[idx + 1] if idx + 1 < len(paragraphs) else ""

            # Determine if this paragraph is a dialogue candidate
            is_dialogue = any(pat.search(para) for pat in self.DIALOGUE_PATTERNS)

            # Pass‑1 does NOT classify type — but we DO mark dialogue candidates
            # so Pass‑2 can use this as a hint.
            segment = {
                "text": para,
                "paragraph_id": paragraph_id,
                "context_before": context_before,
                "context_after": context_after,
                "is_dialogue_candidate": bool(is_dialogue),
            }

            segments.append(segment)

        return segments
