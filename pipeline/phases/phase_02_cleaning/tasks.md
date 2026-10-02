Phase 02 — Text Normalization
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 02 using Phase 00 and Phase 01 as templates.
Follow their structure EXACTLY.

Inputs:
You receive:
- chapter_index: list of chapter descriptors
- raw_payloads: dict of raw HTML/text per chapter
- settings: normalized_config from Phase 00

Outputs:
You must produce:
- normalized_chapters: { chapter_id: "cleaned text" }
- chapter_stats: { chapter_id: { length, word_count, ... } }
Plus:
- meta
- input_summary
- output_summary
- errors[]
- warnings[]
- timings{}

Rules:
- Do NOT import legacy code. Use it ONLY as reference:
    legacy/ebook_app/clean/*
    legacy/ebook_app/parse/*
    legacy/ebook_app/text/*
- processor.py must be pure logic.
- No filesystem writes.
- No logging.
- No network calls.
- No side effects.
- runner.py must follow Phase 00 exactly.
- debug.py must write:
    normalized.json
    stats.json
    meta.json
    summary.json
- Tests must follow Phase 00 patterns.
- All code must be deterministic.
- All artifacts must be JSON.
