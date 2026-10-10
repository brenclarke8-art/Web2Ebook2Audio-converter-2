# Phase 00_fetch — Web Acquisition Layer

## Purpose
Phase 00_fetch is the pipeline’s external acquisition layer. It is responsible for
fetching the novel’s index page, discovering chapter URLs, fetching each chapter’s
HTML, and assembling a complete `source` object for Phase 01_source.

This is the ONLY phase allowed to perform network I/O.

---

## Responsibilities

### 1. Fetch Index Page
- Perform an HTTP GET request to the user-provided `index_url`.
- Return raw HTML as a string.
- If the index page cannot be fetched, the phase terminates with an error.

### 2. Hybrid Chapter URL Extraction
Use a hybrid extraction strategy:
- **Rule-based extraction** using `scraper_rules.json` (site-specific selectors).
- **Generic fallback extraction** using BeautifulSoup:
  - Anchor tags containing “chapter”
  - Numeric patterns in URLs
  - Sequential chapter links

If no chapter URLs are found, the phase terminates with an error.

### 3. Apply Chapter Range
- Slice the discovered chapter URL list using `[start, end]`.
- Clamp out-of-range values safely.
- Record warnings if the range exceeds available chapters.

### 4. Fetch Each Chapter (Skip-on-Failure)
For each selected chapter URL:
- Perform an HTTP GET request.
- If the request fails:
  - Skip the chapter.
  - Record a warning.
  - Continue processing remaining chapters.

### 5. Hybrid Chapter Title Extraction
Use hybrid extraction:
- **Rule-based title selector** (if present).
- **Generic fallback**:
  - `<h1>`, `<h2>`, `<title>`
  - First non-empty text block
- If no title is found, generate `"Untitled Chapter"`.

### 6. Hybrid Chapter Content Extraction
Use hybrid extraction:
- **Rule-based content selector** (if present).
- **Generic fallback**:
  - Largest text-containing `<div>`, `<article>`, or `<main>`
  - Raw HTML as final fallback

### 7. Build Source Object for Phase 01
Produce a deterministic `source` object:

{
"type": "web",
"url": index_url,
"chapters": [
{
"title": "...",
"content": "<html>...</html>",
"source": "chapter_url"
},
...
],
"chapter_range": [start, end]
}

Code

This object is consumed directly by Phase 01_source.

### 8. Write Debug Artifacts
Write acquisition artifacts to:

pipeline/artifacts/phase_00_fetch/

Code

Artifacts include:
- `source.json`
- `warnings.json`
- `meta.json`
- (optional future expansion: raw index HTML, raw chapter HTML)

### 9. Produce Phase00FetchOutput
Return a structured output containing:
- `source`
- `meta`
- `input_summary`
- `output_summary`
- `errors`
- `warnings`
- `timings`

---

## Forbidden Actions
Phase 00_fetch must NOT:
- Perform normalization or cleaning of text.
- Modify HTML content.
- Segment paragraphs.
- Reorder chapters.
- Perform deterministic-only logic (network calls break determinism).
- Import or rely on legacy scraper code.
- Perform any Phase 01 responsibilities.

---

## Error Handling Model

### Hard Fail:
- Index page cannot be fetched.
- No chapter URLs extracted.

### Soft Fail (Skip-on-Failure):
- Individual chapter fetch fails.
- Title extraction fails → fallback title.
- Content extraction fails → skip chapter.
- Rule-based selectors fail → fallback extraction.

All soft failures produce warnings but do not stop the phase.

---

## Output → Phase 01_source
Phase 00_fetch produces the canonical `source` object consumed by Phase 01_source.
Phase 01_source must not perform any network calls or HTML parsing.

This separation ensures:
- deterministic downstream phases,
- reproducible pipelines,
- clean architecture,
- and strict responsibility boundaries.
