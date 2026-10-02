"""
Phase 07 — Audio Stitching Debug Writer

Copilot Instructions:
- Follow Phase 00–06 debug.py EXACTLY.
- Write ONLY:
    stitched_audio.json
    stitched_index.json
    meta.json
    summary.json
"""

import json
from pathlib import Path
from .output_schema import Phase07Output

def write_debug_artifacts(context: dict, output: Phase07Output):
    base = Path(context["artifact_root"]) / "phases" / "07_stitch"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "stitched_audio.json", "w", encoding="utf-8") as f:
        json.dump(output.stitched_audio, f, indent=2)

    with open(base / "stitched_index.json", "w", encoding="utf-8") as f:
        json.dump(output.stitched_index, f, indent=2)

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
