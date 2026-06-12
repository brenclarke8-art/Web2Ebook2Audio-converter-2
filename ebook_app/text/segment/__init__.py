# ebook_app/text/segment/__init__.py
from .segmenter import DialogueSegmentationService
from .segment_models import Segment, DetectedCharacter, SegmentationResult
from .dialogue_detector import DialogueDetector
from .thought_detector import ThoughtDetector

__all__ = [
    "DialogueSegmentationService",
    "Segment",
    "DetectedCharacter",
    "SegmentationResult",
    "DialogueDetector",
    "ThoughtDetector",
]
