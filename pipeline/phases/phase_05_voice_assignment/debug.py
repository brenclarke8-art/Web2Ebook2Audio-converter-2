"""
Phase 05 — Audio Script Generation Debug Writer

Copilot Instructions:
- Follow Phase 00–04 debug.py EXACTLY.
- Write ONLY:
    script_segments.json
    script_index.json
    meta.json
    summary.json
"""

import json
from pathlib import Path
from .output_schema import Phase05Output

def write_debug_artifacts(context: dict, output: Phase05Output):
    base = Path(context["artifact_root"]) / "phases" / "05_script"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "script_segments.json", "w", encoding="utf-8") as f:
        json.dump(output.script_segments, f, indent=2)

    with open(base / "script_index.json", "w", encoding="utf-8") as f:
        json.dump(output.script_index, f, indent=2)

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
