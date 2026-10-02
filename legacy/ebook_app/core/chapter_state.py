# ebook_app/app/state/chapter_state.py
"""Per-chapter pipeline state container."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ChapterState:
    """Holds all intermediate state for a single chapter across pipeline phases."""

    chapter_index: int
    url: str = ""
    title: str = ""

    # Phase outputs
    raw_html: str = ""
    scraped_text: str = ""
    translated_text: str = ""
    overridden_text: str = ""
    segments: List[Dict[str, Any]] = field(default_factory=list)
    identified_segments: List[Dict[str, Any]] = field(default_factory=list)
    emotion_segments: List[Dict[str, Any]] = field(default_factory=list)
    final_segments: List[Dict[str, Any]] = field(default_factory=list)

    # Audio
    audio_path: Optional[Path] = None
    audio_duration: float = 0.0

    # Flags
    needs_review: bool = False
    approved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_index": self.chapter_index,
            "url": self.url,
            "title": self.title,
            "scraped_text": self.scraped_text,
            "translated_text": self.translated_text,
            "segments": self.segments,
            "identified_segments": self.identified_segments,
            "emotion_segments": self.emotion_segments,
            "final_segments": self.final_segments,
            "audio_path": str(self.audio_path) if self.audio_path else "",
            "audio_duration": self.audio_duration,
            "needs_review": self.needs_review,
            "approved": self.approved,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterState":
        obj = cls(chapter_index=data.get("chapter_index", 0))
        for key in ("url", "title", "scraped_text", "translated_text",
                    "segments", "identified_segments", "emotion_segments",
                    "final_segments", "audio_duration", "needs_review", "approved"):
            if key in data:
                setattr(obj, key, data[key])
        ap = data.get("audio_path", "")
        obj.audio_path = Path(ap) if ap else None
        return obj
