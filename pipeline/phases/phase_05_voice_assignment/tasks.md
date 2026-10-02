Phase 05 — Audio Script Generation
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 05 using Phase 00–04 as templates.
Follow their structure EXACTLY.

Inputs:
You receive:
- enriched_segments: list of enriched segment objects from Phase 04
- enriched_index: lookup table from Phase 04
- settings: normalized_config from Phase 00

Outputs:
You must produce:
- script_segments: [
    {
        script_id: "scr_0001",
        segment_id: "seg_0001",
        chapter_id: "ch1",
        text: "tts-ready text",
        pacing: { pause_ms, speed, emphasis },
        voice: { style, tone, variation },
        metadata: { length, word_count }
    }
]
- script_index: { script_id: script_segment }
Plus:
- meta
- input_summary
- output_summary
- errors[]
- warnings[]
- timings{}

Rules:
- Do NOT import legacy code. Use it ONLY as reference:
    legacy/ebook_app/audio/*
    legacy/ebook_app/tts/*
    legacy/ebook_app/text/*
- processor.py must be pure logic.
- No filesystem writes.
- No logging.
- No network calls.
- No side effects.
- runner.py must follow Phase 00 exactly.
- debug.py must write:
    script_segments.json
    script_index.json
    meta.json
    summary.json
- Tests must follow Phase 00 patterns.
- All code must be deterministic.
- All artifacts must be JSON.
