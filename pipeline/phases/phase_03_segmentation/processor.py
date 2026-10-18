"""
Phase 03 — Segmentation Processor
"""

import re
import time
from collections import Counter
from .input_schema import Phase03Input
from .output_schema import Phase03Output


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_WORD_PATTERN = re.compile(r"\b\w+\b")


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def _split_sentences(paragraph: str) -> list[str]:
    if not paragraph:
        return []
    sentences = [s.strip() for s in _SENTENCE_BOUNDARY.split(paragraph) if s.strip()]
    return sentences or [paragraph.strip()]


def _segment_kind_for_text(text: str) -> str:
    if text.startswith('"') or text.startswith("“"):
        return "quoted"
    if text.startswith("-") or text.startswith("—"):
        return "line"
    return "sentence"


def _build_segments(chapter_id: str, text: str, sequence_start: int) -> tuple[list[dict], int]:
    segments: list[dict] = []
    sequence = sequence_start

    for paragraph_index, paragraph in enumerate(_split_paragraphs(text)):
        for sentence in _split_sentences(paragraph):
            segment_id = f"{chapter_id}_seg{sequence:04d}"
            segments.append(
                {
                    "segment_id": segment_id,
                    "chapter_id": chapter_id,
                    "sequence": sequence,
                    "text": sentence,
                    "paragraph_index": paragraph_index,
                    "segment_kind": _segment_kind_for_text(sentence),
                    "word_count": len(_WORD_PATTERN.findall(sentence)),
                    "char_count": len(sentence),
                }
            )
            sequence += 1

    return segments, sequence


def process(input_data: Phase03Input) -> Phase03Output:
    start = time.time()

    segments: list[dict] = []
    sequence = 0
    per_chapter_counts: dict[str, int] = {}

    for chapter_id, text in input_data.normalized_chapters.items():
        chapter_segments, sequence = _build_segments(chapter_id, text, sequence)
        segments.extend(chapter_segments)
        per_chapter_counts[chapter_id] = len(chapter_segments)

    kind_counts = dict(Counter(seg["segment_kind"] for seg in segments))

    output = Phase03Output(
        segments=segments,
        segmentation_stats={
            "chapters": len(input_data.normalized_chapters),
            "total_segments": len(segments),
            "segments_per_chapter": per_chapter_counts,
            "segment_kind_counts": kind_counts,
        },
        meta={
            "phase": "03_segmentation",
            "version": "1.0.0",
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
