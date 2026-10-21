Phase 08 — Final Packaging
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 08 using Phase 00–07 as templates.
Follow their structure EXACTLY.

Inputs:
You receive:
- stitched_audio: list of stitched chapter audio objects from Phase 07
- stitched_index: lookup table from Phase 07
- settings: normalized_config from Phase 00

Outputs:
You must produce:
- package_manifest: {
    "audiobook": {
        "chapters": [
            {
                "chapter_id": "ch1",
                "stitched_id": "sti_0001",
                "path": "relative/path.wav",
                "metadata": {...}
            }
        ]
    },
    "epub": {
        "chapters": [
            {
                "chapter_id": "ch1",
                "title": "...",
                "text": "normalized text",
                "semantic": {...}
            }
        ],
        "metadata": {...}
    }
}
- package_index: { "audiobook": {...}, "epub": {...} }
Plus:
- meta
- input_summary
- output_summary
- errors[]
- warnings[]
- timings{}

Rules:
- Do NOT import legacy code. Use it ONLY as reference:
    legacy/ebook_app/package/*
    legacy/ebook_app/epub/*
    legacy/ebook_app/audio/*
- processor.py must be pure logic.
- No filesystem writes.
- No logging.
- No network calls.
- No side effects.
- runner.py must follow Phase 00 exactly.
- debug.py must write:
    package_manifest.json
    package_index.json
    meta.json
    summary.json
- Tests must follow Phase 00 patterns.
- All code must be deterministic.
- All artifacts must be JSON.
