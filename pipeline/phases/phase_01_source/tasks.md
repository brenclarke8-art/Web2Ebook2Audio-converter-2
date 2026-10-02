Phase 01 — Source Acquisition
Copilot Instructions (READ THIS BEFORE GENERATING ANY CODE)

Your job is to implement Phase 01 — Source Acquisition using Phase 00 as the template. Follow Phase 00’s structure EXACTLY.

Inputs
You receive:

source: {
type: "web" | "epub" | "pdf" | "text" | "ocr",
url?: string,
file_path?: string,
chapter_range?: [start, end],
...
}

settings: normalized_config from Phase 00

Outputs
You must produce:

chapter_index: [
{ chapter_id, title, source_offsets, ... }
]

raw_payloads: {
chapter_id: "<raw html or text>"
}

Plus the standard fields:
meta
input_summary
output_summary
errors[]
warnings[]
timings{}

Rules
Do NOT import legacy code. Use it ONLY as reference:

legacy/ebook_app/text/*
legacy/ebook_app/scrape/*
legacy/ebook_app/parse/*
legacy/ebook_app/epub/*
legacy/ebook_app/pdf/*
legacy/ebook_app/ocr/*

processor.py must be pure logic.
No filesystem writes.
No logging.
No network calls.
No side effects.
No imports from legacy code.

runner.py must follow Phase 00 exactly.
Validate input schema, call process(), write debug artifacts, return output_model.dict().

debug.py must write the following JSON artifacts to pipeline/artifacts/phases/01_source/:
index.json
raw_payloads.json
meta.json
summary.json

Tests must follow Phase 00 patterns:
test_processor.py
test_runner.py
test_contracts.py

Global Requirements
All code must be deterministic.
All artifacts must be JSON.
All structures must mirror Phase 00 patterns.