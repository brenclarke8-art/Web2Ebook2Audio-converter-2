# ebook_app/text/segment/segment_models.py
"""Data models for text segmentation."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class Segment:
    """A single text segment (narration, dialogue, or thought)."""
    text: str
    type: str = "narration"
    speaker: str = ""
    gender: str = "unknown"
    speaker_confidence: float = 0.0
    gender_confidence: float = 0.0
    character_confidence: float = 0.0
    paragraph_id: str = ""
    voice: str = ""
    emotion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Segment":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class DetectedCharacter:
    name: str
    gender: str = "unknown"
    confidence: float = 0.0
    aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SegmentationResult:
    segments: List[Segment]
    detected_characters: List[DetectedCharacter]
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    @property
    def characters(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self.detected_characters]
