"""
Phase 04 — Semantic Enrichment Debug Writer

Copilot Instructions:
- Follow Phase 00–03 debug.py EXACTLY.
- Write ONLY:
    enriched_segments.json
    enriched_index.json
    meta.json
    summary.json
"""

import json
from pathlib import Path
from .output_schema import Phase04Output

def write_debug_artifacts(context: dict, output: Phase04Output):
    base = Path(context["artifact_root"]) / "phases" / "04_enrich"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "enriched_segments.json", "w", encoding="utf-8") as f:
        json.dump(output.enriched_segments, f, indent=2)

    with open(base / "enriched_index.json", "w", encoding="utf-8") as f:
        json.dump(output.enriched_index, f, indent=2)

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
