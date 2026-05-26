# src/ebook_app/models/dialogue_parser.py
"""LLM-powered dialogue parser — segments text into speaker-tagged lines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class Segment:
    """A single spoken or narrated segment.

    :param text:        The raw text content.
    :param speaker:     Speaker name, or ``'narrator'`` for narration.
    :param kind:        ``'dialogue'`` | ``'narration'``.
    :param paragraph_id: Unique identifier for SMIL synchronisation.
    """

    text: str
    speaker: str = "narrator"
    kind: Literal["dialogue", "narration"] = "narration"
    paragraph_id: str = ""


class DialogueParser:
    """Splits a chapter string into :class:`Segment` objects.

    An LLM call is used to identify dialogue attribution.

    Usage::

        parser = DialogueParser()
        segments = parser.parse(chapter_text)

    TODO: implement real LLM call (e.g. via openai / local Ollama).
    """

    def parse(self, text: str, chapter_id: str = "ch") -> list[Segment]:
        """Parse *text* into a list of :class:`Segment` objects.

        :param text:       Raw chapter text (may contain dialogue).
        :param chapter_id: Short prefix used to generate paragraph IDs.
        :returns:          Ordered list of segments.

        TODO: send text to LLM with a structured prompt; parse JSON response.
        """
        # Placeholder: treat the whole chapter as a single narration segment.
        return [
            Segment(
                text=text,
                speaker="narrator",
                kind="narration",
                paragraph_id=f"{chapter_id}_p0",
            )
        ]
