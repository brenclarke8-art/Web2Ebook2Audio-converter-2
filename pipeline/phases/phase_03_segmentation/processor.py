"""
Phase 03 — Segmentation Processor

Copilot Instructions:
- Follow Phase 00–02 processor.py EXACTLY.
- Rewrite segmentation logic using legacy code ONLY as reference:
    legacy/ebook_app/segment/*
    legacy/ebook_app/text/*
    legacy/ebook_app/parse/*
- Do NOT import legacy code.
- Do NOT perform filesystem writes.
- Do NOT perform logging.
- Do NOT perform network calls.
- All logic must be PURE and DETERMINISTIC.
"""

import time
from .input_schema import Phase03Input
from .output_schema import Phase03Output

# Helper stubs Copilot will fill in
def _segment_paragraphs(text: str) -> list:
    """Copilot: rewrite paragraph segmentation logic using legacy code ONLY as reference."""
    return text.split("\n\n")

def _segment_sentences(text: str) -> list:
    """Copilot: rewrite sentence segmentation logic using legacy code ONLY as reference."""
    return text.split(". ")

def _build_segments(chapter_id: str, text: str) -> list:
    """Copilot: combine paragraph + sentence segmentation into stable segment objects."""
    return []

def process(input_data: Phase03Input) -> Phase03Output:
    start = time.time()

    segments = []
    segment_index = {}

    for chapter_id, text in input_data.normalized_chapters.items():
        chapter_segments = _build_segments(chapter_id, text)

        for seg in chapter_segments:
            segments.append(seg)
            segment_index[seg["segment_id"]] = seg

    output = Phase03Output(
        segments=segments,
        segment_index=segment_index,
        meta={
            "phase": "03_segment",
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
