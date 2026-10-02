Phase 06 — Audio Rendering
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 06 using Phase 00–05 as templates.
Follow their structure EXACTLY.

Inputs:
You receive:
- script_segments: list of script objects from Phase 05
- script_index: lookup table from Phase 05
- settings: normalized_config from Phase 00

Outputs:
You must produce:
- audio_chunks: [
    {
        audio_id: "aud_0001",
        script_id: "scr_0001",
        chapter_id: "ch1",
        path: "relative/path.wav",
        metadata: { duration_ms, sample_rate, format }
    }
]
- audio_index: { audio_id: audio_chunk }
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
- processor.py must be pure logic.
- No filesystem writes.
- No logging.
- No network calls.
- No side effects.
- runner.py must follow Phase 00 exactly.
- debug.py must write:
    audio_chunks.json
    audio_index.json
    meta.json
    summary.json
- Tests must follow Phase 00 patterns.
- All code must be deterministic.
- All artifacts must be JSON.
