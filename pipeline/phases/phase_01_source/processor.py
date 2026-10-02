"""
Phase 01 — Source Acquisition Processor

Copilot Instructions:
- Follow Phase 00 processor.py EXACTLY.
- Rewrite source acquisition logic cleanly using legacy code ONLY as reference:
    legacy/ebook_app/text/*
    legacy/ebook_app/scrape/*
    legacy/ebook_app/parse/*
    legacy/ebook_app/epub/*
    legacy/ebook_app/pdf/*
    legacy/ebook_app/ocr/*
- Do NOT import legacy code.
- Do NOT perform filesystem writes.
- Do NOT perform logging.
- Do NOT perform network calls.
- Do NOT use global state.
- Do NOT introduce side effects.
- All logic must be PURE and DETERMINISTIC.
- Implement source-type dispatch inside process().
- Implement helper functions for each source type and let Copilot fill them in.
"""

import time
from .input_schema import Phase01Input
from .output_schema import Phase01Output


# ---------------------------------------------------------------------------
# Helper stubs Copilot will fill in using legacy code as reference
# ---------------------------------------------------------------------------

def _load_web_source(source: dict) -> (list, dict):
    """Copilot: rewrite web scraping logic using legacy code ONLY as reference."""
    return [], {}

def _load_epub_source(source: dict) -> (list, dict):
    """Copilot: rewrite EPUB parsing logic using legacy code ONLY as reference."""
    return [], {}

def _load_pdf_source(source: dict) -> (list, dict):
    """Copilot: rewrite PDF parsing logic using legacy code ONLY as reference."""
    return [], {}

def _load_ocr_source(source: dict) -> (list, dict):
    """Copilot: rewrite OCR extraction logic using legacy code ONLY as reference."""
    return [], {}

def _load_text_source(source: dict) -> (list, dict):
    """Copilot: rewrite plain text chapter detection using legacy code ONLY as reference."""
    return [], {}


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

def process(input_data: Phase01Input) -> Phase01Output:
    start = time.time()

    source = input_data.source
    source_type = source.get("type")

    # Dispatch based on source type
    if source_type == "web":
        chapter_index, raw_payloads = _load_web_source(source)
    elif source_type == "epub":
        chapter_index, raw_payloads = _load_epub_source(source)
    elif source_type == "pdf":
        chapter_index, raw_payloads = _load_pdf_source(source)
    elif source_type == "ocr":
        chapter_index, raw_payloads = _load_ocr_source(source)
    elif source_type == "text":
        chapter_index, raw_payloads = _load_text_source(source)
    else:
        chapter_index, raw_payloads = [], []

    output = Phase01Output(
        chapter_index=chapter_index,
        raw_payloads=raw_payloads,
        meta={
            "phase": "01_source",
            "version": "1.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "source_type": source_type,
            "source_fields": list(source.keys()),
        },
        output_summary={
            "chapter_count": len(chapter_index),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
