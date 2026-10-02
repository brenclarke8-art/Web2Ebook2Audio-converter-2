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

Your job:
- Read ONLY these files
- Understand how they extract raw text/HTML/chapters
- Rewrite the logic cleanly and deterministically
- Produce chapter_index and raw_payloads
- Do NOT replicate legacy side effects
- Do NOT replicate legacy I/O
- Do NOT replicate legacy network calls
- Only replicate the logic flow and transformations

Generate ONLY the helper function implementations.
Do NOT modify any other files.
