"""
Phase 03 — Segmentation Processor
"""

import re
import time
from collections import Counter
from .input_schema import Phase03Input
from .output_schema import Phase03Output


_CHAPTER_TITLE_PATTERN = re.compile(r"^chapter\b", re.IGNORECASE)
_SCENE_BREAK_PATTERN = re.compile(r"^(?:[-*_~•\s]{3,}|#\s*#\s*#)$")
_ITALIC_TAG_PATTERN = re.compile(r"<\s*(?:i|em)\b.*?>.*?<\s*/\s*(?:i|em)\s*>", re.IGNORECASE | re.DOTALL)
_MARKDOWN_ITALIC_PATTERN = re.compile(r"(?<!\w)(?:\*[^*\n]+\*|_[^_\n]+_)(?!\w)")
_SINGLE_QUOTE_PATTERN = re.compile(r"(^|[^\w])['‘’][^'‘’]+['‘’]([^\w]|$)")
_DOUBLE_QUOTE_PATTERN = re.compile(r'["“”][^"“”]+["“”]')


def _split_paragraphs(text: str) -> list[tuple[str, int, int]]:
    segments: list[tuple[str, int, int]] = []
    source = text or ""
    separator_pattern = re.compile(r"\n\s*\n")

    cursor = 0
    for separator in separator_pattern.finditer(source):
        raw = source[cursor:separator.start()]
        paragraph = raw.strip()
        if paragraph:
            leading_ws = len(raw) - len(raw.lstrip())
            trailing_ws = len(raw) - len(raw.rstrip())
            start = cursor + leading_ws
            end = separator.start() - trailing_ws
            segments.append((paragraph, start, end))
        cursor = separator.end()

    raw = source[cursor:]
    paragraph = raw.strip()
    if paragraph:
        leading_ws = len(raw) - len(raw.lstrip())
        trailing_ws = len(raw) - len(raw.rstrip())
        start = cursor + leading_ws
        end = len(source) - trailing_ws
        segments.append((paragraph, start, end))

    return segments


def _detect_text_markers(text: str) -> list[str]:
    markers: list[str] = []
    if _DOUBLE_QUOTE_PATTERN.search(text):
        markers.append("double_quote")
    if _SINGLE_QUOTE_PATTERN.search(text):
        markers.append("single_quote")
    if _ITALIC_TAG_PATTERN.search(text) or _MARKDOWN_ITALIC_PATTERN.search(text):
        markers.append("italicized")
    return markers


def _is_heading_candidate(text: str) -> bool:
    compact = " ".join(text.split())
    if not compact or len(compact) > 90:
        return False
    if compact.endswith((".", "?", "!", ";", ":", ")")):
        return False
    words = compact.split()
    if len(words) > 10:
        return False
    return compact.isupper() or compact.istitle()


def _structural_type(text: str) -> str:
    compact = " ".join(text.split())
    if _CHAPTER_TITLE_PATTERN.match(compact):
        return "chapter_title"
    if _SCENE_BREAK_PATTERN.match(compact):
        return "scene_break"
    if _is_heading_candidate(compact):
        return "heading"
    return "paragraph"


def _build_segments(chapter_id: str, text: str) -> list[dict]:
    chapter_segments: list[dict] = []
    paragraph_positions = _split_paragraphs(text)

    for sequence, (paragraph, start, end) in enumerate(paragraph_positions, start=1):
        chapter_segments.append(
            {
                "segment_id": f"{chapter_id}_seg{sequence:04d}",
                "chapter_id": chapter_id,
                "sequence": sequence,
                "paragraph_index": sequence - 1,
                "structural_type": _structural_type(paragraph),
                "text": paragraph,
                "text_markers": _detect_text_markers(paragraph),
                "source_offset_start": start,
                "source_offset_end": end,
            }
        )

    return chapter_segments


def process(input_data: Phase03Input) -> Phase03Output:
    start = time.time()

    segments: list[dict] = []
    per_chapter_counts: dict[str, int] = {}

    for chapter_id, text in input_data.normalized_chapters.items():
        chapter_segments = _build_segments(chapter_id, text)
        segments.extend(chapter_segments)
        per_chapter_counts[chapter_id] = len(chapter_segments)

    structural_type_counts = dict(Counter(seg["structural_type"] for seg in segments))

    output = Phase03Output(
        segments=segments,
        segmentation_stats={
            "chapters": len(input_data.normalized_chapters),
            "total_segments": len(segments),
            "segments_per_chapter": per_chapter_counts,
            "structural_type_counts": structural_type_counts,
        },
        meta={
            "phase": "03_segmentation",
            "version": "2.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "chapter_count": len(input_data.normalized_chapters),
        },
        output_summary={
            "segment_count": len(segments),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
