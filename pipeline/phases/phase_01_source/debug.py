"""
Phase 01 — Source Acquisition Debug Writer

Copilot Instructions:
- Follow Phase 00 debug.py EXACTLY.
- Write ONLY the following JSON artifacts:
    index.json
    raw_payloads.json
    meta.json
    summary.json
- Do NOT add additional artifacts.
- Do NOT change naming conventions.
- Do NOT write anything other than JSON.
- All filesystem writes for Phase 01 MUST occur here, not in processor.py.
- Do NOT modify output.chapter_index or output.raw_payloads before writing.
"""

import json
from pathlib import Path
from .output_schema import Phase01Output

def write_debug_artifacts(context: dict, output: Phase01Output):
    base = Path(context["artifact_root"]) / "phases" / "01_source"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "index.json", "w", encoding="utf-8") as f:
        json.dump(output.chapter_index, f, indent=2)

    with open(base / "raw_payloads.json", "w", encoding="utf-8") as f:
        json.dump(output.raw_payloads, f, indent=2)

    with open(base / "meta.json", "w", encoding="utf-8") as f:
        json.dump(output.meta, f, indent=2)

    with open(base / "summary.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "input_summary": output.input_summary,
                "output_summary": output.output_summary,
            },
            f,
            indent=2,
        )
