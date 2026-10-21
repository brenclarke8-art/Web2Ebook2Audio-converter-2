Phase 07 — Audio Stitching
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 07 using Phase 00–06 as templates.
Follow their structure EXACTLY.

Inputs:
You receive:
- audio_chunks: list of audio chunk objects from Phase 06
- audio_index: lookup table from Phase 06
- settings: normalized_config from Phase 00

Outputs:
You must produce:
- stitched_audio: [
    {
        stitched_id: "sti_0001",
        chapter_id: "ch1",
        chunk_ids: [...],
        path: "relative/path.wav",
        metadata: { duration_ms, sample_rate, format }
    }
]
- stitched_index: { stitched_id: stitched_audio }
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
    legacy/ebook_app/stitch/*
- processor.py must be pure logic.
- No filesystem writes.
- No logging.
- No network calls.
- No side effects.
- runner.py must follow Phase 00 exactly.
- debug.py must write:
    stitched_audio.json
    stitched_index.json
    meta.json
    summary.json
- Tests must follow Phase 00 patterns.
- All code must be deterministic.
- All artifacts must be JSON.
