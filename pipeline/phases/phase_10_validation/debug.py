"""
Phase 09 — File Writing & Export Debug Writer

Copilot Instructions:
- Follow Phase 00–08 debug.py EXACTLY.
- Write ONLY:
    export_manifest.json
    export_index.json
    meta.json
    summary.json
"""

import json
from pathlib import Path
from .output_schema import Phase09Output

def write_debug_artifacts(context: dict, output: Phase09Output):
    base = Path(context["artifact_root"]) / "phases" / "09_export"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "export_manifest.json", "w", encoding="utf-8") as f:
        json.dump(output.export_manifest, f, indent=2)

    with open(base / "export_index.json", "w", encoding="utf-8") as f:
        json.dump(output.export_index, f, indent=2)

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
