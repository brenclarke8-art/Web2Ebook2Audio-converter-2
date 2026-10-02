Phase 09 — File Writing & Export
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 09 using Phase 00–08 as templates.
Follow their structure EXACTLY.

Inputs:
You receive:
- package_manifest: from Phase 08
- package_index: from Phase 08
- settings: normalized_config from Phase 00
- context: contains artifact_root

Outputs:
You must produce:
- export_manifest: {
    "audiobook_dir": "...",
    "epub_dir": "...",
    "metadata_path": "...",
    "files_written": [...]
}
- export_index: { "audiobook": {...}, "epub": {...}, "metadata": {...} }
Plus:
- meta
- input_summary
- output_summary
- errors[]
- warnings[]
- timings{}

Rules:
- This phase MAY write files.
- Writes MUST be deterministic.
- Writes MUST be limited to the export directory:
    context["artifact_root"] / "export"
- Do NOT import legacy code. Use it ONLY as reference:
    legacy/ebook_app/export/*
    legacy/ebook_app/epub/*
    legacy/ebook_app/audio/*
- processor.py MUST:
    - create directories
    - write JSON metadata
    - write placeholder audio files
    - write placeholder EPUB files
- runner.py must follow Phase 00 exactly.
- debug.py must write:
    export_manifest.json
    export_index.json
    meta.json
    summary.json
- Tests must follow Phase 00 patterns.
- All artifacts must be JSON.
