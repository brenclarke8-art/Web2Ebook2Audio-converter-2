# Phase 00_fetch — Web Acquisition Layer

## Purpose
Fetch the index URL, extract chapter URLs, apply chapter_range, fetch each chapter,
and produce a `source` object for Phase 01_source.

## Responsibilities
- Perform network calls (index + chapters)
- Parse HTML using BeautifulSoup
- Hybrid extraction:
  - Site-specific rules (scraper_rules.json)
  - Generic fallback extraction
- Skip failed chapter fetches (record warnings)
- Produce deterministic JSON output
- Write debug artifacts

## Forbidden
- No normalization
- No cleaning
- No segmentation
- No chapter ordering logic
- No deterministic purity (network calls allowed)
- No legacy imports

## Output → Phase 01_source
Produces:
    source = {
    "type": "web",
    "url": index_url,
    "chapters": [{"title": "...", "content": "<html>...</html>", "source": chapter_url}...],   
    "chapter_range": [start, end]
    }