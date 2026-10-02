Phase 03 — Segmentation
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 03 using Phase 00, Phase 01, and Phase 02 as templates.
Follow their structure EXACTLY.

Inputs:
You receive:
- normalized_chapters: { chapter_id: "cleaned text" }
- chapter_stats: { chapter_id: {...} }
- settings: normalized_config from Phase 00

Outputs:
You must produce:
- segments: [
    {
        segment_id: "seg_0001",
        chapter_id: "ch1",
        text: "paragraph or sentence",
        offsets: { start, end },
        type: "paragraph" | "sentence"
    }
]
- segment_index: { segment_id: {...} }
Plus:
- meta
- input_summary
- output_summary
- errors[]
- warnings[]
- timings{}

Rules:
- Do NOT import legacy code. Use it ONLY as reference:
    legacy/ebook_app/segment/*
    legacy/ebook_app/text/*
    legacy/ebook_app/parse/*
- processor.py must be pure logic.
- No filesystem writes.
- No logging.
- No network calls.
- No side effects.
- runner.py must follow Phase 00 exactly.
- debug.py must write:
    segments.json
    segment_index.json
    meta.json
    summary.json
- Tests must follow Phase 00 patterns.
- All code must be deterministic.
- All artifacts must be JSON.
