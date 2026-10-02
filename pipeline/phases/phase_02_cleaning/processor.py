"""
Phase 02 — Text Normalization Processor

Copilot Instructions:
- Follow Phase 00 and Phase 01 processor.py EXACTLY.
- Rewrite normalization logic using legacy code ONLY as reference:
    legacy/ebook_app/clean/*
    legacy/ebook_app/parse/*
    legacy/ebook_app/text/*
- Do NOT import legacy code.
- Do NOT perform filesystem writes.
- Do NOT perform logging.
- Do NOT perform network calls.
- All logic must be PURE and DETERMINISTIC.
"""

import time
from .input_schema import Phase02Input
from .output_schema import Phase02Output

# Helper stubs Copilot will fill in
def _strip_html(raw: str) -> str:
    """Copilot: rewrite HTML stripping logic using legacy code ONLY as reference."""
    return raw

def _normalize_whitespace(text: str) -> str:
    """Copilot: rewrite whitespace normalization logic."""
    return text

def _compute_stats(text: str) -> dict:
    """Copilot: compute deterministic chapter statistics."""
    return {"length": len(text), "word_count": len(text.split())}

def process(input_data: Phase02Input) -> Phase02Output:
    start = time.time()

    normalized = {}
    stats = {}

    for chapter in input_data.chapter_index:
        cid = chapter["chapter_id"]
        raw = input_data.raw_payloads.get(cid, "")

        cleaned = _strip_html(raw)
        cleaned = _normalize_whitespace(cleaned)

        normalized[cid] = cleaned
        stats[cid] = _compute_stats(cleaned)

    output = Phase02Output(
        normalized_chapters=normalized,
        chapter_stats=stats,
        meta={
            "phase": "02_normalize",
            "version": "1.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "chapter_count": len(input_data.chapter_index),
            "payload_count": len(input_data.raw_payloads),
        },
        output_summary={
            "normalized_count": len(normalized),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
