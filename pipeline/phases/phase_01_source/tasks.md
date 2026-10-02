Phase 01 — Source Acquisition
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Phase 01 is responsible for acquiring source material and producing a structured chapter_index and raw_payloads. It receives a source descriptor (web, epub, pdf, text, ocr) and extracts all chapter text or HTML from that source. The output of Phase 01 is a deterministic representation of the book’s raw content, organized by chapter_id, ready for normalization in Phase 02.

Phase 01 must always extract the full chapter index from the source, regardless of which chapters the user wants. After building the complete chapter_index, Phase 01 must extract raw text or HTML only for the chapters specified in source.chapter_range. If chapter_range is omitted, Phase 01 extracts all chapters. The output must always include the full chapter_index, but raw_payloads must contain only the selected chapters.

Phase 01 does not perform any cleaning, normalization, segmentation, semantic analysis, or audio preparation; it only extracts raw chapter content and structural chapter boundaries.

Follow Phase 00 patterns EXACTLY:
- processor.py must be pure logic
- runner.py must only call processor()
- debug.py must only write JSON artifacts
- schemas must NOT be modified
- tests must NOT be modified

NEVER import legacy code.
Use legacy code ONLY as reference.

Implement the helper functions inside processor.py:
    _load_web_source
    _load_epub_source
    _load_pdf_source
    _load_ocr_source
    _load_text_source

All logic must be:
- deterministic
- pure
- side‑effect‑free
- no filesystem writes
- no logging
- no network calls
- no global state

Use ONLY the following legacy files as reference:

legacy/scrape_clean/api_importer.py  
legacy/scrape_clean/base_scraper.py  
legacy/scrape_clean/browser_scraper.py  
legacy/scrape_clean/chapter_detection.py  
legacy/scrape_clean/epub_importer.py  
legacy/scrape_clean/file_importer.py  
legacy/scrape_clean/html_cleaner.py  
legacy/scrape_clean/ocr_importer.py  
legacy/scrape_clean/parser.py  
legacy/scrape_clean/pdf_importer.py  
legacy/scrape_clean/scraper_rules.json  
legacy/scrape_clean/text_normalizer.py  
legacy/scrape_clean/web_scraper.py  


====================================================================
## Output Examples (Copilot MUST follow this structure)
====================================================================

### Example — Web Source (chapter_range = [2, 3])

chapter_index = [
  {"chapter_id": "ch1", "title": "Prologue", "order": 1},
  {"chapter_id": "ch2", "title": "The Journey Begins", "order": 2},
  {"chapter_id": "ch3", "title": "Crossing the Threshold", "order": 3},
  {"chapter_id": "ch4", "title": "Into the Wild", "order": 4}
]

raw_payloads = {
  "ch2": "<raw html or text for chapter 2>",
  "ch3": "<raw html or text for chapter 3>"
}


### Example — EPUB Source (all chapters)

chapter_index = [
  {"chapter_id": "ch1", "title": "Chapter 1", "order": 1},
  {"chapter_id": "ch2", "title": "Chapter 2", "order": 2},
  {"chapter_id": "ch3", "title": "Chapter 3", "order": 3}
]

raw_payloads = {
  "ch1": "<raw html from spine item 1>",
  "ch2": "<raw html from spine item 2>",
  "ch3": "<raw html from spine item 3>"
}


### Example — PDF Source (chapter_range = [1, 1])

chapter_index = [
  {"chapter_id": "ch1", "title": "Introduction", "order": 1},
  {"chapter_id": "ch2", "title": "Background", "order": 2},
  {"chapter_id": "ch3", "title": "Methods", "order": 3}
]

raw_payloads = {
  "ch1": "<raw extracted text from PDF pages belonging to chapter 1>"
}


### Example — OCR Source (all chapters)

chapter_index = [
  {"chapter_id": "ch1", "title": "Scan 1", "order": 1},
  {"chapter_id": "ch2", "title": "Scan 2", "order": 2}
]

raw_payloads = {
  "ch1": "<raw OCR text block>",
  "ch2": "<raw OCR text block>"
}


### Example — Plain Text Source (chapter_range = [2, 2])

chapter_index = [
  {"chapter_id": "ch1", "title": "Part I", "order": 1},
  {"chapter_id": "ch2", "title": "Part II", "order": 2}
]

raw_payloads = {
  "ch2": "<raw text block for part II>"
}


====================================================================
## Validation Checklist (Copilot MUST satisfy ALL items)
====================================================================

### Structural Rules
- chapter_index MUST be a list of dicts.
- Each chapter dict MUST contain:
  - chapter_id (string)
  - title (string)
  - order (integer)
- raw_payloads MUST be a dict mapping chapter_id → raw text or raw HTML.

### Chapter Index Rules
- MUST detect ALL chapters from the source.
- MUST preserve chapter order.
- MUST generate deterministic chapter_id values.
- MUST NOT skip chapters even if chapter_range is provided.

### Chapter Range Rules
- If chapter_range is provided:
  - raw_payloads MUST contain ONLY chapters in the range.
- If chapter_range is omitted:
  - raw_payloads MUST contain ALL chapters.
- chapter_index MUST always contain ALL chapters.

### Raw Payload Rules
- MUST contain RAW text or HTML.
- MUST NOT:
  - clean HTML
  - normalize whitespace
  - segment text
  - enrich text
  - extract metadata
  - remove tags
  - convert formats

### Determinism Rules
- MUST NOT use randomness.
- MUST NOT use timestamps for chapter_id generation.
- MUST NOT use external scraping libraries.
- MUST NOT perform network calls.
- MUST NOT perform filesystem reads.

### Phase Boundary Rules
Phase 01 MUST NOT:
- clean or normalize text (Phase 02)
- segment text (Phase 03)
- enrich text (Phase 04)
- generate script (Phase 05)
- render audio (Phase 06)
- stitch audio (Phase 07)
- package (Phase 08)
- export files (Phase 09)

### Error Handling Rules
- MUST NOT throw exceptions for missing chapters.
- MUST return empty structures if the source is invalid.
- MUST NOT modify schemas.


====================================================================
Your job:
- Read ONLY the legacy files listed above.
- Understand how they extract raw text/HTML/chapters.
- Rewrite the logic cleanly and deterministically.
- Produce chapter_index and raw_payloads.
- Do NOT replicate legacy side effects.
- Do NOT replicate legacy I/O.
- Do NOT replicate legacy network calls.
- Only replicate the logic flow and transformations.

Generate ONLY the helper function implementations.
Do NOT modify any other files.
