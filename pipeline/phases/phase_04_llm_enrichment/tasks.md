Phase 04 — Semantic Enrichment
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 04 using Phase 00–03 as templates.
Follow their structure EXACTLY.

Inputs:
You receive:
- segments: list of segment objects from Phase 03
- segment_index: lookup table from Phase 03
- settings: normalized_config from Phase 00

Outputs:
You must produce:
- enriched_segments: [
    {
        segment_id,
        chapter_id,
        text,
        semantic: {
            entities: [...],
            keywords: [...],
            topics: [...],
            sentiment: "positive" | "neutral" | "negative",
            readability: {...},
            embedding: [...],
            summary: "..."
        }
    }
]
- enriched_index: { segment_id: enriched_segment }
Plus:
- meta
- input_summary
- output_summary
- errors[]
- warnings[]
- timings{}

Rules:
- Do NOT import legacy code. Use it ONLY as reference:
    legacy/ebook_app/semantic/*
    legacy/ebook_app/nlp/*
    legacy/ebook_app/text/*
- processor.py must be pure logic.
- No filesystem writes.
- No logging.
- No network calls.
- No side effects.
- runner.py must follow Phase 00 exactly.
- debug.py must write:
    enriched_segments.json
    enriched_index.json
    meta.json
    summary.json
- Tests must follow Phase 00 patterns.
- All code must be deterministic.
- All artifacts must be JSON.
