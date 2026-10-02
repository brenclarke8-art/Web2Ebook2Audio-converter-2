"""
Phase 01 — Source Acquisition Processor

Copilot Instructions:
- Implement ONLY the helper functions below.
- Follow Phase 00 patterns EXACTLY.
- Use legacy/scrape_clean/* ONLY as reference.
- NEVER import legacy code.
- NEVER perform network calls.
- NEVER perform filesystem writes.
- NEVER perform HTML cleaning or normalization.
- ALWAYS extract the full chapter_index.
- raw_payloads MUST contain only selected chapters.
"""

import time
from .input_schema import Phase01Input
from .output_schema import Phase01Output

# ------------------------------------------------------------
# Helper functions Copilot must implement
# ------------------------------------------------------------

def _load_web_source(source: dict) -> tuple:
    """
    PURPOSE:
        Extract the full chapter index and raw HTML/text for a web source.

    INPUT:
        source = {
            "type": "web",
            "url": "...",
            "chapter_range": [start, end] (optional)
        }

    OUTPUT:
        chapter_index: list[dict]
            [
                {
                    "chapter_id": "ch1",
                    "title": "Chapter 1",
                    "order": 1
                },
                ...
            ]

        raw_payloads: dict[str, str]
            {
                "ch1": "<raw html or text>",
                "ch2": "<raw html or text>",
                ...
            }

    LEGACY REFERENCES (READ ONLY):
        legacy/scrape_clean/web_scraper.py
        legacy/scrape_clean/browser_scraper.py
        legacy/scrape_clean/chapter_detection.py
        legacy/scrape_clean/html_cleaner.py
        legacy/scrape_clean/parser.py
        legacy/scrape_clean/scraper_rules.json

    RULES:
        - NO network calls.
        - NO HTML cleaning.
        - NO normalization.
        - MUST detect ALL chapters first.
        - MUST extract raw text ONLY for selected chapters.
        - DO NOT apply chapter_range filtering here. The main processor handles filtering.
        - chapter_id MUST be deterministic (e.g., 'ch1', 'ch2', ...).
        - MUST be deterministic and pure.

    """
    return [], {}


def _load_epub_source(source: dict) -> tuple:
    """
    PURPOSE:
        Extract chapter index + raw HTML/text from an EPUB file.

    INPUT:
        source = {
            "type": "epub",
            "file_path": "...",
            "chapter_range": [...]
        }

    LEGACY REFERENCES:
        legacy/scrape_clean/epub_importer.py
        legacy/scrape_clean/parser.py
        legacy/scrape_clean/chapter_detection.py
        legacy/scrape_clean/html_cleaner.py

    RULES:
        - MUST parse EPUB structure deterministically.
        - MUST detect ALL chapters first.
        - raw_payloads MUST contain only selected chapters.
        - DO NOT apply chapter_range filtering here. The main processor handles filtering.
        - chapter_id MUST be deterministic.
        - NO filesystem reads (simulate logic only).

    """
    return [], {}


def _load_pdf_source(source: dict) -> tuple:
    """
    PURPOSE:
        Extract chapter index + raw text from a PDF source.

    LEGACY REFERENCES:
        legacy/scrape_clean/pdf_importer.py
        legacy/scrape_clean/parser.py
        legacy/scrape_clean/chapter_detection.py

    RULES:
        - MUST simulate PDF → text extraction deterministically.
        - MUST detect ALL chapters first.
        - raw_payloads MUST contain only selected chapters.
        - DO NOT apply chapter_range filtering here. The main processor handles filtering.
        - chapter_id MUST be deterministic.
        - NO PDF library usage.
        - NO filesystem reads.

    """
    return [], {}


def _load_ocr_source(source: dict) -> tuple:
    """
    PURPOSE:
        Extract chapter index + raw OCR text from images.

    LEGACY REFERENCES:
        legacy/scrape_clean/ocr_importer.py
        legacy/scrape_clean/text_normalizer.py
        legacy/scrape_clean/chapter_detection.py

    RULES:
        - MUST simulate OCR extraction deterministically.
        - MUST detect ALL chapters first.
        - raw_payloads MUST contain only selected chapters.
        - DO NOT apply chapter_range filtering here. The main processor handles filtering.
        - chapter_id MUST be deterministic.
        - NO OCR engine calls.
        - NO filesystem reads.

    """
    return [], {}


def _load_text_source(source: dict) -> tuple:
    """
    PURPOSE:
        Extract chapter index + raw text from a plain text file.

    LEGACY REFERENCES:
        legacy/scrape_clean/file_importer.py
        legacy/scrape_clean/text_normalizer.py
        legacy/scrape_clean/chapter_detection.py

    RULES:
        - MUST simulate text loading deterministically.
        - MUST detect ALL chapters first.
        - raw_payloads MUST contain only selected chapters.
        - DO NOT apply chapter_range filtering here. The main processor handles filtering.
        - chapter_id MUST be deterministic.
        - NO filesystem reads.

    """
    return [], {}


# ------------------------------------------------------------
# Main processor
# ------------------------------------------------------------

def process(input_data: Phase01Input) -> Phase01Output:
    start = time.time()

    source = input_data.source
    stype = source.get("type")

    if stype == "web":
        chapter_index, raw_payloads = _load_web_source(source)
    elif stype == "epub":
        chapter_index, raw_payloads = _load_epub_source(source)
    elif stype == "pdf":
        chapter_index, raw_payloads = _load_pdf_source(source)
    elif stype == "ocr":
        chapter_index, raw_payloads = _load_ocr_source(source)
    elif stype == "text":
        chapter_index, raw_payloads = _load_text_source(source)
    else:
        chapter_index, raw_payloads = [], {}

    # ------------------------------------------------------------
    # Apply chapter_range filtering
    # ------------------------------------------------------------
    chapter_range = source.get("chapter_range")
    if chapter_range:
        start_idx, end_idx = chapter_range
        selected_ids = [
            ch["chapter_id"]
            for ch in chapter_index
            if start_idx <= ch["order"] <= end_idx
        ]
        raw_payloads = {cid: raw_payloads[cid] for cid in selected_ids if cid in raw_payloads}

    output = Phase01Output(
        chapter_index=chapter_index,
        raw_payloads=raw_payloads,
        meta={"phase": "01_source", "timestamp": time.time()},
        input_summary={"source_type": stype},
        output_summary={"chapter_count": len(chapter_index)},
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
