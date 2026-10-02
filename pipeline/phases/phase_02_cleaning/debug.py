"""
Phase 02 — Text Normalization Debug Writer

Copilot Instructions:
- Follow Phase 00 and Phase 01 debug.py EXACTLY.
- Write ONLY:
    normalized.json
    stats.json
    meta.json
    summary.json
"""

import json
from pathlib import Path
from .output_schema import Phase02Output

def write_debug_artifacts(context: dict, output: Phase02Output):
    base = Path(context["artifact_root"]) / "phases" / "02_normalize"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "normalized.json", "w", encoding="utf-8") as f:
        json.dump(output.normalized_chapters, f, indent=2)

    with open(base / "stats.json", "w", encoding="utf-8") as f:
        json.dump(output.chapter_stats, f, indent=2)

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
